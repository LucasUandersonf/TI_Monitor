"""Chama o renderer Node (Playwright) em paralelo, dividindo as cenas em lotes."""
from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..config import FPS, MOTION_BLUR, RENDER_PARALELO, RENDERER, RESOLUCAO


def _rodar(cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    """Roda o renderer e, se falhar, devolve o erro dele (não só o código de saída)."""
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        detalhe = (r.stderr or r.stdout or "").strip().splitlines()
        raise RuntimeError("renderer falhou: " + " | ".join(detalhe[-4:])[:800])
    return r


def extrair(artifact: Path) -> dict:
    out = _rodar(["node", str(RENDERER), "--artifact", str(artifact), "--extrair"], timeout=300)
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        raise RuntimeError("o artifact não segue o contrato (SCENES / go / #stage): " + (out.stderr or "")[-400:])


def extrair_partes(artifacts: list[Path]) -> dict:
    """Junta as cenas de um ou mais artifacts (parte 1, parte 2...) numa lista só."""
    cenas, meta = [], {}
    for k, art in enumerate(artifacts):
        ext = extrair(art)
        if k == 0:
            meta = ext["meta"]
            # índices de META.shorts só valem para artifact único
            if len(artifacts) > 1:
                meta.pop("shorts", None)
        for c in ext["cenas"]:
            c["parte"] = k
            cenas.append(c)
    return {"meta": meta, "cenas": cenas}


def renderizar(artifacts: list[Path], plano: dict, pasta: Path, preset: str = "medium") -> list[Path]:
    """Renderiza cada parte com o seu artifact; os clipes saem numerados pela posição global (cena_000.mp4...)."""
    pasta.mkdir(parents=True, exist_ok=True)
    tarefas = []
    for k, art in enumerate(artifacts):
        sub = [c for c in plano["cenas"] if c.get("parte", 0) == k]
        if not sub:
            continue
        arq_plano = pasta / f"plano_parte{k}.json"
        arq_plano.write_text(json.dumps({**plano, "cenas": sub}, ensure_ascii=False))
        n = len(sub)
        lotes = max(1, min(RENDER_PARALELO, n))
        passo = -(-n // lotes)
        tarefas += [(art, arq_plano, de, min(n, de + passo)) for de in range(0, n, passo)]

    def lote(t):
        art, arq_plano, de, ate = t
        _rodar(["node", str(RENDERER), "--artifact", str(art), "--plano", str(arq_plano), "--pasta", str(pasta),
                "--de", str(de), "--ate", str(ate), "--fps", str(FPS), "--blur", str(MOTION_BLUR), "--escala", f"{RESOLUCAO / 1080:.4f}", "--preset", preset])

    with ThreadPoolExecutor(max(1, min(RENDER_PARALELO, len(tarefas)))) as ex:
        list(ex.map(lote, tarefas))
    return [pasta / f"cena_{i:03d}.mp4" for i in range(len(plano["cenas"]))]
