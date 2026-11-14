"""
Pauta (antes do artifact): tendências -> 3 candidatos -> roteiro em texto para a conversa de artifacts.
A edição do vídeo não depende desta parte; ela só alimenta a conversa que gera o artifact.
"""
from __future__ import annotations

import json

import anthropic

from .config import ESFORCO_ROTEIRO, MODELO_ROTEIRO, PROMPTS

S, I = {"type": "string"}, {"type": "integer"}


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


SCHEMA_CANDIDATOS = _obj({"candidatos": {"type": "array", "items": _obj({
    "tema": S, "angulo": {"type": "string", "enum": ["psicologia", "e_se", "curiosidade", "filosofia", "historia"]},
    "titulo_provisorio": S, "gancho": S, "por_que_agora": S, "ideia_universal": S,
    "origem": {"type": "string", "enum": ["brasil", "gringa", "ambos"]}, "nota_retencao": I, "justificativa": S})}})
SCHEMA_ROTEIRO = _obj({"titulo": S, "titulos_alternativos": {"type": "array", "items": S}, "tese": S,
                       "gancho_vertical": S, "palavras": I, "roteiro_markdown": S})


def _prompt(nome: str, **v) -> str:
    t = (PROMPTS / nome).read_text(encoding="utf-8")
    for k, x in v.items():
        t = t.replace("{{" + k + "}}", x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, indent=1))
    return t


def _chamar(instrucao: str, schema: dict, esforco: str) -> dict:
    cliente = anthropic.Anthropic()
    with cliente.beta.messages.stream(
        model=MODELO_ROTEIRO, max_tokens=64000, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        system=[{"type": "text", "text": _prompt("dna_do_canal.md"), "cache_control": {"type": "ephemeral"}}],
        output_config={"effort": esforco, "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": instrucao}],
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError(f"Pedido recusado pelo modelo: {msg.stop_details}")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("Resposta cortada por max_tokens.")
    return json.loads(next(b.text for b in msg.content if b.type == "text"))


def candidatos(tendencias: list[dict], ja_feitos: list[str]) -> dict:
    enxuto = [{"termo": t["termo"], "fonte": t["fonte"], "regiao": t["regiao"], "score": round(t["score"], 3),
               "cruzamento": t.get("cruzamento"),
               "extra": {k: v for k, v in t.get("extra", {}).items() if k in ("noticias", "canal", "sub", "views")}}
              for t in tendencias[:60]]
    return _chamar(_prompt("escolher_tema.md", TENDENCIAS=enxuto, JA_FEITOS=ja_feitos or ["(nenhum)"]),
                   SCHEMA_CANDIDATOS, "medium")


def roteiro(tema: dict) -> dict:
    return _chamar(_prompt("roteiro_texto.md", TEMA=tema), SCHEMA_ROTEIRO, ESFORCO_ROTEIRO)
