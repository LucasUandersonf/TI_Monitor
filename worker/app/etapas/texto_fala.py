"""
Prepara o texto para a voz falar bem em português (a legenda continua com o texto original).

  - números por extenso: 2023 -> "dois mil e vinte e três", 1,5 -> "um vírgula cinco", 90% -> "noventa por cento"
  - dinheiro: R$ 10 -> "dez reais", R$ 2,50 -> "dois reais e cinquenta centavos"
  - ordinais: 1º -> "primeiro", 3ª -> "terceira"
  - "90 MI" / "13 MIL" / "2 BI" -> "noventa milhões" etc.
  - dicionário de pronúncia editável: biblioteca/voz/pronuncia.txt, uma regra por linha:  GTA = gê tê á
"""
from __future__ import annotations

import re
from pathlib import Path

from ..config import BIBLIOTECA

UNI = ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez", "onze", "doze",
       "treze", "quatorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"]
DEZ = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
CEN = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos", "setecentos",
       "oitocentos", "novecentos"]
ORD = {1: "primeiro", 2: "segundo", 3: "terceiro", 4: "quarto", 5: "quinto", 6: "sexto", 7: "sétimo",
       8: "oitavo", 9: "nono", 10: "décimo", 20: "vigésimo", 30: "trigésimo", 100: "centésimo"}


def _ate_mil(n: int) -> str:
    if n < 20:
        return UNI[n]
    if n < 100:
        d, u = divmod(n, 10)
        return DEZ[d] + (f" e {UNI[u]}" if u else "")
    if n == 100:
        return "cem"
    c, r = divmod(n, 100)
    return CEN[c] + (f" e {_ate_mil(r)}" if r else "")


def extenso(n: int) -> str:
    if n < 0:
        return "menos " + extenso(-n)
    if n < 1000:
        return _ate_mil(n)
    partes = []
    for valor, sing, plur in ((10 ** 12, "trilhão", "trilhões"), (10 ** 9, "bilhão", "bilhões"),
                              (10 ** 6, "milhão", "milhões"), (1000, "mil", "mil")):
        q, n = divmod(n, valor)
        if q:
            if valor == 1000:
                partes.append("mil" if q == 1 else f"{extenso(q)} mil")
            else:
                partes.append(f"{extenso(q)} {sing if q == 1 else plur}")
    if n:
        # "e" antes do último grupo quando ele é < 100 ou centena redonda
        partes.append(("e " if n < 100 or n % 100 == 0 else "") + _ate_mil(n))
    return " ".join(partes).replace("  ", " ")


def _ordinal(n: int, fem: bool) -> str:
    if n in ORD:
        p = ORD[n]
    elif n < 100:
        d, u = divmod(n, 10)
        p = f"{ORD[d * 10]} {ORD[u]}"
    else:
        p = extenso(n)
    return p[:-1] + "a" if fem and p.endswith("o") else p


def _numero(s: str) -> str:
    s = s.replace(".", "")
    if "," in s:
        i, d = s.split(",", 1)
        return f"{extenso(int(i or 0))} vírgula " + (" ".join(UNI[int(c)] for c in d) if d.startswith("0") else extenso(int(d)))
    return extenso(int(s))


MULT = {"mi": "milhões", "mil": "mil", "bi": "bilhões", "tri": "trilhões", "k": "mil"}


def _regras_pronuncia() -> list[tuple[re.Pattern, str]]:
    arq = BIBLIOTECA / "voz" / "pronuncia.txt"
    regras = []
    if arq.exists():
        for l in arq.read_text(encoding="utf-8").splitlines():
            if "=" in l and not l.strip().startswith("#"):
                a, b = l.split("=", 1)
                if a.strip():
                    regras.append((re.compile(rf"\b{re.escape(a.strip())}\b", re.I), b.strip()))
    return regras


def preparar(texto: str) -> str:
    t = texto
    for padrao, troca in _regras_pronuncia():
        t = padrao.sub(troca, t)
    # dinheiro
    def reais(m):
        i, c = m.group(1).replace(".", ""), m.group(2)
        txt = f"{extenso(int(i))} {'real' if int(i) == 1 else 'reais'}"
        if c and int(c):
            txt += f" e {extenso(int(c))} centavos"
        return txt
    t = re.sub(r"R\$\s?(\d[\d.]*)(?:,(\d{1,2}))?", reais, t)
    # 90 MI, 2,6 BI, 13 MIL
    t = re.sub(r"(\d[\d.,]*)\s?(mi|bi|tri|mil|k)\b\+?", lambda m: f"{_numero(m.group(1))} {MULT[m.group(2).lower()]}", t, flags=re.I)
    # porcentagem
    t = re.sub(r"(\d[\d.,]*)\s?%", lambda m: f"{_numero(m.group(1))} por cento", t)
    # ordinais
    t = re.sub(r"\b(\d+)\s?([ºª])", lambda m: _ordinal(int(m.group(1)), m.group(2) == "ª"), t)
    # "1 em 3", horas simples 3h -> "três horas"
    t = re.sub(r"\b(\d{1,2})h(\d{2})?\b", lambda m: f"{extenso(int(m.group(1)))} {'hora' if m.group(1) == '1' else 'horas'}"
               + (f" e {extenso(int(m.group(2)))}" if m.group(2) else ""), t)
    # demais números
    t = re.sub(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?", lambda m: _numero(m.group(0)), t)
    # símbolos comuns
    t = t.replace("&", " e ").replace("+", " mais ").replace("=", " igual a ").replace("≠", " diferente de ")
    t = re.sub(r"\s+", " ", t).strip()
    return t


if __name__ == "__main__":
    for x in ["Em 2023, o trailer passou de 90 MI de views.", "Custa R$ 2,50 e cresceu 12,5%.", "O 1º lugar e a 3ª vez.",
              "Entre o 5 e o 6 se passaram 13 anos.", "1.500 pessoas às 3h30.", "100 anos, 101 dias, 1000 vezes, 21000, 1000000"]:
        print(x, "->", preparar(x))
