"""
Narração: uma faixa por cena, com o texto exato do artifact.

Motores (TTS_MOTOR=auto escolhe o primeiro disponível, nesta ordem):
  elevenlabs  : voz premium paga (ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID)
  clone       : SUA voz clonada, grátis e local (biblioteca/voz/referencia.wav), com o motor de
                VOZ_CLONE_MOTOR: qwen3 (Qwen3-TTS, Apache 2.0) ou chatterbox (Chatterbox Multilingual, MIT).
                Cada frase é conferida pelo Whisper e refeita se sair errada (ver voz_clonada.py)
  kokoro_onnx : Kokoro-82M ONNX quantizado, CPU, vozes pt-BR pm_alex / pm_santa / pf_dora
  kokoro      : Kokoro em PyTorch (mesmas vozes)
  piper       : Piper TTS local (PIPER_MODEL)
  estimado    : silêncio com a duração estimada, só para teste
"""
from __future__ import annotations

import base64
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf

from ..config import (ELEVENLABS_API_KEY, ELEVENLABS_MODELO, ELEVENLABS_VOICE_ID, KOKORO_VELOCIDADE, KOKORO_VOZ,
                      MODELOS, PIPER_BIN, PIPER_MODEL, TTS_MOTOR, VOZ_CLONE_MOTOR)
from . import texto_fala, voz_clonada

SR = 48000
ORDEM = ["elevenlabs", "clone", "kokoro_onnx", "kokoro", "piper", "estimado"]


def _carregar(nome: str):
    if nome == "elevenlabs":
        if not (ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID):
            raise RuntimeError("sem chave")
        return True
    if nome == "clone":
        ok, motivo = voz_clonada.disponivel(VOZ_CLONE_MOTOR)
        if not ok:
            raise RuntimeError(motivo)
        return VOZ_CLONE_MOTOR
    if nome == "kokoro_onnx":
        from kokoro_onnx import Kokoro
        modelo, vozes = MODELOS / "kokoro" / "model_quantized.onnx", MODELOS / "kokoro" / "voices_ptbr.bin"
        if not modelo.exists():
            raise RuntimeError("modelo Kokoro não baixado (rode docker/baixar_modelos.sh)")
        return Kokoro(str(modelo), str(vozes))
    if nome == "kokoro":
        from kokoro import KPipeline
        return KPipeline(lang_code="p")
    if nome == "piper":
        if not PIPER_MODEL or not Path(PIPER_MODEL).exists():
            raise RuntimeError("sem PIPER_MODEL")
        return PIPER_MODEL
    return None


_cache_motores: dict = {}


def _obter(nome: str):
    if nome not in _cache_motores:
        _cache_motores[nome] = _carregar(nome)
    return _cache_motores[nome]


@lru_cache(maxsize=1)
def _motor():
    for nome in ([TTS_MOTOR] if TTS_MOTOR != "auto" else ORDEM):
        try:
            return nome, _obter(nome)
        except Exception:
            continue
    return "estimado", None


def _para_48k(audio: np.ndarray, sr: int) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if sr == SR:
        return audio
    x = np.linspace(0, len(audio) - 1, int(len(audio) * SR / sr))
    return np.interp(x, np.arange(len(audio)), audio).astype(np.float32)


def _aparar(audio: np.ndarray, limiar: float = 0.01) -> tuple[np.ndarray, float]:
    """Tira silêncio do começo e do fim. Devolve também quanto foi cortado do começo (s)."""
    idx = np.where(np.abs(audio) > limiar)[0]
    if len(idx) == 0:
        return audio, 0.0
    ini = max(0, idx[0] - int(0.03 * SR))
    return audio[ini: idx[-1] + int(0.08 * SR)], ini / SR


def _elevenlabs(texto: str) -> tuple[np.ndarray, list[dict]]:
    import httpx
    r = httpx.post(f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/with-timestamps",
                   params={"output_format": "pcm_44100"}, timeout=120,
                   headers={"xi-api-key": ELEVENLABS_API_KEY},
                   json={"text": texto, "model_id": ELEVENLABS_MODELO, "language_code": "pt",
                         "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.25}})
    r.raise_for_status()
    d = r.json()
    pcm = np.frombuffer(base64.b64decode(d["audio_base64"]), dtype=np.int16).astype(np.float32) / 32768
    # letras -> palavras
    al = d.get("alignment") or {}
    letras, ini, fim = al.get("characters", []), al.get("character_start_times_seconds", []), al.get("character_end_times_seconds", [])
    palavras, atual, t0 = [], "", None
    for ch, a, b in zip(letras, ini, fim):
        if ch.isspace():
            if atual:
                palavras.append({"w": atual, "ini": t0, "fim": ultimo})
            atual, t0 = "", None
            continue
        if t0 is None:
            t0 = a
        atual += ch
        ultimo = b
    if atual:
        palavras.append({"w": atual, "ini": t0, "fim": ultimo})
    return _para_48k(pcm, 44100), palavras


def falar(texto: str, saida: Path, semente: int = 7, motor: str | None = None) -> dict:
    """motor: força um motor (ex.: 'kokoro_onnx'); sem ele, usa o escolhido por TTS_MOTOR / auto."""
    nome, m = (motor, _obter(motor)) if motor else _motor()
    if nome == "clone":
        return voz_clonada.falar(texto, saida, m, semente)
    palavras = None
    original, texto = texto, texto_fala.preparar(texto)   # números por extenso e pronúncia
    if nome == "elevenlabs":
        audio, palavras = _elevenlabs(texto)
    elif nome == "kokoro_onnx":
        amostras, sr = m.create(texto, voice=KOKORO_VOZ, speed=KOKORO_VELOCIDADE, lang="pt-br")
        audio = _para_48k(amostras, sr)
    elif nome == "kokoro":
        partes = [np.asarray(a) for _, _, a in m(texto, voice=KOKORO_VOZ, speed=KOKORO_VELOCIDADE)]
        audio = _para_48k(np.concatenate(partes), 24000)
    elif nome == "piper":
        tmp = saida.with_suffix(".piper.wav")
        subprocess.run([PIPER_BIN, "--model", m, "--output_file", str(tmp)], input=texto.encode(), check=True,
                       capture_output=True)
        a, sr = sf.read(tmp, dtype="float32")
        audio = _para_48k(a if a.ndim == 1 else a.mean(axis=1), sr)
        tmp.unlink(missing_ok=True)
    else:
        audio = np.zeros(int(max(1.5, len(texto.split()) / 2.5) * SR), dtype=np.float32)
    corte = 0.0
    if nome != "estimado":
        audio, corte = _aparar(audio)
        pico = float(np.max(np.abs(audio)) or 1)
        audio = audio * min(1.0, 0.89 / pico)        # pico em -1 dBFS antes da mixagem
    sf.write(saida, audio, SR)
    if palavras:
        palavras = [{"w": w["w"], "ini": round(max(0, w["ini"] - corte), 3), "fim": round(max(0, w["fim"] - corte), 3)}
                    for w in palavras]
        if texto != original:  # a ElevenLabs falou o texto preparado; a legenda usa o original
            from . import transcricao
            palavras = transcricao.alinhar(original, palavras, len(audio) / SR)
    return {"arquivo": str(saida), "duracao": len(audio) / SR, "motor": nome, "palavras_tts": palavras}


def disponiveis() -> dict:
    out = {}
    for motor in ("qwen3", "chatterbox"):
        ok, motivo = voz_clonada.disponivel(motor)
        out[f"clone_{motor}"] = "ok" if ok else motivo
    for nome in ORDEM[:-1]:
        if nome == "clone":
            continue
        try:
            _carregar(nome)
            out[nome] = "ok"
        except Exception as e:
            out[nome] = str(e)[:80]
    return out
