"""
Plano de edição: transforma (cenas do artifact + narração + alinhamento) em decisões de edição.

Regras (todas ajustáveis em REGRAS):
  - a NARRAÇÃO manda no tempo: duração da cena = respiro curto + fala + pausa curta. As animações do
    artifact são aceleradas ou desaceleradas (0,6x a 2x) para caber, e nunca alongam a cena
  - cada elemento entra na palavra que fala dele: data-palavra no artifact, JSON do diretor ou,
    sozinho, quando o texto do elemento aparece na narração
  - câmera nunca parada: deriva lenta em toda cena + micro punch-in quando passa ~1,5 s sem nada entrar
  - corte em L: a imagem da próxima cena entra durante a última palavra da cena atual
  - punch-in de câmera nas palavras de destaque (hot) no instante em que são ditas
  - tremor leve + impacto no cartão de capítulo
  - efeito sonoro em cada entrada animada do artifact (pop -> pop, slide -> whoosh, traço -> caneta...)
  - transição forte na troca de capítulo, dissolve curto dentro do capítulo
"""
from __future__ import annotations

import re

from . import alinhamento, camadas as camadas_mod

REGRAS = {
    "respiro": 0.08,              # silêncio antes da fala em cada cena
    "respiro_capitulo": 0.35,
    "pausa": 0.14,                # depois da fala
    "dur_min": 1.2,
    "antecipa_corte": 0.22,       # a transição começa ~0,2 s antes da fala acabar (corte em L)
    "antecipa_entrada": 0.12,     # o elemento começa a entrar um pouco antes da palavra
    "parado_max": 1.5,            # mais que isso sem nada novo na tela -> micro punch-in
    "deriva": 0.022,              # zoom lento ao longo da cena (2,2%: não corta texto na borda)
    "punch_forca": 1.045,
    "sfx_intervalo_min": 0.22,
    "sfx_max_por_cena": 5,
    "transicao_capitulo": ("circleopen", 0.6),   # xfade; com gl-transitions vira "CrossZoom"
    "transicao_cena": ("fade", 0.3),
    "transicao_seco": ("fade", 0.06),
    "transicao_short": ("fade", 0.18),
    "relogio_min": 0.6,           # no máximo desacelera as animações do artifact para 60%
    "relogio_max": 2.0,           # e acelera até 2x
    "punch_intervalo_min": 1.2,
    "lottie_auto": "destaque",    # biblioteca/lottie/destaque.json toca em cima do elemento que entrou na palavra forte
    "lottie_largura": 320,
}
SFX_DA_ANIMACAO = {"pop": "pop", "slideL": "whoosh", "slideR": "whoosh", "grow": "whoosh_grave",
                   "toss": "papel", "draw": "risco_caneta"}


def eh_capitulo(c: dict) -> bool:
    txt = f"{c.get('molde') or ''} {c.get('layout') or ''}".lower()
    return "capitulo" in txt or "capítulo" in txt


def _sfx_da_cena(c: dict, ws: list[dict], respiro: float, relogio: float = 1.0, cap: bool | None = None,
                 entradas: list[dict] | None = None) -> list[dict]:
    lista = []
    # entradas já com o instante real (casado com a fala); sem elas, as animações no tempo do artifact
    fontes = ([{"nome": e["nome"], "duracao": e["duracao"], "real": e["real"]} for e in entradas] if entradas is not None
              else [{"nome": a["nome"], "duracao": a["duracao"], "real": a["atraso"] / relogio} for a in c.get("animacoes", [])])
    for a in sorted(fontes, key=lambda a: a["real"]):
        cat = SFX_DA_ANIMACAO.get(a["nome"])
        if not cat or (cat == "risco_caneta" and a["duracao"] > 1.3):
            continue
        lista.append({"tipo": cat, "em": round(a["real"], 3), "origem": "animacao"})
    if (cap if cap is not None else eh_capitulo(c)):
        lista.append({"tipo": "impacto", "em": round(0.3 / relogio, 3), "origem": "capitulo"})
    # efeito pedido em texto no artifact: 'bipe antes de "Com todo respeito"'
    texto_sfx = c["sfx"] if isinstance(c.get("sfx"), str) else c.get("sfx_texto")
    if texto_sfx:
        from .sfx_texto import do_texto
        lista += do_texto(texto_sfx, ws, 0.0, respiro)
    # efeitos declarados no artifact como lista: {"tipo": "...", "em": segundos | "palavra"}
    for s in (c.get("sfx") if isinstance(c.get("sfx"), list) else []):
        em = s.get("em", 0)
        if isinstance(em, str) and not re.fullmatch(r"[\d.]+", em):
            m = _palavra_em(ws, em)  # ws já está no tempo da cena (com o respiro)
            if m is None:
                continue
            em = m
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


def _sem_acento(s: str) -> str:
    import unicodedata
    return "".join(ch for ch in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(ch) != "Mn")


def _palavra_em(ws: list[dict], alvo: str, depois: float = -1.0) -> float | None:
    """Instante em que a palavra (ou o começo da expressão) é dita. Aceita variações: 'boleto' casa com 'boletos'."""
    termos = [t for t in re.findall(r"\w+", _sem_acento(alvo or "")) if t]
    if not termos:
        return None
    falado = [re.sub(r"\W", "", _sem_acento(w["w"])) for w in ws]
    def casa(a, b):
        return a == b or (min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)))
    for i in range(len(ws)):
        if ws[i]["ini"] < depois:
            continue
        if all(i + j < len(falado) and casa(falado[i + j], t) for j, t in enumerate(termos)):
            return ws[i]["ini"]
    return None


def _palavras_do_texto(texto: str) -> list[str]:
    return [t for t in re.findall(r"\w+", _sem_acento(texto or "")) if len(t) >= 4 and not t.isdigit()]


def _resolver_entradas(c: dict, ws: list[dict], dur: float, relogio: float) -> list[dict]:
    """Em que instante real cada elemento do artifact entra.
    Ordem de preferência: diretor (JSON) > data-palavra no artifact > texto do elemento dito na narração > tempo original."""
    ents = c.get("entradas") or []
    if not ents:
        return []
    limite = max(0.0, dur - 0.35)
    diretor = {}
    for d in c.get("direcao_entradas") or []:
        el, pal = d.get("elemento"), d.get("palavra")
        if not pal:
            continue
        if isinstance(el, int) or (isinstance(el, str) and el.strip().isdigit()):
            k = int(el) - 1
        else:
            alvo = _sem_acento(str(el or ""))
            k = next((e["k"] for e in ents if alvo and alvo in _sem_acento(e.get("texto") or "")), None)
        if k is not None and 0 <= k < len(ents):
            diretor[k] = pal
    ancora_grupo: dict[int, float] = {}
    out = []
    for e in ents:
        real, origem = e["atraso"] / relogio, "artifact"
        pal = diretor.get(e["k"]) or e.get("palavra")
        m = None
        if pal:
            m = _palavra_em(ws, pal)
            origem = "diretor" if e["k"] in diretor else "data-palavra"
        elif e["atraso"] >= 0.5 and 0 < len(e.get("texto") or "") <= 40:
            for t in _palavras_do_texto(e["texto"]):
                m = _palavra_em(ws, t)
                if m is not None:
                    origem = "texto"
                    break
        if m is not None:
            real = m - REGRAS["antecipa_entrada"]
            if e["k"] not in diretor and e.get("palavra"):
                ancora_grupo[e.get("grupo", e["k"])] = real - e["atraso"] / relogio
        elif e.get("grupo", e["k"]) in ancora_grupo:  # filho de um elemento ancorado: anda junto com ele
            real += ancora_grupo[e["grupo"]]
            origem = "grupo"
        out.append({"k": e["k"], "real": real, "orig": e["atraso"] / relogio, "nome": e.get("nome", ""),
                    "duracao": e.get("duracao", 0), "origem": origem})
    # os que não têm palavra seguem a coreografia do artifact entre os vizinhos ancorados
    # (a seta entre "ESTUDA" e "ARRUMA UM EMPREGO" entra entre as duas, não no tempo antigo)
    anc = [o for o in out if o["origem"] in ("diretor", "data-palavra", "texto")]
    if anc:
        for o in out:
            if o["origem"] != "artifact":
                continue
            ant = max((a for a in anc if a["orig"] <= o["orig"]), key=lambda a: a["orig"], default=None)
            dep = min((a for a in anc if a["orig"] > o["orig"]), key=lambda a: a["orig"], default=None)
            if ant and dep and dep["orig"] > ant["orig"]:
                f = (o["orig"] - ant["orig"]) / (dep["orig"] - ant["orig"])
                o["real"] = ant["real"] + f * (dep["real"] - ant["real"])
            elif ant:  # depois do último ancorado: espalha no tempo que sobra
                ult = max(x["orig"] for x in out)
                f = min(1.0, (limite - ant["real"]) / (ult - ant["orig"])) if ult > ant["orig"] else 1.0
                o["real"] = ant["real"] + (o["orig"] - ant["orig"]) * max(0.0, f)
            elif dep:  # antes do primeiro ancorado: comprime entre 0 e ele
                f = min(1.0, dep["real"] / dep["orig"]) if dep["orig"] > 0 else 1.0
                o["real"] = o["orig"] * max(0.0, f)
            o["origem"] = "vizinhos"
    for o in out:
        o["real"] = round(min(limite, max(0.0, o.pop("real"))), 3)
        o["orig"] = round(o["orig"], 3)
        o["em"] = round(o["real"] * relogio, 3)
    return out


def _preencher_parado(movimento: list[dict], entradas: list[dict], ws: list[dict], dur: float, ini: float):
    """Se passa mais de ~1,5 s sem nada novo na tela, um micro punch-in numa palavra longa do trecho."""
    eventos = sorted([0.0] + [e["real"] for e in entradas] + [m["em"] for m in movimento if m["tipo"] == "punch"] + [dur])
    for a, b in zip(eventos, eventos[1:]):
        t = a
        while b - t > REGRAS["parado_max"] + 0.3:
            alvo = t + REGRAS["parado_max"]
            cand = [w for w in ws if alvo - 0.6 <= w["ini"] <= alvo + 0.6 and len(re.sub(r"\W", "", w["w"])) >= 5]
            em = min(cand, key=lambda w: abs(w["ini"] - alvo))["ini"] if cand else alvo
            if em < ini or em > dur - 0.4:
                break
            if all(abs(em - x["em"]) >= REGRAS["punch_intervalo_min"] for x in movimento):
                movimento.append({"tipo": "punch", "em": round(em, 3), "forca": 1.022})
            t = em


def montar(cenas: list[dict], falas: list[dict], curto: bool = False) -> dict:
    """cenas: saída do --extrair; falas: [{arquivo, duracao, palavras, boca}] na mesma ordem."""
    out, t, cabeca = [], 0.0, 0.0
    tem_partes = any(c.get("capitulo") for c in cenas)
    for k, (c, f) in enumerate(zip(cenas, falas)):
        # com partes no artifact (SECTIONS), capítulo = troca de parte; sem elas, cartão de capítulo pelo molde
        cap = (k == 0 or c.get("capitulo") != cenas[k - 1].get("capitulo")) if tem_partes else eh_capitulo(c)
        respiro = REGRAS["respiro_capitulo"] if cap and not curto else REGRAS["respiro"]
        # a fala manda: a cena dura o que a narração dura (as animações se ajustam a ela)
        dur = round(max(respiro + f["duracao"] + REGRAS["pausa"], REGRAS["dur_min"]), 3)
        # relógio: a cena do artifact (c["dur"]) é encaixada na duração da fala, de 0,6x a 2x
        relogio = round(max(REGRAS["relogio_min"], min(REGRAS["relogio_max"], c["dur"] / dur)), 4)
        dur_artifact = round(dur * relogio, 3)
        ws = [{"w": w["w"], "ini": w["ini"] + respiro, "fim": w["fim"] + respiro} for w in f["palavras"]]
        entradas = _resolver_entradas(c, ws, dur, relogio)

        movimento = []
        for h in c.get("destaques") or []:
            m = _palavra_em(ws, h)
            if m is not None and all(abs(m - x["em"]) >= REGRAS["punch_intervalo_min"] for x in movimento):
                movimento.append({"tipo": "punch", "em": round(m, 3), "forca": REGRAS["punch_forca"]})
        if cap:
            movimento.append({"tipo": "tremor", "em": 0.35, "forca": 6, "dur": 0.3})
        _preencher_parado(movimento, entradas, ws, dur, respiro)
        movimento.sort(key=lambda m: m["em"])
        # deriva: zoom lento, alternando aproximar/afastar e o lado do pan
        lado = 1 if k % 2 == 0 else -1
        deriva = ({"de": 1.0, "ate": 1 + REGRAS["deriva"], "dx": 8 * lado, "dy": -4} if k % 3 != 2
                  else {"de": 1 + REGRAS["deriva"], "ate": 1.0, "dx": -8 * lado, "dy": 4})

        # Lottie: os que a cena pede + o acento automático nas palavras fortes
        lotties = []
        for l in c.get("lottie") or []:
            info = camadas_mod.lottie_da_biblioteca(l.get("nome", ""))
            em = l.get("em", 0.5)
            if isinstance(em, str) and not re.fullmatch(r"[\d.]+", em):
                em = _palavra_em(ws, em)
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
            pedido = (c.get("direcao_corte") or "").lower()
            if not prox_cap and pedido in ("seco", "suave", "forte"):
                trans = {"seco": REGRAS["transicao_seco"], "suave": REGRAS["transicao_cena"],
                         "forte": REGRAS["transicao_capitulo"]}[pedido]
        # corte em L: a próxima imagem entra antes da fala desta cena acabar (capítulo: metade da transição)
        if prox is None:
            corte = 0.0
        elif trans == REGRAS["transicao_capitulo"]:
            corte = round(min(dur * 0.4, trans[1] / 2), 3)
        else:  # pausa + antecipação: a transição começa ~0,2 s antes da última palavra terminar
            corte = round(min(dur * 0.4, REGRAS["pausa"] + REGRAS["antecipa_corte"]), 3)

        out.append({
            "indice": c["indice"], "global": k, "parte": c.get("parte", 0), "inicio": round(t, 3), "dur": dur, "cauda": trans[1],
            "cabeca": cabeca, "corte": corte, "v_inicio": round(t - cabeca, 3), "dur_artifact": dur_artifact,
            "entradas": [{"k": e["k"], "em": e["em"]} for e in entradas],
            "entradas_info": entradas, "deriva": deriva,
            "transicao": trans[0], "capitulo": cap,
            "fala": {"arquivo": f["arquivo"], "em": respiro, "duracao": f["duracao"]},
            "palavras": ws, "destaques": c.get("destaques") or [],
            "movimento": movimento, "sfx": _sfx_da_cena(c, ws, respiro, relogio, cap and not curto and k > 0, entradas if c.get("entradas") is not None else None),
            "relogio": relogio,
            "boca": [[a + respiro, b + respiro, v] for a, b, v in f["boca"]] if f.get("boca") else None,
            "camadas": c.get("camadas") or [], "lottie": lotties,
            "titulo_capitulo": ((c.get("capitulo") if tem_partes else None) or _titulo_capitulo(c)) if cap else None,
        })
        t += dur
        cabeca = corte
    return {"duracao": round(t, 3), "cenas": out}
