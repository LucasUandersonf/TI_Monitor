"""
Efeito sonoro pedido em texto (campo "sfx" do artifact ou "efeito_sonoro" da ficha), por exemplo:
  'bipe antes de "Com todo respeito"'   ->  bip 0,18 s antes da palavra "Com"
  'moeda em "dinheiro"'                 ->  moeda no instante da palavra
  'impacto'                             ->  impacto no começo da fala
"""
from __future__ import annotations

import re

SFX_PALAVRAS = [  # campo "efeito_sonoro" da ficha -> categoria
    (r"bip|censur", "bip"), (r"caixa registradora|cha.?ching", "caixa_registradora"), (r"moeda", "moeda"),
    (r"whoosh|swoosh|vento|desliz", "whoosh"), (r"impacto|boom|pancada|batida", "impacto"), (r"\bpop\b|estalo", "pop"),
    (r"ding|sino|plim", "ding"), (r"notifica", "notificacao"), (r"papel|rasg", "papel"), (r"tique|tic.?tac|rel[oó]gio", "tick"),
    (r"baque|queda|tombo", "baque"), (r"caneta|risc", "risco_caneta"), (r"drone|tens[aã]o", "drone"),
]


def do_texto(texto: str | None, ws: list[dict], fala_dur: float, respiro: float) -> list[dict]:
    if not texto:
        return []
    tipo = next((cat for pad, cat in SFX_PALAVRAS if re.search(pad, texto, re.I)), None)
    if not tipo:
        return []
    em = respiro + 0.1
    m = re.search(r"(antes de|depois de|ap[oó]s|em|no|na|junto com)\s*[\"“'«]([^\"”'»]+)[\"”'»]", texto, re.I)
    if m:
        alvo = m.group(2).split()
        pos = None
        for i in range(len(ws) - len(alvo) + 1):
            if all(re.sub(r"[^\wÀ-ú]", "", ws[i + k]["w"].lower()) == re.sub(r"[^\wÀ-ú]", "", a.lower()) for k, a in enumerate(alvo)):
                pos = i
                break
        if pos is not None:
            if m.group(1).lower().startswith("antes"):
                em = ws[pos]["ini"] - 0.18
            elif m.group(1).lower().startswith(("depois", "ap")):
                em = ws[pos + len(alvo) - 1]["fim"] + 0.05
            else:
                em = ws[pos]["ini"]
    return [{"tipo": tipo, "em": round(max(0.0, em), 3), "origem": "ficha"}]
