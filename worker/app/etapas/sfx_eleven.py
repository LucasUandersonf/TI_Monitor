"""
Biblioteca de efeitos sonoros modernos gerada pela ElevenLabs (Sound Effects), UMA vez só.

Os arquivos ficam em dados/biblioteca/sfx/<categoria>/eleven_N.wav e são reaproveitados em todos os vídeos
(a edição sorteia a variação e muda levemente o tom a cada uso, para não soar repetido).
Nenhum vídeo gera som na hora: o gasto de créditos acontece só quando você chama POST /sfx/biblioteca.
"""
from __future__ import annotations

import json
import subprocess
import time

import httpx
import numpy as np
import soundfile as sf

from ..config import BIBLIOTECA, ELEVENLABS_API_KEY
from . import narracao

SR = 48000
ESTILO = "modern YouTube documentary sound design, clean, crisp, high fidelity, no music, no voice"
# categoria -> (descrição, duração em s, variações)
PEDIDOS = {
    "pop":                ("soft modern UI pop, bubbly and tight, satisfying", 0.5, 3),
    "whoosh":             ("fast airy swoosh passing by, short and clean", 0.8, 3),
    "whoosh_grave":       ("deep cinematic sub whoosh with low rumble tail", 1.4, 2),
    "transicao":          ("short riser that ends in a crisp swoosh, scene transition", 1.2, 2),
    "impacto":            ("punchy cinematic trailer hit, low boom with short tail", 1.6, 2),
    "baque":              ("soft heavy thud, muffled", 0.6, 1),
    "risco_caneta":       ("quick felt marker scribble on paper", 0.8, 2),
    "papel":              ("paper crumple and toss", 1.0, 1),
    "tick":               ("subtle clean UI tick", 0.5, 2),
    "ding":               ("bright clean bell ding, single hit", 1.2, 1),
    "notificacao":        ("smartphone notification chime, two short notes", 0.9, 1),
    "moeda":              ("single coin drop on a table", 0.8, 1),
    "caixa_registradora": ("cash register cha-ching", 1.3, 1),
    "bip":                ("censor bleep, single 1 kHz tone", 0.6, 1),
    "glitch":             ("short digital glitch stutter, data corruption", 0.6, 2),
    "riser":              ("tension riser building up, ends abruptly", 2.0, 1),
    "digitar":            ("short burst of fast keyboard typing", 1.0, 1),
    "drone":              ("dark low ambient drone, slow and evolving", 8.0, 1),
}


def plano() -> dict:
    itens = [(cat, k) for cat, (_, _, n) in PEDIDOS.items() for k in range(1, n + 1)]
    feitos = [(c, k) for c, k in itens if (BIBLIOTECA / "sfx" / c / f"eleven_{k}.wav").exists()]
    faltam = [(c, k) for c, k in itens if (c, k) not in feitos]
    return {"total": len(itens), "ja_existem": len(feitos), "a_gerar": len(faltam),
            "segundos_a_gerar": round(sum(PEDIDOS[c][1] for c, _ in faltam), 1),
            "categorias": sorted({c for c, _ in faltam})}


def gerar(refazer: bool = False, limite_creditos: int = 1500) -> dict:
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("configure ELEVENLABS_API_KEY no worker")
    antes = narracao.saldo_elevenlabs()
    feitos, erros = [], []
    for cat, (desc, dur, n) in PEDIDOS.items():
        pasta = BIBLIOTECA / "sfx" / cat
        pasta.mkdir(parents=True, exist_ok=True)
        for k in range(1, n + 1):
            dest = pasta / f"eleven_{k}.wav"
            if dest.exists() and not refazer:
                continue
            agora = narracao.saldo_elevenlabs()
            if antes and agora and antes["restante"] - agora["restante"] > limite_creditos:
                erros.append(f"parei: o limite de {limite_creditos} créditos para sons foi atingido")
                return _fim(antes, feitos, erros)
            try:
                r = None
                for t in range(4):
                    r = httpx.post("https://api.elevenlabs.io/v1/sound-generation", timeout=120,
                                   headers={"xi-api-key": ELEVENLABS_API_KEY},
                                   json={"text": f"{desc}. {ESTILO}. Variation {k}.", "duration_seconds": max(0.5, dur),
                                         "prompt_influence": 0.6})
                    if r.status_code in (429, 500, 502, 503):
                        time.sleep(3 * 2 ** t)
                        continue
                    break
                if r.status_code != 200:
                    erros.append(f"{cat} {k}: {r.status_code} {r.text[:150]}")
                    if r.status_code in (401, 402, 403):
                        return _fim(antes, feitos, erros)
                    continue
                pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", "pipe:0", "-f", "f32le", "-ac", "1", "-ar", str(SR), "pipe:1"],
                                     input=r.content, capture_output=True, check=True).stdout
                a = np.frombuffer(pcm, dtype=np.float32).copy()
                idx = np.where(np.abs(a) > 0.004)[0]          # tira o silêncio da ponta: o som cai no instante certo
                if len(idx):
                    a = a[max(0, idx[0] - int(0.005 * SR)): idx[-1] + int(0.05 * SR)]
                n_fade = min(len(a), int(0.02 * SR))
                a[-n_fade:] *= np.linspace(1, 0, n_fade)
                a *= 0.89 / float(np.max(np.abs(a)) or 1)
                sf.write(dest, a, SR, subtype="PCM_24")
                (pasta / "_sintetico.wav").unlink(missing_ok=True)
                dest.with_name(dest.name + ".credito.json").write_text(json.dumps(
                    {"fonte": "ElevenLabs Sound Effects", "licenca": "uso comercial (plano pago)", "nao_creditar": True},
                    ensure_ascii=False))
                feitos.append(f"{cat}/{dest.name}")
            except Exception as e:
                erros.append(f"{cat} {k}: {str(e)[:150]}")
    return _fim(antes, feitos, erros)


def _fim(antes, feitos, erros) -> dict:
    depois = narracao.saldo_elevenlabs()
    gasto = (antes["restante"] - depois["restante"]) if antes and depois else None
    return {"gerados": feitos, "erros": erros, "creditos_gastos": gasto, "saldo": depois and depois["restante"]}
