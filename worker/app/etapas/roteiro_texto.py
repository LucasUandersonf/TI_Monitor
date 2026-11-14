"""
Roteiro que vem da planilha (coluna "roteiro") aplicado às cenas do artifact.

  narracao_vem_de = "auto"      (padrão) se o artifact já tem narração em 80 % das cenas, ela vale
                                 (está sincronizada com o desenho); o roteiro só preenche cenas vazias
                  = "roteiro"   a narração de todas as cenas vem do roteiro
                  = "artifact"  ignora o roteiro na narração (ele ainda dá o título)

Como o roteiro é dividido entre as cenas:
  - com marcadores [CENA] (formato do roteiro gerado pela pauta): um bloco por cena, na ordem
  - sem marcadores: frases inteiras distribuídas pelas cenas, na proporção da duração de cada uma
Linhas de título (# ...), capítulos (## ...) e notas (> visual: ...) não são narradas.
"""
from __future__ import annotations

import re


def _limpar(txt: str) -> str:
    linhas = []
    for l in txt.splitlines():
        s = l.strip()
        if not s or s.startswith(("#", ">", "---")) or re.fullmatch(r"\(?\s*cor:.*\)?", s, re.I):
            continue
        s = re.sub(r"^\[?(cena|narra[cç][aã]o|narrador)\]?\s*[:\-–]?\s*", "", s, flags=re.I)
        linhas.append(s)
    return re.sub(r"\s+", " ", " ".join(linhas)).strip()


def titulo(roteiro: str) -> str | None:
    for l in roteiro.splitlines():
        s = l.strip()
        if s.startswith("# "):
            return s[2:].strip()
    texto = _limpar(roteiro)
    if not texto:
        return None
    primeira = re.split(r"(?<=[.!?…])\s+", texto)[0]
    return primeira[:80].rstrip(".!?… ") if primeira else None


def blocos(roteiro: str, n: int, pesos: list[float]) -> list[str]:
    if re.search(r"\[CENA\]", roteiro, re.I):
        partes = [_limpar(p) for p in re.split(r"\[CENA\]", roteiro, flags=re.I)[1:]]
        partes = [p for p in partes if p]
        if len(partes) == n:
            return partes
        roteiro_limpo = " ".join(partes)
    else:
        roteiro_limpo = _limpar(roteiro)
    frases = [f for f in re.split(r"(?<=[.!?…])\s+", roteiro_limpo) if f.strip()]
    if not frases or n == 0:
        return [""] * n
    # distribui frases inteiras, NA ORDEM: cada cena recebe palavras na proporção do seu peso,
    # nenhuma cena fica vazia enquanto houver frases, e nenhuma frase troca de lugar
    pal = [len(f.split()) for f in frases]
    total_pal = sum(pal)
    soma = sum(pesos) or n
    alvos, acc = [], 0.0
    for p in pesos:
        acc += p / soma * total_pal
        alvos.append(acc)
    out, k, contadas = [[] for _ in range(n)], 0, 0
    for i, f in enumerate(frases):
        restantes = len(frases) - i                     # frases que ainda faltam, contando esta
        cenas_depois = n - 1 - k                         # cenas depois da atual
        if out[k] and k < n - 1 and (restantes <= cenas_depois or contadas + pal[i] / 2 > alvos[k]):
            k += 1
        out[k].append(f)
        contadas += pal[i]
    return [" ".join(x) for x in out]


def aplicar(cenas: list[dict], roteiro: str | None, modo: str = "auto") -> tuple[str, list[str]]:
    """Muda as narrações das cenas no lugar. Devolve (modo usado, avisos)."""
    if not roteiro or not roteiro.strip():
        vazias = [c["indice"] for c in cenas if not c["narracao"].strip()]
        return "artifact", ([f"cenas sem narração e sem roteiro: {vazias}"] if vazias else [])
    com_texto = sum(1 for c in cenas if c["narracao"].strip())
    if modo == "auto":
        modo = "artifact" if com_texto >= 0.8 * len(cenas) else "roteiro"
    avisos = []
    if modo == "roteiro":
        novos = blocos(roteiro, len(cenas), [float(c.get("dur") or 7) for c in cenas])
        for c, t in zip(cenas, novos):
            if t:
                c["narracao_original"] = c["narracao"]
                c["narracao"] = t
                # destaques do artifact que sumiram do texto novo não servem mais
                c["destaques"] = [h for h in (c.get("destaques") or []) if h.lower().strip(".,!?…") in t.lower()]
        avisos.append("narração tirada do roteiro da planilha")
    else:
        vazias = [c for c in cenas if not c["narracao"].strip()]
        if vazias:
            novos = blocos(roteiro, len(vazias), [float(c.get("dur") or 7) for c in vazias])
            for c, t in zip(vazias, novos):
                c["narracao"] = t
            avisos.append(f"{len(vazias)} cena(s) sem narração no artifact receberam texto do roteiro")
    return modo, avisos
