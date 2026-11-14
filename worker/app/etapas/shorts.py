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
