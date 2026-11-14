"""
Coleta do que está bombando no Brasil e fora, de fontes gratuitas:

  - YouTube Data API v3 (vídeos em alta por país e categoria)  -> precisa de YOUTUBE_API_KEY (grátis, 10k unidades/dia)
  - Google Trends (feed RSS de buscas em alta por país)         -> sem chave
  - Wikipedia (artigos mais lidos ontem, pt e en)               -> sem chave
  - Reddit (top do dia em subreddits que combinam com o canal)  -> sem chave, só User-Agent

Cada item vira {fonte, regiao, termo, titulo, url, metrica, score_bruto, extra}.
A pontuação final normaliza por fonte, dá bônus para termos que aparecem em várias
fontes/países e penaliza temas já feitos (via banco).
"""
from __future__ import annotations

import datetime as dt
import math
import re
import xml.etree.ElementTree as ET
from collections import defaultdict

import httpx

from ..config import REDDIT_USER_AGENT, YOUTUBE_API_KEY

TIMEOUT = httpx.Timeout(20.0)
# categorias do YouTube que combinam com o canal: 20 Jogos, 24 Entretenimento, 27 Educação, 28 Ciência e tecnologia, 1 Filmes
CATEGORIAS_YT = ["0", "20", "24", "27", "28", "1"]
SUBREDDITS = ["todayilearned", "Damnthatsinteresting", "philosophy", "psychology", "gaming",
              "movies", "television", "brasil", "explainlikeimfive", "Futurology", "nostalgia"]
IGNORAR_WIKI = re.compile(r"^(Main_Page|Página_principal|Special:|Especial:|Wikipédia:|Wikipedia:|Ficheiro:|File:|Portal:|-)")


def _horas_desde(iso: str) -> float:
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return max(1.0, (dt.datetime.now(dt.timezone.utc) - t).total_seconds() / 3600)


def youtube(regiao: str) -> list[dict]:
    if not YOUTUBE_API_KEY:
        return []
    itens = []
    with httpx.Client(timeout=TIMEOUT) as c:
        for cat in CATEGORIAS_YT:
            params = {"part": "snippet,statistics", "chart": "mostPopular", "regionCode": regiao,
                      "maxResults": 25, "key": YOUTUBE_API_KEY}
            if cat != "0":
                params["videoCategoryId"] = cat
            r = c.get("https://www.googleapis.com/youtube/v3/videos", params=params)
            if r.status_code != 200:
                continue
            for v in r.json().get("items", []):
                sn, st = v["snippet"], v.get("statistics", {})
                views = int(st.get("viewCount", 0))
                vph = views / _horas_desde(sn["publishedAt"])  # velocidade: views por hora
                itens.append({
                    "fonte": "youtube", "regiao": regiao, "termo": sn["title"], "titulo": sn["title"],
                    "url": f"https://youtu.be/{v['id']}", "metrica": "views_por_hora", "score_bruto": vph,
                    "extra": {"canal": sn["channelTitle"], "categoria": cat, "views": views,
                              "tags": sn.get("tags", [])[:12], "comentarios": int(st.get("commentCount", 0))},
                })
    return itens


def google_trends(regiao: str) -> list[dict]:
    r = httpx.get(f"https://trends.google.com/trending/rss?geo={regiao}", timeout=TIMEOUT,
                  headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        return []
    ns = {"ht": "https://trends.google.com/trending/rss"}
    itens = []
    for it in ET.fromstring(r.content).iter("item"):
        trafego = (it.findtext("ht:approx_traffic", default="0", namespaces=ns) or "0")
        n = int(re.sub(r"\D", "", trafego) or 0)
        noticias = [x.findtext("ht:news_item_title", namespaces=ns) for x in it.findall("ht:news_item", ns)]
        itens.append({"fonte": "google_trends", "regiao": regiao, "termo": it.findtext("title"),
                      "titulo": it.findtext("title"), "url": it.findtext("link"), "metrica": "buscas_aprox",
                      "score_bruto": n, "extra": {"noticias": [x for x in noticias if x][:3]}})
    return itens


def wikipedia(projeto: str) -> list[dict]:
    ontem = dt.date.today() - dt.timedelta(days=1)
    url = (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/{projeto}/all-access/"
           f"{ontem:%Y/%m/%d}")
    r = httpx.get(url, timeout=TIMEOUT, headers={"User-Agent": REDDIT_USER_AGENT})
    if r.status_code != 200:
        return []
    regiao = "BR" if projeto.startswith("pt") else "GLOBAL"
    itens = []
    for a in r.json()["items"][0]["articles"][:80]:
        if IGNORAR_WIKI.match(a["article"]):
            continue
        titulo = a["article"].replace("_", " ")
        itens.append({"fonte": "wikipedia", "regiao": regiao, "termo": titulo, "titulo": titulo,
                      "url": f"https://{projeto}.org/wiki/{a['article']}", "metrica": "pageviews",
                      "score_bruto": a["views"], "extra": {"rank": a["rank"]}})
    return itens


def reddit() -> list[dict]:
    itens = []
    with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": REDDIT_USER_AGENT}) as c:
        for sub in SUBREDDITS:
            r = c.get(f"https://www.reddit.com/r/{sub}/top.json", params={"t": "day", "limit": 15})
            if r.status_code != 200:
                continue
            for p in r.json()["data"]["children"]:
                d = p["data"]
                itens.append({"fonte": "reddit", "regiao": "BR" if sub == "brasil" else "GLOBAL",
                              "termo": d["title"], "titulo": d["title"],
                              "url": "https://reddit.com" + d["permalink"], "metrica": "upvotes",
                              "score_bruto": d["score"],
                              "extra": {"sub": sub, "comentarios": d["num_comments"]}})
    return itens


def _palavras(t: str) -> set[str]:
    return {w for w in re.findall(r"[\wÀ-ú]{4,}", (t or "").lower())}


def pontuar(itens: list[dict], ja_feitos: list[str] | None = None) -> list[dict]:
    """Normaliza por fonte (log + percentil), bônus de cruzamento entre fontes/países, penaliza repetidos."""
    por_fonte = defaultdict(list)
    for it in itens:
        por_fonte[it["fonte"]].append(it)
    for lst in por_fonte.values():
        lst.sort(key=lambda x: x["score_bruto"])
        for i, it in enumerate(lst):
            it["score"] = (i + 1) / len(lst) * 0.7 + 0.3 * math.log1p(it["score_bruto"]) / math.log1p(lst[-1]["score_bruto"] or 1)

    # cruzamento: o mesmo assunto em fontes ou países diferentes é sinal forte
    tokens = [(_palavras(it["termo"]), it) for it in itens]
    for pal, it in tokens:
        fontes, regioes = {it["fonte"]}, {it["regiao"]}
        for pal2, it2 in tokens:
            if it2 is not it and len(pal & pal2) >= 1 and len(pal & pal2) / max(1, len(pal)) >= 0.5:
                fontes.add(it2["fonte"])
                regioes.add(it2["regiao"])
        it["cruzamento"] = {"fontes": sorted(fontes), "regioes": sorted(regioes)}
        it["score"] *= 1 + 0.35 * (len(fontes) - 1) + 0.25 * (len(regioes) - 1)

    feitos = [_palavras(t) for t in (ja_feitos or [])]
    for pal, it in tokens:
        if any(len(pal & f) >= 2 for f in feitos):
            it["score"] *= 0.3
            it["ja_feito"] = True
    return sorted(itens, key=lambda x: -x["score"])


def coletar(ja_feitos: list[str] | None = None, limite: int = 60) -> dict:
    itens, erros = [], {}
    tarefas = {
        "youtube_BR": lambda: youtube("BR"), "youtube_US": lambda: youtube("US"),
        "trends_BR": lambda: google_trends("BR"), "trends_US": lambda: google_trends("US"),
        "wiki_pt": lambda: wikipedia("pt.wikipedia"), "wiki_en": lambda: wikipedia("en.wikipedia"),
        "reddit": reddit,
    }
    for nome, f in tarefas.items():
        try:
            itens += f()
        except Exception as e:  # uma fonte fora do ar não derruba a coleta
            erros[nome] = str(e)[:200]
    ranking = pontuar(itens, ja_feitos)
    return {"coletado_em": dt.datetime.now().isoformat(timespec="seconds"), "total": len(itens),
            "erros": erros, "itens": ranking[:limite]}
