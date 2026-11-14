"""
faster-whisper (modelo small, int8, CPU): transcreve a narração com o tempo de cada palavra.

Serve para duas coisas:
  1. alinhamento sem GPU: tempo real de cada palavra do texto original (legenda, punch-in, efeitos)
  2. conferência: compara o que foi falado com o texto
"""
from __future__ import annotations

import difflib
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf

from . import modelos


def _norm(w: str) -> str:
    return re.sub(r"[^\wÀ-ú]", "", w.lower())


@lru_cache(maxsize=1)
def _modelo():
    from faster_whisper import WhisperModel
    if not modelos.presente("whisper_small"):
        modelos.baixar("whisper_small")
    return WhisperModel(str(modelos.pasta("whisper_small")), device="cpu", compute_type="int8")


def disponivel() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def _ler16k(audio) -> np.ndarray:
    if isinstance(audio, (str, Path)):
        a, sr = sf.read(audio, dtype="float32")
    else:
        a, sr = audio
    a = a if a.ndim == 1 else a.mean(axis=1)
    if sr != 16000:
        a = np.interp(np.linspace(0, len(a) - 1, int(len(a) * 16000 / sr)), np.arange(len(a)), a)
    return a.astype(np.float32)


def transcrever(audio, texto_esperado: str | None = None) -> list[dict]:
    """Palavras ouvidas com início e fim (s). audio: caminho ou (array, sr)."""
    # sem initial_prompt de propósito: com o texto esperado como "dica", o Whisper entende que aquilo já foi
    # dito e transcreve só o final (a conferência dava nota baixa para uma fala certa)
    segs, _ = _modelo().transcribe(_ler16k(audio), language="pt", word_timestamps=True, beam_size=1,
                                   vad_filter=False, condition_on_previous_text=False)
    return [{"w": w.word.strip(), "ini": float(w.start), "fim": float(w.end)} for s in segs for w in (s.words or [])]


def semelhanca(ouvidas: list[dict], texto: str) -> float:
    a = [_norm(w["w"]) for w in ouvidas if _norm(w["w"])]
    b = [_norm(w) for w in texto.split() if _norm(w)]
    if not b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def alinhar(texto: str, ouvidas: list[dict], duracao: float) -> list[dict]:
    """Dá a cada palavra do texto original o tempo da palavra ouvida correspondente; as que não casaram
    são interpoladas entre as vizinhas."""
    orig = texto.split()
    a = [_norm(w) for w in orig]
    b = [_norm(w["w"]) for w in ouvidas]
    tempos: list[tuple[float, float] | None] = [None] * len(orig)
    for bloco in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(bloco.size):
            w = ouvidas[bloco.b + k]
            tempos[bloco.a + k] = (w["ini"], w["fim"])
    # interpola os buracos (números falados por extenso, palavras que o modelo ouviu diferente)
    i = 0
    while i < len(orig):
        if tempos[i] is None:
            j = i
            while j < len(orig) and tempos[j] is None:
                j += 1
            ini = tempos[i - 1][1] if i > 0 else (ouvidas[0]["ini"] if ouvidas else 0.0)
            fim = tempos[j][0] if j < len(orig) else (ouvidas[-1]["fim"] if ouvidas else duracao)
            passo = max(0.05, (fim - ini) / (j - i))
            for k in range(i, j):
                tempos[k] = (ini + (k - i) * passo, ini + (k - i + 1) * passo * 0.94)
            i = j
        else:
            i += 1
    return [{"w": w, "ini": round(t[0], 3), "fim": round(t[1], 3)} for w, t in zip(orig, tempos)]
