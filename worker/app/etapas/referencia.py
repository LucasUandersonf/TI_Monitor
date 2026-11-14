"""
Cadastro da sua voz: recebe uma gravação qualquer (celular serve), limpa e escolhe o melhor trecho.

  1. converte para mono 24 kHz, tira graves de ruído (passa-alta 70 Hz), reduz chiado (afftdn),
     nivela o volume (-20 LUFS)
  2. escolhe a janela de ~12 s com mais fala contínua e sem estouro
  3. transcreve o trecho com o Whisper (referencia.txt): o Qwen3 usa a transcrição para clonar melhor
  4. devolve um relatório: duração, ruído de fundo, estouro, avisos do que melhorar
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from ..config import BIBLIOTECA
from . import transcricao

PASTA = BIBLIOTECA / "voz"
SR = 24000
JANELA = 12.0


def preparar(entrada: Path) -> dict:
    PASTA.mkdir(parents=True, exist_ok=True)
    limpo = PASTA / "_gravacao_limpa.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(entrada), "-ac", "1", "-ar", str(SR),
                    "-af", "highpass=f=70,afftdn=nr=12:nf=-40,loudnorm=I=-20:TP=-2:LRA=7",
                    str(limpo)], check=True)
    a, sr = sf.read(limpo, dtype="float32")
    avisos = []
    total = len(a) / sr
    if total < 6:
        avisos.append("Gravação curta: grave de 15 a 30 s falando naturalmente.")

    # energia em blocos de 50 ms
    n = int(0.05 * sr)
    k = len(a) // n
    rms = np.sqrt((a[: k * n].reshape(k, n) ** 2).mean(axis=1)) if k else np.zeros(1)
    estouro = (np.abs(a) > 0.98).mean() * 100
    if estouro > 0.1:
        avisos.append(f"Áudio estourado em {estouro:.1f}% do tempo: grave mais longe do microfone.")
    voz = rms > np.percentile(rms, 90) * 0.15
    ruido_db = 20 * np.log10(np.percentile(rms, 10) + 1e-9)
    fala_db = 20 * np.log10(np.percentile(rms, 90) + 1e-9)
    snr = fala_db - ruido_db
    if snr < 25:
        avisos.append(f"Ruído de fundo alto (fala só {snr:.0f} dB acima do ruído): grave num lugar mais silencioso.")

    # melhor janela: mais blocos com voz, sem silêncios longos
    blocos_janela = int(JANELA / 0.05)
    if k > blocos_janela:
        soma = np.convolve(voz.astype(float), np.ones(blocos_janela), "valid")
        i0 = int(np.argmax(soma))
    else:
        i0 = 0
    trecho = a[i0 * n: (i0 + blocos_janela) * n]
    # começa e termina em silêncio (não corta palavra)
    ini = max(0, int(np.argmax(np.abs(trecho) > 0.02)) - int(0.05 * sr))
    fim = len(trecho) - max(0, int(np.argmax(np.abs(trecho[::-1]) > 0.02)) - int(0.08 * sr))
    trecho = trecho[ini:fim]
    sf.write(PASTA / "referencia.wav", trecho, sr)

    texto = ""
    try:
        texto = " ".join(w["w"] for w in transcricao.transcrever((trecho, sr))).strip()
        (PASTA / "referencia.txt").write_text(texto, encoding="utf-8")
    except Exception as e:
        avisos.append(f"Não consegui transcrever a referência ({e}); a clonagem usa só o timbre.")
        (PASTA / "referencia.txt").unlink(missing_ok=True)
    limpo.unlink(missing_ok=True)
    return {"ok": True, "duracao_gravacao": round(total, 1), "duracao_referencia": round(len(trecho) / sr, 1),
            "fala_acima_do_ruido_db": round(float(snr), 1), "estouro_pct": round(float(estouro), 2),
            "transcricao": texto, "avisos": avisos, "arquivo": str(PASTA / "referencia.wav")}
