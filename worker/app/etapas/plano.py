"""
Plano de edição: transforma (cenas do artifact + narração + alinhamento) em decisões de edição.

Regras (todas ajustáveis em REGRAS):
  - duração da cena = respiro + fala + pausa, nunca menor que o fim das animações do artifact
  - punch-in de câmera nas palavras de destaque (hot) no instante em que são ditas
  - tremor leve + impacto no cartão de capítulo
  - efeito sonoro em cada entrada animada do artifact (pop -> pop, slide -> whoosh, traço -> caneta...)
  - transição forte na troca de capítulo, dissolve curto dentro do capítulo
"""
from __future__ import annotations

import re

from . import alinhamento, camadas as camadas_mod

REGRAS = {
    "respiro": 0.25,              # silêncio antes da fala em cada cena
    "respiro_capitulo": 0.6,
    "pausa": 0.35,                # depois da fala
    "folga_animacao": 0.6,        # a cena dura pelo menos até a última animação + folga
    "punch_forca": 1.045,
    "sfx_intervalo_min": 0.22,
    "sfx_max_por_cena": 5,
    "transicao_capitulo": ("circleopen", 0.6),   # xfade; com gl-transitions vira "CrossZoom"
    "transicao_cena": ("fade", 0.3),
    "transicao_short": ("fade", 0.18),
    "relogio_min": 0.6,           # no máximo desacelera as animações do artifact para 60%
    "punch_intervalo_min": 1.2,
    "lottie_auto": "destaque",    # biblioteca/lottie/destaque.json toca em cima do elemento que entrou na palavra forte
    "lottie_largura": 320,
}
SFX_DA_ANIMACAO = {"pop": "pop", "slideL": "whoosh", "slideR": "whoosh", "grow": "whoosh_grave",
                   "toss": "papel", "draw": "risco_caneta"}


def eh_capitulo(c: dict) -> bool:
    txt = f"{c.get('molde') or ''} {c.get('layout') or ''}".lower()
    return "capitulo" in txt or "capítulo" in txt


def _sfx_da_cena(c: dict, ws: list[dict], respiro: float, relogio: float = 1.0, cap: bool | None = None) -> list[dict]:
    lista = []
    for a in sorted(c.get("animacoes", []), key=lambda a: a["atraso"]):
        cat = SFX_DA_ANIMACAO.get(a["nome"])
        if not cat or (cat == "risco_caneta" and a["duracao"] > 1.3):
            continue
        lista.append({"tipo": cat, "em": round(a["atraso"] / relogio, 3), "origem": "animacao"})
    if (cap if cap is not None else eh_capitulo(c)):
        lista.append({"tipo": "impacto", "em": round(0.3 / relogio, 3), "origem": "capitulo"})
    # efeito pedido em texto no artifact: 'bipe antes de "Com todo respeito"'
    if isinstance(c.get("sfx"), str):
        from .sfx_texto import do_texto
        lista += do_texto(c["sfx"], ws, 0.0, respiro)
    # efeitos declarados no artifact como lista: {"tipo": "...", "em": segundos | "palavra"}
    for s in (c.get("sfx") if isinstance(c.get("sfx"), list) else []):
        em = s.get("em", 0)
        if isinstance(em, str) and not re.fullmatch(r"[\d.]+", em):
            m = alinhamento.momento(ws, em)
            if m is None:
                continue
            em = m + respiro
        lista.append({"tipo": s["tipo"], "em": float(em), "origem": "artifact"})
    lista.sort(key=lambda s: s["em"])
    filtrada = []
    for s in lista:
        if filtrada and s["em"] - filtrada[-1]["em"] < REGRAS["sfx_intervalo_min"] and s["origem"] == "animacao":
            continue
        filtrada.append(s)
    prioridade = {"artifact": 0, "ficha": 0, "capitulo": 1, "animacao": 2}
    if len(filtrada) > REGRAS["sfx_max_por_cena"]:
        filtrada = sorted(sorted(filtrada, key=lambda s: prioridade[s["origem"]])[:REGRAS["sfx_max_por_cena"]], key=lambda s: s["em"])
    return filtrada


def _titulo_capitulo(c: dict) -> str:
    """'Capítulo dois: Vice City é um espelho.' -> 'Vice City é um espelho'."""
    t = c.get("narracao", "")
    t = re.sub(r"^\s*(cap[ií]tulo|erro de pensamento|parte)[^:]*:\s*", "", t, flags=re.I)
    return t.strip().rstrip(".!?…")[:60] or (c.get("layout") or "Capítulo")


def montar(cenas: list[dict], falas: list[dict], curto: bool = False) -> dict:
    """cenas: saída do --extrair; falas: [{arquivo, duracao, palavras, boca}] na mesma ordem."""
    out, t = [], 0.0
    tem_partes = any(c.get("capitulo") for c in cenas)
    for k, (c, f) in enumerate(zip(cenas, falas)):
        # com partes no artifact (SECTIONS), capítulo = troca de parte; sem elas, cartão de capítulo pelo molde
        cap = (k == 0 or c.get("capitulo") != cenas[k - 1].get("capitulo")) if tem_partes else eh_capitulo(c)
        respiro = REGRAS["respiro_capitulo"] if cap and not curto else REGRAS["respiro"]
        fim_anim = max([a["atraso"] + a["duracao"] for a in c.get("animacoes", [])] + [0])
        dur = round(max(respiro + f["duracao"] + REGRAS["pausa"], fim_anim + REGRAS["folga_animacao"], 2.0), 3)
        # relógio: se a fala ficou mais longa que a cena original do artifact, as animações
        # andam mais devagar na mesma proporção, para cada elemento entrar junto com a frase
        relogio = round(max(REGRAS["relogio_min"], min(1.0, c["dur"] / dur)), 4)
        ws = [{"w": w["w"], "ini": w["ini"] + respiro, "fim": w["fim"] + respiro} for w in f["palavras"]]

        movimento = []
        for h in c.get("destaques") or []:
            m = alinhamento.momento(ws, h)
            if m is not None and all(abs(m - x["em"]) >= REGRAS["punch_intervalo_min"] for x in movimento):
                movimento.append({"tipo": "punch", "em": round(m, 3), "forca": REGRAS["punch_forca"]})
        if cap:
            movimento.append({"tipo": "tremor", "em": 0.35, "forca": 6, "dur": 0.3})

        # Lottie: os que a cena pede + o acento automático nas palavras fortes
        lotties = []
        for l in c.get("lottie") or []:
            info = camadas_mod.lottie_da_biblioteca(l.get("nome", ""))
            em = l.get("em", 0.5)
            if isinstance(em, str) and not re.fullmatch(r"[\d.]+", em):
                em = alinhamento.momento(ws, em)
            if info and em is not None:
                lotties.append({**{k2: v for k2, v in l.items() if k2 != "em"}, "em": float(em), "dados": info["dados"]})
        auto = camadas_mod.lottie_da_biblioteca(REGRAS["lottie_auto"]) if REGRAS["lottie_auto"] else None
        if auto and not curto:
            for m in movimento:
                if m["tipo"] == "punch":
                    lotties.append({"nome": REGRAS["lottie_auto"], "em": m["em"], "alvo": "ultimo",
                                    "largura": REGRAS["lottie_largura"], "dados": auto["dados"]})

        prox = cenas[k + 1] if k + 1 < len(cenas) else None
        if prox is None:
            trans = (None, 0.0)
        elif curto:
            trans = REGRAS["transicao_short"]
        else:
            prox_cap = (prox.get("capitulo") != c.get("capitulo")) if tem_partes else eh_capitulo(prox)
            trans = REGRAS["transicao_capitulo"] if prox_cap else REGRAS["transicao_cena"]

        out.append({
            "indice": c["indice"], "global": k, "parte": c.get("parte", 0), "inicio": round(t, 3), "dur": dur, "cauda": trans[1],
            "transicao": trans[0], "capitulo": cap,
            "fala": {"arquivo": f["arquivo"], "em": respiro, "duracao": f["duracao"]},
            "palavras": ws, "destaques": c.get("destaques") or [],
            "movimento": movimento, "sfx": _sfx_da_cena(c, ws, respiro, relogio, cap and not curto and k > 0), "relogio": relogio,
            "boca": [[a + respiro, b + respiro, v] for a, b, v in f["boca"]] if f.get("boca") else None,
            "camadas": c.get("camadas") or [], "lottie": lotties,
            "titulo_capitulo": ((c.get("capitulo") if tem_partes else None) or _titulo_capitulo(c)) if cap else None,
        })
        t += dur
    return {"duracao": round(t, 3), "cenas": out}
