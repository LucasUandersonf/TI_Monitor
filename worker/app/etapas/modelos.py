"""
Baixa pesos de modelos direto do Hugging Face (só os arquivos necessários, uma vez, para MODELOS/).
Usado no build do Docker (docker/baixar_modelos.sh) e, se faltar algo, na primeira vez que o modelo é usado.
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx

from ..config import MODELOS_VOZ as MODELOS

CATALOGO = {
    # faster-whisper small (CTranslate2): tempo de cada palavra e conferência da voz, em CPU
    "whisper_small": ("Systran/faster-whisper-small", ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"]),
}


def pasta(nome: str) -> Path:
    return MODELOS / nome


def presente(nome: str) -> bool:
    repo, arquivos = CATALOGO[nome]
    return all((pasta(nome) / a).exists() for a in arquivos)


def baixar(nome: str) -> Path:
    repo, arquivos = CATALOGO[nome]
    destino = pasta(nome)
    cab = {"Authorization": f"Bearer {os.environ['HF_TOKEN']}"} if os.environ.get("HF_TOKEN") else {}
    with httpx.Client(timeout=httpx.Timeout(60, read=600), follow_redirects=True, headers=cab) as c:
        for a in arquivos:
            alvo = destino / a
            if alvo.exists() and alvo.stat().st_size > 0:
                continue
            alvo.parent.mkdir(parents=True, exist_ok=True)
            tmp = alvo.with_suffix(alvo.suffix + ".parcial")
            with c.stream("GET", f"https://huggingface.co/{repo}/resolve/main/{a}") as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for bloco in r.iter_bytes(1 << 20):
                        f.write(bloco)
            tmp.rename(alvo)
    return destino


if __name__ == "__main__":
    import sys
    for n in sys.argv[1:]:
        print(n, "->", baixar(n))
