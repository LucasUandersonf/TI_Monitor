"""
Narração: uma faixa por cena, com o texto exato do artifact. A duração da cena vem desta faixa.

Motores (TTS_MOTOR=auto escolhe o primeiro configurado, nesta ordem):
  elevenlabs  : voz premium (ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID); o tempo de cada letra vem junto
  google      : Google Cloud TTS (GOOGLE_TTS_API_KEY); cota grátis mensal generosa; o tempo de cada
                palavra vem junto (marcas SSML), então a sincronia é tão exata quanto a da ElevenLabs
  kokoro_onnx : Kokoro-82M local, grátis, CPU, vozes pt-BR pm_alex / pm_santa / pf_dora
  estimado    : silêncio com a duração estimada, só para teste
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf

from ..config import (DADOS, ELEVENLABS_API_KEY, ELEVENLABS_ESTABILIDADE, ELEVENLABS_MODELO, ELEVENLABS_VELOCIDADE,
                      ELEVENLABS_VOICE_ID, GOOGLE_TTS_API_KEY, GOOGLE_TTS_TOM, GOOGLE_TTS_VELOCIDADE, GOOGLE_TTS_VOZ,
                      KOKORO_VELOCIDADE, KOKORO_VOZ, MODELOS, TTS_MOTOR)
from . import texto_fala

SR = 48000
ORDEM = ["elevenlabs", "google", "kokoro_onnx", "estimado"]


def _carregar(nome: str):
    if nome == "elevenlabs":
        if not (ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID):
            raise RuntimeError("sem chave")
        return True
    if nome == "google":
        if not GOOGLE_TTS_API_KEY:
            raise RuntimeError("sem chave")
        return True
    if nome == "kokoro_onnx":
        from kokoro_onnx import Kokoro
        modelo, vozes = MODELOS / "kokoro" / "model_quantized.onnx", MODELOS / "kokoro" / "voices_ptbr.bin"
        if not modelo.exists():
            raise RuntimeError("modelo Kokoro não baixado (rode docker/baixar_modelos.sh)")
        return Kokoro(str(modelo), str(vozes))
    return None


_cache_motores: dict = {}


def _obter(nome: str):
    if nome not in _cache_motores:
        _cache_motores[nome] = _carregar(nome)
    return _cache_motores[nome]


@lru_cache(maxsize=1)
def _motor():
    if TTS_MOTOR != "auto":  # motor escolhido: se não funcionar, para com o motivo (nunca troca de voz no meio)
        try:
            return TTS_MOTOR, _obter(TTS_MOTOR)
        except Exception as e:
            msg = {"elevenlabs": "configure ELEVENLABS_API_KEY e ELEVENLABS_VOICE_ID nas variáveis do worker no Railway",
                   "google": "configure GOOGLE_TTS_API_KEY nas variáveis do worker no Railway"}.get(TTS_MOTOR, str(e))
            raise RuntimeError(f"voz {TTS_MOTOR} indisponível: {msg}")
    for nome in ORDEM:
        try:
            return nome, _obter(nome)
        except Exception:
            continue
    return "estimado", None


def motor_atual() -> str:
    return _motor()[0]


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


ELEVEN = "https://api.elevenlabs.io/v1"
CACHE_TTS = Path(os.environ.get("FABRICA_CACHE_TTS", str(DADOS / "cache" / "tts")))


def _eh_v3() -> bool:
    return "v3" in (ELEVENLABS_MODELO or "")


def custo_por_caractere() -> float:
    """Créditos por caractere do modelo (Flash/Turbo custam metade)."""
    m = (ELEVENLABS_MODELO or "").lower()
    return 0.5 if ("flash" in m or "turbo" in m) else 1.0


def _chave_cache(texto: str) -> str:
    base = json.dumps([texto, ELEVENLABS_VOICE_ID, ELEVENLABS_MODELO, ELEVENLABS_VELOCIDADE, ELEVENLABS_ESTABILIDADE],
                      ensure_ascii=False)
    return hashlib.sha256(base.encode()).hexdigest()[:24]


def em_cache(texto: str) -> bool:
    return (CACHE_TTS / f"{_chave_cache(texto_fala.preparar(texto))}.json").exists()


def saldo_elevenlabs() -> dict | None:
    """Créditos restantes na conta (None se não deu para consultar)."""
    import httpx
    try:
        r = httpx.get(f"{ELEVEN}/user/subscription", headers={"xi-api-key": ELEVENLABS_API_KEY}, timeout=20)
        r.raise_for_status()
        d = r.json()
        return {"usados": d.get("character_count"), "limite": d.get("character_limit"),
                "restante": (d.get("character_limit") or 0) - (d.get("character_count") or 0), "plano": d.get("tier")}
    except Exception:
        return None


def _decodificar(conteudo: bytes, formato: str) -> np.ndarray:
    if formato.startswith("pcm_"):
        return _para_48k(np.frombuffer(conteudo, dtype=np.int16).astype(np.float32) / 32768, int(formato.split("_")[1]))
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", "pipe:0", "-f", "f32le", "-ac", "1", "-ar", str(SR), "pipe:1"],
                       input=conteudo, capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype=np.float32).copy()


_FORMATO = {"atual": "pcm_44100"}


def _pedir_elevenlabs(corpo: dict) -> tuple[np.ndarray, dict]:
    """Chama a API com novas tentativas (limite de taxa, instabilidade) e erros claros (chave, créditos)."""
    import time
    import httpx
    ultimo = ""
    for tentativa in range(6):
        try:
            r = httpx.post(f"{ELEVEN}/text-to-speech/{ELEVENLABS_VOICE_ID}/with-timestamps",
                           params={"output_format": _FORMATO["atual"]}, timeout=180,
                           headers={"xi-api-key": ELEVENLABS_API_KEY}, json=corpo)
        except httpx.HTTPError as e:
            ultimo = str(e)
            time.sleep(2 * 2 ** tentativa)
            continue
        if r.status_code == 200:
            d = r.json()
            return _decodificar(base64.b64decode(d["audio_base64"]), _FORMATO["atual"]), d.get("alignment") or {}
        txt = r.text[:400]
        if r.status_code in (400, 403) and "output_format" in txt and _FORMATO["atual"] != "mp3_44100_128":
            _FORMATO["atual"] = "mp3_44100_128"      # plano sem PCM: usa MP3 de alta qualidade
            continue
        if "quota_exceeded" in txt or ("credit" in txt.lower() and r.status_code in (401, 402, 403)):
            raise RuntimeError("ElevenLabs: créditos insuficientes para terminar a narração. Recarregue e rode de novo "
                               "(as cenas já narradas ficam guardadas e não são cobradas outra vez)")
        if r.status_code == 401 or "invalid_api_key" in txt:
            raise RuntimeError("ElevenLabs recusou a chave (ELEVENLABS_API_KEY errada ou sem permissão de Text to Speech)")
        if r.status_code == 404 or "voice_not_found" in txt:
            raise RuntimeError(f"ElevenLabs: voz {ELEVENLABS_VOICE_ID} não encontrada (confira ELEVENLABS_VOICE_ID)")
        if r.status_code in (429, 500, 502, 503, 504):
            ultimo = f"{r.status_code} {txt}"
            time.sleep(min(60, 3 * 2 ** tentativa))
            continue
        raise RuntimeError(f"ElevenLabs falhou ({r.status_code}): {txt}")
    raise RuntimeError(f"ElevenLabs indisponível depois de 6 tentativas: {ultimo[:300]}")


def _elevenlabs(texto: str, anterior: str = "", seguinte: str = "") -> tuple[np.ndarray, list[dict], bool]:
    """Fala uma cena. Guarda em cache: rodar o mesmo vídeo de novo não gasta crédito.
    anterior/seguinte (texto das cenas vizinhas) mantêm a entonação contínua entre as cenas."""
    CACHE_TTS.mkdir(parents=True, exist_ok=True)
    chave = _chave_cache(texto)
    meta, wav = CACHE_TTS / f"{chave}.json", CACHE_TTS / f"{chave}.wav"
    if meta.exists() and wav.exists():
        a, _ = sf.read(wav, dtype="float32")
        return a, json.loads(meta.read_text(encoding="utf-8")), True
    corpo = {"text": texto, "model_id": ELEVENLABS_MODELO, "language_code": "pt",
             "apply_text_normalization": "auto",
             "voice_settings": {"stability": ELEVENLABS_ESTABILIDADE, "similarity_boost": 0.8, "style": 0.15,
                                "use_speaker_boost": True, "speed": ELEVENLABS_VELOCIDADE}}
    if not _eh_v3():  # o v3 não aceita contexto; v2/flash/turbo aceitam
        if anterior:
            corpo["previous_text"] = texto_fala.preparar(anterior)[-600:]
        if seguinte:
            corpo["next_text"] = texto_fala.preparar(seguinte)[:300]
    audio, al = _pedir_elevenlabs(corpo)
    # letras -> palavras
    letras, ini, fim = al.get("characters", []), al.get("character_start_times_seconds", []), al.get("character_end_times_seconds", [])
    palavras, atual, t0, ultimo = [], "", None, 0.0
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
    sf.write(wav, audio, SR, subtype="PCM_24")
    meta.write_text(json.dumps(palavras, ensure_ascii=False), encoding="utf-8")
    return audio, palavras, False


GOOGLE = "https://texttospeech.googleapis.com/v1beta1/text:synthesize"


def _ssml_com_marcas(texto: str) -> tuple[str, list[str]]:
    """Uma marca antes de cada palavra: o Google devolve o instante em que cada uma começa."""
    esc = lambda w: w.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    ws = texto.split()
    corpo = " ".join(f'<mark name="{i}"/>{esc(w)}' for i, w in enumerate(ws))
    return f'<speak>{corpo}<mark name="fim"/></speak>', ws


def _google(texto: str) -> tuple[np.ndarray, list[dict], bool]:
    """Fala uma cena pelo Google Cloud TTS, com o tempo de cada palavra. Guarda em cache (refazer não gasta cota)."""
    import time
    import httpx
    CACHE_TTS.mkdir(parents=True, exist_ok=True)
    chave = hashlib.sha256(json.dumps(["google", texto, GOOGLE_TTS_VOZ, GOOGLE_TTS_VELOCIDADE, GOOGLE_TTS_TOM],
                                      ensure_ascii=False).encode()).hexdigest()[:24]
    meta, wav = CACHE_TTS / f"{chave}.json", CACHE_TTS / f"{chave}.wav"
    if meta.exists() and wav.exists():
        a, _ = sf.read(wav, dtype="float32")
        return a, json.loads(meta.read_text(encoding="utf-8")), True
    ssml, ws = _ssml_com_marcas(texto)
    lingua = "-".join(GOOGLE_TTS_VOZ.split("-")[:2]) or "pt-BR"
    corpo = {"input": {"ssml": ssml}, "voice": {"languageCode": lingua, "name": GOOGLE_TTS_VOZ},
             "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": SR, "speakingRate": GOOGLE_TTS_VELOCIDADE,
                             "pitch": GOOGLE_TTS_TOM},
             "enableTimePointing": ["SSML_MARK"]}
    ultimo = ""
    for tentativa in range(6):
        try:
            r = httpx.post(GOOGLE, params={"key": GOOGLE_TTS_API_KEY}, json=corpo, timeout=120)
        except httpx.HTTPError as e:
            ultimo = str(e)
            time.sleep(2 * 2 ** tentativa)
            continue
        if r.status_code == 200:
            break
        txt = r.text[:400]
        if r.status_code in (429, 500, 502, 503, 504):
            ultimo = f"{r.status_code} {txt}"
            time.sleep(min(60, 3 * 2 ** tentativa))
            continue
        if r.status_code in (401, 403):
            raise RuntimeError("Google TTS recusou a chave: confira GOOGLE_TTS_API_KEY e se a API Cloud Text-to-Speech "
                               f"está ativada no projeto ({txt})")
        raise RuntimeError(f"Google TTS falhou ({r.status_code}): {txt}")
    else:
        raise RuntimeError(f"Google TTS indisponível depois de 6 tentativas: {ultimo[:300]}")
    d = r.json()
    audio = _decodificar(base64.b64decode(d["audioContent"]), "wav")
    dur = len(audio) / SR
    marcas = {t["markName"]: float(t["timeSeconds"]) for t in d.get("timepoints", [])}
    palavras = []
    if all(str(i) in marcas for i in range(len(ws))):   # vozes sem suporte a marcas: fica sem (o alinhamento estima)
        for i, w in enumerate(ws):
            ini = marcas[str(i)]
            fim = marcas.get(str(i + 1), marcas.get("fim", dur))
            palavras.append({"w": w, "ini": round(ini, 3), "fim": round(max(ini + 0.05, fim - 0.02), 3)})
    sf.write(wav, audio, SR, subtype="PCM_24")
    meta.write_text(json.dumps(palavras, ensure_ascii=False), encoding="utf-8")
    return audio, palavras, False


def falar(texto: str, saida: Path, motor: str | None = None,
          anterior: str = "", seguinte: str = "") -> dict:
    """motor: força um motor (ex.: 'kokoro_onnx'); sem ele, usa o escolhido por TTS_MOTOR / auto.
    anterior/seguinte: texto das cenas vizinhas (a ElevenLabs usa para a entonação não "recomeçar" a cada cena)."""
    nome, m = (motor, _obter(motor)) if motor else _motor()
    do_cache = False
    palavras = None
    original, texto = texto, texto_fala.preparar(texto)   # números por extenso e pronúncia
    if nome == "elevenlabs":
        audio, palavras, do_cache = _elevenlabs(texto, anterior, seguinte)
    elif nome == "google":
        audio, palavras, do_cache = _google(texto)
    elif nome == "kokoro_onnx":
        amostras, sr = m.create(texto, voice=KOKORO_VOZ, speed=KOKORO_VELOCIDADE, lang="pt-br")
        audio = _para_48k(amostras, sr)
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
        if texto != original:  # a voz falou o texto preparado; a legenda usa o original
            from . import transcricao
            palavras = transcricao.alinhar(original, palavras, len(audio) / SR)
    return {"arquivo": str(saida), "duracao": len(audio) / SR, "motor": nome, "palavras_tts": palavras,
            "caracteres": len(texto) if nome in ("elevenlabs", "google") and not do_cache else 0, "do_cache": do_cache}


def disponiveis() -> dict:
    out = {}
    for nome in ORDEM[:-1]:
        try:
            _carregar(nome)
            out[nome] = "ok"
        except Exception as e:
            out[nome] = str(e)[:80]
    return out
