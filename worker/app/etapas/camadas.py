"""
Camadas extras que o ARTIFACT pede (nada entra se ele não pedir).

  mapa     marcador [data-mapa] ou campo `mapa` da cena      -> Natural Earth (mapas.py)
  arte     marcador [data-arte="prompt"]                      -> FLUX.1 schnell (GPU) -> vtracer -> SVG
           marcador [data-arte-arquivo="nome.png"]            -> imagem sua em biblioteca/arte -> vtracer -> SVG
  desenho  marcador [data-desenho="nome"] data-movimento=..   -> AnimatedDrawings anima o desenho de biblioteca/desenhos
  lottie   campo `lottie` da cena, ou automático nos destaques -> lottie-web no render; rlottie valida e mede o arquivo

Cada função devolve camadas no formato que o renderer entende:
  {tipo: 'svg', alvo, svg, viewBox} · {tipo: 'imagem', alvo, href} · {tipo: 'sequencia', alvo, quadros, fps}
"""
from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
from functools import lru_cache
from pathlib import Path

from ..config import ANIMATED_DRAWINGS_CMD, BIBLIOTECA, FLUX_MODELO
from . import mapas

ESTILO_ARTE = ("flat duotone vector illustration, bold simple shapes, magenta #F0508C and teal #19B9C2 on near-black "
               "background, subtle grain, editorial explainer style, no text, no letters")
MOVIMENTOS = {"acenar": "wave_hello", "dancar": "dab", "pular": "jumping", "zumbi": "zombie", "danca": "jesse_dance"}


def _h(*partes) -> str:
    return hashlib.md5("|".join(map(str, partes)).encode()).hexdigest()[:12]


# ---------------------------------------------------------------- arte
@lru_cache(maxsize=1)
def _flux():
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("FLUX precisa de GPU")
    from diffusers import FluxPipeline
    pipe = FluxPipeline.from_pretrained(FLUX_MODELO, torch_dtype=torch.bfloat16)
    pipe.enable_model_cpu_offload()
    return pipe


def _vetorizar(png: Path, svg: Path) -> Path:
    import vtracer
    vtracer.convert_image_to_svg_py(str(png), str(svg), colormode="color", hierarchical="stacked", mode="spline",
                                    filter_speckle=6, color_precision=6, layer_difference=24, corner_threshold=60,
                                    length_threshold=4.0, max_iterations=10, splice_threshold=45, path_precision=2)
    return svg


def arte(dados: dict, caixa: dict, pasta: Path) -> dict | None:
    """Gera ou pega a imagem, vetoriza com vtracer (fica com cara de ilustração chapada) e devolve o arquivo SVG."""
    pasta.mkdir(parents=True, exist_ok=True)
    if dados.get("arteArquivo"):
        origem = BIBLIOTECA / "arte" / dados["arteArquivo"]
        if not origem.exists():
            return None
        png = origem
        chave = _h(origem, origem.stat().st_mtime)
    else:
        prompt = dados.get("arte") or ""
        if not prompt:
            return None
        chave = _h(prompt, caixa.get("w"), caixa.get("h"))
        png = pasta / f"arte_{chave}.png"
        if not png.exists():
            try:
                pipe = _flux()
            except Exception:
                return None
            w = int(round(min(1344, max(512, caixa.get("w", 1024))) / 16) * 16)
            h = int(round(min(1344, max(512, caixa.get("h", 768))) / 16) * 16)
            img = pipe(f"{prompt}. {ESTILO_ARTE}", num_inference_steps=4, guidance_scale=0.0, width=w, height=h,
                       max_sequence_length=256).images[0]
            img.save(png)
    if dados.get("vetorizar", "1") == "0":
        return {"href": png.resolve().as_uri()}
    svg = pasta / f"arte_{chave}.svg"
    if not svg.exists():
        _vetorizar(png, svg)
    return {"href": svg.resolve().as_uri()}


# ---------------------------------------------------------------- desenho animado
def desenho(dados: dict, pasta: Path) -> dict | None:
    """AnimatedDrawings: rig automático de um desenho (biblioteca/desenhos/<nome>.png) + movimento -> quadros PNG."""
    if not ANIMATED_DRAWINGS_CMD:
        return None
    img = BIBLIOTECA / "desenhos" / f"{dados.get('desenho')}.png"
    if not img.exists():
        return None
    mov = MOVIMENTOS.get(dados.get("movimento", "acenar"), dados.get("movimento", "wave_hello"))
    saida = pasta / f"desenho_{_h(img, mov)}"
    gif = saida / "video.gif"
    if not gif.exists():
        saida.mkdir(parents=True, exist_ok=True)
        cmd = ANIMATED_DRAWINGS_CMD.format(imagem=shlex.quote(str(img)), saida=shlex.quote(str(saida)), movimento=mov)
        if subprocess.run(cmd, shell=True).returncode != 0 or not gif.exists():
            return None
    quadros_dir = saida / "quadros"
    if not quadros_dir.exists():
        quadros_dir.mkdir()
        subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(gif), str(quadros_dir / "q_%04d.png")], check=True)
    fps = 24.0
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                            "-of", "csv=p=0", str(gif)], capture_output=True, text=True).stdout.strip()
        n, d = r.split("/")
        fps = float(n) / float(d)
    except Exception:
        pass
    return {"quadros": [q.resolve().as_uri() for q in sorted(quadros_dir.glob("q_*.png"))], "fps": fps}


# ---------------------------------------------------------------- lottie
@lru_cache(maxsize=64)
def lottie_info(arquivo: str) -> dict | None:
    """Valida o .json com o rlottie (o mesmo motor do Telegram) e mede duração e tamanho."""
    p = Path(arquivo)
    if not p.exists():
        return None
    try:
        from rlottie_python import LottieAnimation
        with LottieAnimation.from_file(str(p)) as anim:
            quadros = anim.lottie_animation_get_totalframe()
            fps = anim.lottie_animation_get_framerate()
            w, h = anim.lottie_animation_get_size()
        info = {"duracao": quadros / (fps or 30), "w": w, "h": h, "validado_por": "rlottie"}
    except ImportError:
        d = json.loads(p.read_text())
        info = {"duracao": (d.get("op", 60) - d.get("ip", 0)) / (d.get("fr") or 30), "w": d.get("w"), "h": d.get("h"),
                "validado_por": "json"}
    except Exception:
        return None
    info["dados"] = json.loads(p.read_text())
    return info


def lottie_da_biblioteca(nome: str) -> dict | None:
    return lottie_info(str(BIBLIOTECA / "lottie" / f"{nome}.json"))


# ---------------------------------------------------------------- montagem das camadas de uma cena
def da_cena(c: dict, pasta: Path) -> tuple[list[dict], list[str]]:
    camadas, avisos = [], []
    for m in c.get("marcadores") or []:
        try:
            if m["tipo"] == "mapa":
                if not mapas.disponivel():
                    avisos.append("mapa pedido, mas os dados do Natural Earth não foram baixados")
                    continue
                r = mapas.svg(mapas.de_marcador(m["dados"]), m["caixa"])
                camadas.append({"tipo": "svg", "alvo": m["seletor"], **r})
            elif m["tipo"] == "arte":
                r = arte(m["dados"], m["caixa"], pasta)
                if r:
                    camadas.append({"tipo": "imagem", "alvo": m["seletor"], **r})
                else:
                    avisos.append(f"arte '{(m['dados'].get('arte') or m['dados'].get('arteArquivo') or '')[:40]}' não gerada (sem GPU/arquivo)")
            elif m["tipo"] == "desenho":
                r = desenho(m["dados"], pasta)
                if r:
                    camadas.append({"tipo": "sequencia", "alvo": m["seletor"], **r})
                else:
                    avisos.append(f"desenho '{m['dados'].get('desenho')}' não animado (AnimatedDrawings não configurado)")
        except Exception as e:
            avisos.append(f"{m['tipo']}: {e}")
    if c.get("mapa") and mapas.disponivel():   # mapa pedido no campo da cena, sem marcador: vira fundo
        camadas.append({"tipo": "svg", "alvo": "fundo", **mapas.svg(c["mapa"])})
    return camadas, avisos
