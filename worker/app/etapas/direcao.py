"""
JSON do "diretor": decisões de edição ancoradas em PALAVRAS da narração, não em segundos.
Gerado numa conversa com o Claude (prompt em docs/PROMPT_DIRETOR.md) e colado na coluna "direcao" da planilha.

{
  "cenas": [
    {"cena": 3,
     "entradas": [{"elemento": "BOLETO", "palavra": "boleto"},      # texto visível do elemento...
                  {"elemento": 2, "palavra": "juros"}],             # ...ou a ordem em que ele aparece (1, 2, 3...)
     "enfase": ["nunca"],                                           # punch-in de câmera na palavra
     "sfx": [{"tipo": "bipe", "palavra": "respeito"}],
     "corte": "seco"}                                               # seco | suave | forte (troca para a cena seguinte)
  ]
}
"""
from __future__ import annotations

import json
import re


def ler(bruto) -> dict | None:
    if not bruto:
        return None
    if isinstance(bruto, dict):
        return bruto
    txt = str(bruto).strip()
    txt = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.M).strip()  # colado com a moldura de código
    if not txt.startswith("{") and "{" in txt:
        txt = txt[txt.index("{"): txt.rindex("}") + 1]
    return json.loads(txt)


def aplicar(cenas: list[dict], bruto) -> list[str]:
    avisos: list[str] = []
    try:
        d = ler(bruto)
    except Exception as e:
        return [f"JSON do diretor ignorado (não é um JSON válido: {str(e)[:80]})"]
    if not d:
        return avisos
    for item in d.get("cenas") or []:
        try:
            i = int(item.get("cena")) - 1
        except (TypeError, ValueError):
            continue
        if not 0 <= i < len(cenas):
            avisos.append(f"diretor: cena {item.get('cena')} não existe no artifact ({len(cenas)} cenas)")
            continue
        c = cenas[i]
        if item.get("entradas"):
            c["direcao_entradas"] = [e for e in item["entradas"] if isinstance(e, dict)]
        for p in item.get("enfase") or []:
            c["destaques"] = list(c.get("destaques") or []) + [p]
        extra = [{"tipo": s["tipo"], "em": s.get("palavra") or s.get("em", 0)} for s in item.get("sfx") or []
                 if isinstance(s, dict) and s.get("tipo")]
        if extra:
            atual = c.get("sfx")
            c["sfx"] = (atual if isinstance(atual, list) else []) + extra
            if isinstance(atual, str):  # efeito em texto do artifact continua valendo
                c["sfx_texto"] = atual
        if item.get("corte"):
            c["direcao_corte"] = str(item["corte"])
    return avisos
