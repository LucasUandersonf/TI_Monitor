"""
Escolhe os trechos do artifact que viram vídeos curtos (9:16).

1. Se o artifact declarar window.META.shorts = [{titulo, cenas: [i, j, ...], chapeu?}], usa isso.
2. Senão, o Claude lê a narração das cenas e escolhe de 1 a 3 sequências (35 a 60 s) com gancho forte.
   Ele também pode sugerir uma frase de gancho falada nova para abrir o short (é narrada e entra antes
   da primeira cena), que é a única "alteração" de texto que a edição faz.
"""
from __future__ import annotations

import json

import anthropic

from ..config import ESFORCO_ROTEIRO, MODELO_ROTEIRO, PROMPTS

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["shorts"], "properties": {"shorts": {
    "type": "array", "items": {"type": "object", "additionalProperties": False,
                               "required": ["titulo", "chapeu", "cenas", "gancho_falado", "legenda_post", "hashtags", "motivo"],
                               "properties": {"titulo": {"type": "string"}, "chapeu": {"type": "string"},
                                              "cenas": {"type": "array", "items": {"type": "integer"}},
                                              "gancho_falado": {"type": "string"}, "legenda_post": {"type": "string"},
                                              "hashtags": {"type": "array", "items": {"type": "string"}},
                                              "motivo": {"type": "string"}}}}}}


def escolher(meta: dict, cenas: list[dict], duracoes: list[float]) -> list[dict]:
    if meta.get("shorts"):
        return [{"titulo": s.get("titulo", meta.get("titulo", "")), "chapeu": s.get("chapeu", ""),
                 "cenas": s["cenas"], "gancho_falado": s.get("gancho_falado", "")} for s in meta["shorts"]]
    lista = [{"indice": c["indice"], "segundos": round(d, 1), "narracao": c["narracao"]} for c, d in zip(cenas, duracoes)]
    instr = (PROMPTS / "shorts.md").read_text(encoding="utf-8").replace("{{CENAS}}", json.dumps(lista, ensure_ascii=False, indent=1)) \
        .replace("{{TITULO}}", meta.get("titulo", ""))
    cliente = anthropic.Anthropic()
    with cliente.beta.messages.stream(
        model=MODELO_ROTEIRO, max_tokens=16000, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        system=(PROMPTS / "dna_do_canal.md").read_text(encoding="utf-8"),
        output_config={"effort": ESFORCO_ROTEIRO, "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": instr}],
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError(f"Escolha de shorts recusada: {msg.stop_details}")
    dados = json.loads(next(b.text for b in msg.content if b.type == "text"))
    validos = []
    for s in dados["shorts"]:
        s["cenas"] = [i for i in s["cenas"] if 0 <= i < len(cenas)]
        if s["cenas"]:
            validos.append(s)
    return validos


def automatico(meta: dict, cenas: list[dict], duracoes: list[float], maximo: int = 3,
               alvo: tuple[float, float] = (28.0, 55.0)) -> list[dict]:
    """Sem a API do Claude: um corte por parte do vídeo, com cenas seguidas que somam 28 a 55 s.
    Começa na cena mais forte do trecho (a que tem mais palavras de destaque e frase curta = gancho)."""
    partes: dict = {}
    for i, c in enumerate(cenas):
        partes.setdefault(c.get("capitulo") or "", []).append(i)
    candidatos = []
    for nome, idx in partes.items():
        idx = idx[1:] if len(idx) > 3 else idx           # pula o cartão de abertura da parte
        melhor = None
        for a in range(len(idx)):
            soma, fim = 0.0, a
            while fim < len(idx) and idx[fim] == idx[a] + (fim - a) and soma + duracoes[idx[fim]] <= alvo[1]:
                soma += duracoes[idx[fim]]
                fim += 1
            if soma < alvo[0]:
                continue
            c0 = cenas[idx[a]]
            gancho = len(c0.get("destaques") or []) * 2 + (3 if len(c0["narracao"].split()) <= 12 else 0) \
                + (2 if "?" in c0["narracao"] else 0)
            if melhor is None or gancho > melhor[0]:
                melhor = (gancho, idx[a:fim])
        if melhor:
            candidatos.append({"titulo": (str(nome).split("·")[-1].strip() or meta.get("titulo", ""))[:60],
                               "chapeu": meta.get("titulo", "")[:40], "cenas": melhor[1], "gancho_falado": "",
                               "nota": melhor[0]})
    candidatos.sort(key=lambda s: -s["nota"])
    return candidatos[:maximo]
