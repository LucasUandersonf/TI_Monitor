"""
Mapas a partir do Natural Earth (1:50m, map units, domínio público), com nomes em português.

O artifact pede um mapa de dois jeitos:
  - marcador no SVG:  <rect data-mapa="BRA,PRT" data-rota="PRT>BRA" data-rotulos="1" x=.. y=.. width=.. height=../>
  - campo na cena:    mapa: { destaques: ['BRA','PRT'], rota: [['PRT','BRA']], rotulos: true, cor: '#F0508C' }
O mapa é desenhado no estilo da marca (terra grafite, destaques magenta/teal/lima, rota em arco que se
desenha com a classe .draw do próprio artifact, pinos com .pop e rótulos com .fade).

  preparar(geojson, saida)  converte o GeoJSON original num JSON compacto (roda no build do Docker)
  svg(spec)                 devolve {"svg": "<g>...</g>", "viewBox": "x y w h"}
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from ..config import MODELOS

ARQ = MODELOS / "natural_earth" / "mundo_pt.json"
CORES = ["#F0508C", "#19B9C2", "#D7FF3A", "#6B3FB0", "#FF5A4E"]


def _proj(lon: float, lat: float) -> tuple[float, float]:
    """Projeção Natural Earth I (Šavrič et al.), em unidades arbitrárias; escalada depois."""
    l, p = math.radians(lon), math.radians(lat)
    p2, p4 = p * p, p ** 4
    x = l * (0.8707 - 0.131979 * p2 + p4 * (-0.013791 + p4 * (0.003971 * p2 - 0.001529 * p4)))
    y = p * (1.007226 + p2 * (0.015085 + p4 * (-0.044475 + 0.028874 * p2 - 0.005916 * p4)))
    return x * 1000, -y * 1000


def _simplificar(anel: list, tol: float) -> list:
    """Douglas-Peucker simples sobre pontos já projetados."""
    if len(anel) < 5:
        return anel

    def dp(pts):
        if len(pts) < 3:
            return pts
        (x1, y1), (x2, y2) = pts[0], pts[-1]
        dx, dy = x2 - x1, y2 - y1
        n = math.hypot(dx, dy) or 1e-9
        dmax, idx = 0, 0
        for i in range(1, len(pts) - 1):
            d = abs(dy * pts[i][0] - dx * pts[i][1] + x2 * y1 - y2 * x1) / n
            if d > dmax:
                dmax, idx = d, i
        if dmax > tol:
            return dp(pts[: idx + 1])[:-1] + dp(pts[idx:])
        return [pts[0], pts[-1]]
    # anel fechado: simplifica as duas metades separadamente (início = fim quebraria a reta de referência)
    meio = len(anel) // 2
    return dp(anel[: meio + 1])[:-1] + dp(anel[meio:])


def preparar(geojson: Path, saida: Path = ARQ, tol: float = 0.6):
    d = json.loads(Path(geojson).read_text(encoding="utf-8"))
    paises = []
    for f in d["features"]:
        pr, g = f["properties"], f["geometry"]
        polis = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        aneis = []
        for poli in polis:
            anel = [tuple(round(v, 1) for v in _proj(lon, lat)) for lon, lat in poli[0]]
            anel = _simplificar(anel, tol)
            if len(anel) >= 4:
                aneis.append(anel)
        paises.append({"a3": pr.get("ADM0_A3") or pr.get("ISO_A3"), "iso": pr.get("ISO_A3"),
                       "nome": pr.get("NAME_PT") or pr.get("NAME"), "en": pr.get("NAME"),
                       "rot": [round(v, 1) for v in _proj(pr.get("LABEL_X", 0), pr.get("LABEL_Y", 0))], "aneis": aneis})
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(paises, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return saida


def _area(anel: list) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(anel, anel[1:] + anel[:1]))) / 2


@lru_cache(maxsize=1)
def _dados() -> dict:
    unidades = json.loads(ARQ.read_text(encoding="utf-8"))
    # junta as unidades de um mesmo país (ex.: Portugal continental + Madeira + Açores);
    # nome e posição do rótulo vêm da maior unidade
    por_pais: dict[str, dict] = {}
    for u in unidades:
        area = sum(_area(a) for a in u["aneis"])
        p = por_pais.get(u["a3"])
        if p is None:
            por_pais[u["a3"]] = {**u, "aneis": list(u["aneis"]), "_area": area}
            continue
        p["aneis"] += u["aneis"]
        if area > p["_area"]:
            p.update({"nome": u["nome"], "en": u["en"], "rot": u["rot"], "iso": u["iso"] if u["iso"] != "-99" else p["iso"], "_area": area})
    lista = list(por_pais.values())
    idx = {}
    for p in lista:
        for k in {p["a3"], p["iso"], (p["nome"] or "").upper(), (p["en"] or "").upper()}:
            if k and k != "-99":
                idx.setdefault(k.upper(), p)
    return {"lista": lista, "idx": idx}


def _pais(cod: str):
    return _dados()["idx"].get(cod.strip().upper())


def disponivel() -> bool:
    return ARQ.exists()


def svg(spec: dict, caixa: dict | None = None) -> dict:
    """spec: destaques, rota [[de, para]], rotulos, cor. caixa: {w,h} do marcador para acertar a proporção."""
    D = _dados()
    destaques = [c for c in spec.get("destaques", []) if _pais(c)]
    rotas = [r for r in spec.get("rota", []) if len(r) == 2 and _pais(r[0]) and _pais(r[1])]
    foco = set(destaques) | {c for r in rotas for c in r}
    # enquadramento: os países em foco (ou o mundo), com margem, na proporção da caixa
    pts = [pt for c in foco for anel in _pais(c)["aneis"] for pt in anel] if foco else \
        [pt for p in D["lista"] for anel in p["aneis"] for pt in anel]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, h = (x1 - x0) or 1, (y1 - y0) or 1
    mx, my = w * 0.35 + 40, h * 0.35 + 40
    x0, x1, y0, y1 = x0 - mx, x1 + mx, y0 - my, y1 + my
    alvo = (caixa or {"w": 1920, "h": 1080})
    razao = alvo["w"] / alvo["h"]
    w, h = x1 - x0, y1 - y0
    if w / h < razao:
        extra = h * razao - w
        x0, x1 = x0 - extra / 2, x1 + extra / 2
    else:
        extra = w / razao - h
        y0, y1 = y0 - extra / 2, y1 + extra / 2
    w, h = x1 - x0, y1 - y0
    traco = w / 900

    cor_de = {c.upper(): spec.get("cor") or CORES[k % len(CORES)] for k, c in enumerate(destaques)}
    partes = [f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="#0B0B0F"/>']
    for p in D["lista"]:
        cor = next((cor_de[k] for k in (p["a3"], p["iso"]) if k and k.upper() in cor_de), None)
        d = "".join("M" + "L".join(f"{x},{y}" for x, y in anel) + "Z" for anel in p["aneis"])
        if cor:
            partes.append(f'<path class="fade" d="{d}" fill="{cor}" stroke="#0B0B0F" stroke-width="{traco:.2f}"/>')
        else:
            partes.append(f'<path d="{d}" fill="#22202E" stroke="#0B0B0F" stroke-width="{traco:.2f}"/>')
    atraso = 0.6
    for a, b in rotas:
        (ax, ay), (bx, by) = _pais(a)["rot"], _pais(b)["rot"]
        cx, cy = (ax + bx) / 2, min(ay, by) - math.hypot(bx - ax, by - ay) * 0.35
        partes.append(f'<path class="draw" pathLength="1" style="--d:{atraso}s;--t:1.4s" d="M{ax},{ay} Q{cx},{cy} {bx},{by}" '
                      f'fill="none" stroke="#D7FF3A" stroke-width="{traco * 4:.2f}" stroke-linecap="round" stroke-dasharray="1"/>')
        partes.append(f'<circle class="pop" style="--d:{atraso + 1.3}s" cx="{bx}" cy="{by}" r="{traco * 9:.2f}" fill="#D7FF3A"/>')
        partes.append(f'<circle class="pop" style="--d:{atraso}s" cx="{ax}" cy="{ay}" r="{traco * 6:.2f}" fill="#fff"/>')
        atraso += 1.6
    if spec.get("rotulos", True):
        for k, c in enumerate(sorted(foco)):
            p = _pais(c)
            x, y = p["rot"]
            partes.append(f'<text class="fade" style="--d:{0.9 + k * 0.3}s" x="{x}" y="{y - traco * 14}" text-anchor="middle" '
                          f'font-family="Barlow Condensed, Arial Narrow, sans-serif" font-weight="700" font-size="{traco * 30:.1f}" '
                          f'letter-spacing="{traco * 2:.1f}" fill="#fff" stroke="#0B0B0F" stroke-width="{traco * 5:.1f}" '
                          f'paint-order="stroke">{(p["nome"] or "").upper()}</text>')
    return {"svg": "".join(partes), "viewBox": f"{x0:.1f} {y0:.1f} {w:.1f} {h:.1f}"}


def de_marcador(dados: dict) -> dict:
    """Converte atributos data-* do marcador em spec."""
    return {"destaques": [c for c in (dados.get("mapa") or "").split(",") if c.strip()],
            "rota": [r.split(">") for r in (dados.get("rota") or "").split(";") if ">" in r],
            "rotulos": dados.get("rotulos", "1") != "0", "cor": dados.get("cor")}
