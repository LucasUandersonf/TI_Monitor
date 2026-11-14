"""
Voz clonada (a sua voz), grátis e local:

  qwen3       Qwen3-TTS Base (Apache 2.0). Mais rápido em CPU. Com a transcrição da referência
              (referencia.txt, feita sozinha pelo Whisper) usa o modo de clonagem completo.
  chatterbox  Chatterbox Multilingual (MIT). Mais expressivo; melhor com GPU.

Cada motor roda num processo próprio (voz/voz_servidor.py, no ambiente Python dele) que fica com o
modelo carregado entre uma frase e outra.

Para cada cena:
  1. o texto é preparado para a fala (números por extenso, pronúncia) e dividido em frases de até ~220 caracteres
  2. cada pedaço é gerado com a mesma semente (voz estável do começo ao fim do vídeo)
  3. o Whisper confere o que foi falado; se não bater com o texto (palavra trocada, repetição, frase
     inventada), o pedaço é gerado de novo com outra semente (até 2 vezes) e fica o melhor
  4. os pedaços são unidos com pausas naturais (mais longas depois de ponto final)
  5. o tempo de cada palavra sai da própria conferência, sem passo extra de alinhamento
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from pathlib import Path

import numpy as np
import soundfile as sf

from ..config import BIBLIOTECA, RAIZ
from . import modelos, texto_fala, transcricao

SR = 48000
REF = BIBLIOTECA / "voz" / "referencia.wav"
REF_TXT = BIBLIOTECA / "voz" / "referencia.txt"
SCRIPT = Path(os.environ.get("VOZ_SERVIDOR", str(RAIZ / "worker" / "voz" / "voz_servidor.py")))
PYTHONS = {"qwen3": os.environ.get("VOZ_PYTHON_QWEN3", "/opt/voz/qwen3/bin/python"),
           "chatterbox": os.environ.get("VOZ_PYTHON_CHATTERBOX", "/opt/voz/chatterbox/bin/python")}
PESOS = {"qwen3": os.environ.get("QWEN3_PASTA", "qwen3_tts_base"), "chatterbox": "chatterbox_mtl"}
LIMITE_CHARS = 220
SEMELHANCA_MIN = float(os.environ.get("VOZ_SEMELHANCA_MIN", "0.80"))
TENTATIVAS = int(os.environ.get("VOZ_TENTATIVAS", "3"))


class _Servidor:
    def __init__(self, motor: str):
        self.motor, self.lock, self.proc = motor, threading.Lock(), None

    def _subir(self):
        env = {**os.environ, "VOZ_MODELOS": str(modelos.MODELOS / "voz"), "QWEN3_PASTA": PESOS["qwen3"]}
        self.proc = subprocess.Popen([PYTHONS[self.motor], str(SCRIPT), self.motor], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env, bufsize=1)
        pronto = self._ler()
        if not pronto.get("ok"):
            raise RuntimeError(f"servidor de voz {self.motor} não subiu: {pronto}")
        self.dispositivo = pronto.get("dispositivo")

    def _ler(self) -> dict:
        # ignora linhas que não são JSON (bibliotecas que imprimem no stdout)
        while True:
            linha = self.proc.stdout.readline()
            if not linha:
                raise RuntimeError(f"servidor de voz {self.motor} parou")
            linha = linha.strip()
            if linha.startswith("{"):
                try:
                    return json.loads(linha)
                except json.JSONDecodeError:
                    continue

    def pedir(self, pedido: dict) -> dict:
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                self._subir()
            self.proc.stdin.write(json.dumps(pedido, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
            return self._ler()


_servidores: dict[str, _Servidor] = {}


def disponivel(motor: str) -> tuple[bool, str]:
    if not REF.exists():
        return False, "sem voz de referência (cadastre em /voz/referencia)"
    if not Path(PYTHONS[motor]).exists():
        return False, f"ambiente do {motor} não instalado ({PYTHONS[motor]})"
    if not modelos.presente(PESOS[motor]) and os.environ.get("VOZ_BAIXAR_SOB_DEMANDA", "1") != "1":
        return False, "pesos do modelo não baixados"
    if not transcricao.disponivel():
        return False, "faster-whisper não instalado"
    return True, "ok"


def _servidor(motor: str) -> _Servidor:
    if not modelos.presente(PESOS[motor]):
        modelos.baixar(PESOS[motor])
    if motor not in _servidores:
        _servidores[motor] = _Servidor(motor)
    return _servidores[motor]


def _pedacos(texto: str) -> list[str]:
    frases = [f.strip() for f in re.split(r"(?<=[.!?…;])\s+", texto) if f.strip()]
    out, atual = [], ""
    for f in frases:
        if len(f) > LIMITE_CHARS:  # frase enorme: quebra nas vírgulas
            for p in re.split(r"(?<=,)\s+", f):
                if len(atual) + len(p) + 1 > LIMITE_CHARS and atual:
                    out.append(atual)
                    atual = p
                else:
                    atual = (atual + " " + p).strip()
            continue
        if len(atual) + len(f) + 1 > LIMITE_CHARS and atual:
            out.append(atual)
            atual = f
        else:
            atual = (atual + " " + f).strip()
    if atual:
        out.append(atual)
    return out


def _ler48k(arq: Path) -> np.ndarray:
    a, sr = sf.read(arq, dtype="float32")
    a = a if a.ndim == 1 else a.mean(axis=1)
    if sr != SR:
        a = np.interp(np.linspace(0, len(a) - 1, int(len(a) * SR / sr)), np.arange(len(a)), a).astype(np.float32)
    return a


def _aparar(a: np.ndarray, limiar: float = 0.012) -> tuple[np.ndarray, float]:
    idx = np.where(np.abs(a) > limiar)[0]
    if len(idx) == 0:
        return a, 0.0
    ini = max(0, idx[0] - int(0.02 * SR))
    return a[ini: idx[-1] + int(0.06 * SR)], ini / SR


def falar(texto: str, saida: Path, motor: str = "qwen3", semente: int = 7) -> dict:
    srv = _servidor(motor)
    ref_txt = REF_TXT.read_text(encoding="utf-8").strip() if REF_TXT.exists() else ""
    falado_total = texto_fala.preparar(texto)
    partes_orig = _pedacos(texto)
    partes_fala = [texto_fala.preparar(p) for p in partes_orig]
    audios, palavras, t, relatorio = [], [], 0.0, []
    tmp = saida.with_suffix(".parte.wav")
    for k, (orig, fala) in enumerate(zip(partes_orig, partes_fala)):
        melhor = None
        for tentativa in range(TENTATIVAS):
            r = srv.pedir({"cmd": "falar", "texto": fala, "saida": str(tmp), "ref": str(REF), "ref_texto": ref_txt,
                           "semente": semente + 1000 * tentativa})
            if not r.get("ok"):
                raise RuntimeError(f"voz clonada ({motor}) falhou: {r.get('erro')}")
            a, _ = _aparar(_ler48k(tmp))
            ouvidas = transcricao.transcrever((a, SR), fala)
            nota = transcricao.semelhanca(ouvidas, fala)
            # duração absurda também denuncia problema (repetição ou corte)
            esperado = max(0.6, len(fala) / 14.5)
            if not 0.45 < len(a) / SR / esperado < 2.2:
                nota *= 0.5
            if melhor is None or nota > melhor[0]:
                melhor = (nota, a, ouvidas)
            if nota >= SEMELHANCA_MIN:
                break
        nota, a, ouvidas = melhor
        relatorio.append({"parte": k, "semelhanca": round(nota, 3), "tentativas": tentativa + 1})
        palavras += [{"w": w["w"], "ini": round(w["ini"] + t, 3), "fim": round(w["fim"] + t, 3)}
                     for w in transcricao.alinhar(orig, ouvidas, len(a) / SR)]
        audios.append(a)
        t += len(a) / SR
        if k < len(partes_orig) - 1:
            pausa = 0.32 if orig.rstrip()[-1:] in ".!?…" else 0.16
            audios.append(np.zeros(int(pausa * SR), np.float32))
            t += pausa
    tmp.unlink(missing_ok=True)
    audio = np.concatenate(audios) if audios else np.zeros(SR, np.float32)
    pico = float(np.max(np.abs(audio)) or 1)
    audio = audio * min(1.0, 0.89 / pico)
    sf.write(saida, audio, SR)
    return {"arquivo": str(saida), "duracao": len(audio) / SR, "motor": f"clone_{motor}", "palavras_tts": palavras,
            "texto_falado": falado_total, "conferencia": relatorio}
