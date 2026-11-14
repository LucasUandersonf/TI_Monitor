"""
Sincronia com a fala.

Tempo de cada palavra (usado na legenda, no punch-in e nos efeitos presos a palavras):
  1. ElevenLabs   : quando a voz é da ElevenLabs, o tempo de cada letra já vem junto
  2. WhisperX     : alinhamento forçado com o texto conhecido (preciso, ~20 ms)
  3. energia      : sem WhisperX, encontra as pausas reais no áudio e as casa com a pontuação do texto

Boca (formas A..H e X):
  1. Rhubarb Lip Sync (reconhecedor fonético, funciona em português)
  2. envelope da voz: volume e brilho do som a cada 1/30 s viram formas de boca
"""
from __future__ import annotations

import json
import re
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf

from ..config import RHUBARB_BIN


def _norm(w: str) -> str:
    return re.sub(r"[^\wÀ-ú]", "", w.lower())


@lru_cache(maxsize=1)
def _whisperx():
    try:
        import torch
        import whisperx
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        modelo, meta = whisperx.load_align_model(language_code="pt", device=dev)
        return whisperx, modelo, meta, dev
    except Exception:
        return None


def _envelope(audio: Path, passo: float = 0.01) -> tuple[np.ndarray, float]:
    a, sr = sf.read(audio, dtype="float32")
    if a.ndim > 1:
        a = a.mean(axis=1)
    n = int(sr * passo)
    k = len(a) // n
    if k == 0:
        return np.zeros(1), passo
    blocos = a[: k * n].reshape(k, n)
    return np.sqrt((blocos ** 2).mean(axis=1)), passo


def _pesos(ws: list[str]) -> list[float]:
    vog = re.compile(r"[aeiouáéíóúâêôãõà]", re.I)
    return [max(1, len(vog.findall(w))) + 0.4 for w in ws]


def estimar(texto: str, dur: float, audio: Path | None = None) -> list[dict]:
    """Sem WhisperX: usa as pausas reais do áudio (silêncios) e a pontuação para distribuir as palavras."""
    ws = texto.split()
    if not ws:
        return []
    trechos = [(0.0, dur)]
    if audio is not None and Path(audio).exists():
        env, p = _envelope(audio)
        if env.max() > 0:
            voz = env > env.max() * 0.08
            # pausas de pelo menos 120 ms dentro da fala
            pausas, i = [], 0
            while i < len(voz):
                if not voz[i]:
                    j = i
                    while j < len(voz) and not voz[j]:
                        j += 1
                    if i > 0 and j < len(voz) and (j - i) * p >= 0.12:
                        pausas.append((i * p, j * p))
                    i = j
                else:
                    i += 1
            ini = float(np.argmax(voz) * p)
            fim = float((len(voz) - np.argmax(voz[::-1])) * p)
            # quebras do texto: palavras que terminam em pontuação
            quebras = [k for k, w in enumerate(ws[:-1]) if w[-1:] in ".,;:!?…"]
            pausas = sorted(pausas, key=lambda x: x[1] - x[0], reverse=True)[: len(quebras)]
            pausas.sort()
            if pausas and len(pausas) == len(quebras):
                trechos, a = [], ini
                for (pi, pf) in pausas:
                    trechos.append((a, pi))
                    a = pf
                trechos.append((a, fim))
                grupos, g0 = [], 0
                for q in quebras:
                    grupos.append(ws[g0: q + 1])
                    g0 = q + 1
                grupos.append(ws[g0:])
                out = []
                for (a, b), grupo in zip(trechos, grupos):
                    out += _distribuir(grupo, a, b)
                return out
            trechos = [(ini, fim)]
    return _distribuir(ws, trechos[0][0], trechos[0][1])


def _distribuir(ws: list[str], a: float, b: float) -> list[dict]:
    pesos = _pesos(ws)
    tot, t, out = sum(pesos), a, []
    for w, p in zip(ws, pesos):
        d = (b - a) * p / tot
        out.append({"w": w, "ini": round(float(t), 3), "fim": round(float(t + d * 0.94), 3)})
        t += d
    return out


def palavras(audio: Path, texto: str, dur: float, prontas: list[dict] | None = None) -> tuple[list[dict], str]:
    originais = texto.split()
    if prontas and len(prontas) == len(originais):
        return [{"w": o, "ini": p["ini"], "fim": p["fim"]} for o, p in zip(originais, prontas)], "da_voz"
    wx = _whisperx()
    if wx is not None:
        whisperx, modelo, meta, dev = wx
        a = whisperx.load_audio(str(audio))
        res = whisperx.align([{"text": texto, "start": 0.0, "end": len(a) / 16000}], modelo, meta, a, dev,
                             return_char_alignments=False)
        ws = [w for w in res.get("word_segments", []) if "start" in w]
        if ws:
            out = []
            for i, w in enumerate(ws):
                igual = i < len(originais) and _norm(originais[i]) == _norm(w["word"])
                out.append({"w": originais[i] if igual else w["word"], "ini": round(w["start"], 3), "fim": round(w["end"], 3)})
            return out, "whisperx"
    from . import transcricao
    if transcricao.disponivel():
        try:
            ouvidas = transcricao.transcrever(audio, texto)
            if ouvidas:
                return transcricao.alinhar(texto, ouvidas, dur), "whisper"
        except Exception:
            pass
    return estimar(texto, dur, audio), "energia"


def _boca_rhubarb(audio: Path, texto: str) -> list[list] | None:
    try:
        dialogo = audio.with_suffix(".txt")
        dialogo.write_text(texto, encoding="utf-8")
        saida = audio.with_suffix(".boca.json")
        subprocess.run([RHUBARB_BIN, "-r", "phonetic", "-f", "json", "-d", str(dialogo), "-o", str(saida), str(audio)],
                       check=True, capture_output=True, timeout=300)
        return [[c["start"], c["end"], c["value"]] for c in json.loads(saida.read_text())["mouthCues"]]
    except Exception:
        return None


def _boca_envelope(audio: Path, fps: int = 30) -> list[list]:
    """Volume decide o quanto a boca abre; o 'brilho' (cruzamentos por zero) separa sons de S/F de vogais."""
    a, sr = sf.read(audio, dtype="float32")
    if a.ndim > 1:
        a = a.mean(axis=1)
    n = sr // fps
    k = len(a) // n
    if k == 0:
        return []
    bl = a[: k * n].reshape(k, n)
    rms = np.sqrt((bl ** 2).mean(axis=1))
    zcr = (np.abs(np.diff(np.sign(bl), axis=1)) > 0).mean(axis=1)
    ref = np.percentile(rms[rms > 0], 95) if (rms > 0).any() else 1
    formas = []
    for i in range(k):
        v = rms[i] / ref
        if v < 0.08:
            f = "X"
        elif zcr[i] > 0.25:
            f = "G" if v < 0.4 else "B"     # chiado: F, V, S
        elif v < 0.3:
            f = "B"
        elif v < 0.55:
            f = "C"
        elif v < 0.8:
            f = "E" if i % 4 == 0 else "D"
        else:
            f = "D"
        formas.append(f)
    # suaviza: não deixa a boca trocar de forma em menos de 2 quadros
    out, ini = [], 0
    for i in range(1, k + 1):
        if i == k or formas[i] != formas[ini]:
            if out and (i - ini < 2 or out[-1][2] == formas[ini]):
                out[-1][1] = i / fps
            else:
                out.append([ini / fps, i / fps, formas[ini]])
            ini = i
    return out


def boca(audio: Path, texto: str) -> tuple[list[list] | None, str]:
    r = _boca_rhubarb(audio, texto)
    if r:
        return r, "rhubarb"
    return _boca_envelope(audio), "envelope"


def momento(ws: list[dict], palavra: str) -> float | None:
    alvo = _norm(palavra)
    for w in ws:
        if _norm(w["w"]) == alvo:
            return w["ini"]
    return None
