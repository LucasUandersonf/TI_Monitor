"""
Efeitos sonoros e trilha.

Só arquivos locais, sem nenhuma API de busca. Cada efeito (categoria, ex.: "pop") vem de:
  1. volume do worker   dados/biblioteca/sfx/<categoria>/*.wav|ogg|mp3|flac  (ex.: gerados pela ElevenLabs uma vez)
  2. pasta do repositório  sons/sfx/<categoria>/                               (os que você escolheu e subiu no git)
  3. síntese própria    sons desenhados em numpy (pop, whoosh, moeda, ding, caixa registradora...)

Trilha: opção "trilha_arquivo" (caminho ou link) -> biblioteca/trilha/<clima>/ -> sons/trilha/<clima>/ -> sons/trilha/
        -> sem trilha (o vídeo sai só com voz e efeitos)

Um "<arquivo>.credito.json" ao lado do arquivo (fonte, autor, licença) vai para a descrição do vídeo.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import numpy as np
import soundfile as sf

from ..config import BIBLIOTECA, SONS_REPO

SR = 48000
EXT = (".wav", ".ogg", ".mp3", ".flac")

# categoria -> (descrição, ganho em dB)
CATEGORIAS = {
    "pop":                ("short soft cartoon pop, clean ui sound", -13),
    "whoosh":             ("fast airy whoosh transition, cinematic", -15),
    "whoosh_grave":       ("deep low cinematic whoosh, sub swell", -14),
    "risco_caneta":       ("felt marker drawing a quick line on paper", -17),
    "papel":              ("paper being crumpled and tossed", -15),
    "impacto":            ("deep cinematic impact boom, short tail", -11),
    "baque":              ("heavy soft thud on wooden floor", -12),
    "tick":               ("soft clock tick, subtle ui", -19),
    "ding":               ("single clean bell ding", -15),
    "notificacao":        ("smartphone notification two note chime", -15),
    "moeda":              ("single metal coin drop on table", -15),
    "caixa_registradora": ("old cash register cha-ching with bell", -14),
    "transicao":          ("short riser into swoosh transition", -16),
    "bip":                ("single electronic beep", -17),
    "drone":              ("dark low ambient drone, slow", -23),
    "glitch":             ("short digital glitch stutter", -17),
    "riser":              ("tension riser building up", -18),
    "digitar":            ("short burst of keyboard typing", -19),
}
APELIDOS = {"impacto_grave": "impacto", "transicao_capitulo": "impacto", "papel_amassado": "papel",
            "drone_grave": "drone", "whoosh_curto": "whoosh", "slide": "whoosh", "dinheiro": "moeda",
            "sino": "ding", "queda": "baque", "relogio": "tick", "digitacao": "digitar", "coracao": "baque",
            "bipe": "bip", "censura": "bip", "beep": "bip", "erro": "glitch", "tensao": "riser", "subida": "riser",
            "teclado": "digitar", "swoosh": "whoosh", "hit": "impacto", "boom": "impacto", "click": "tick", "clique": "tick"}


# ---------------------------------------------------------------- síntese própria
def _t(seg: float) -> np.ndarray:
    return np.arange(int(seg * SR)) / SR


def _env(t: np.ndarray, ataque: float, decai: float) -> np.ndarray:
    return np.minimum(1, t / max(ataque, 1e-4)) * np.exp(-np.maximum(0, t - ataque) / decai)


def _seno_varrido(t, f0, f1):
    f = f0 * (f1 / f0) ** (t / t[-1])
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def _filtro_passa_baixa(x, corte):
    """Passa-baixa de um polo com corte que pode variar no tempo (array ou número)."""
    corte = np.broadcast_to(np.asarray(corte, dtype=np.float64), x.shape)
    a = np.exp(-2 * np.pi * corte / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1 - a[i]) * x[i] + a[i] * acc
        y[i] = acc
    return y


def _ruido(seg, semente=1):
    return np.random.default_rng(semente).standard_normal(int(seg * SR))


def _sino(t, f, parciais=((1, 1), (2.76, .4), (5.4, .2), (8.9, .08)), decai=0.9):
    return sum(a * np.sin(2 * np.pi * f * m * t) * np.exp(-t / (decai / m ** 0.5)) for m, a in parciais)


def sintetizar(cat: str) -> np.ndarray:
    if cat == "pop":
        t = _t(0.12)
        x = _seno_varrido(t, 1300, 380) * _env(t, 0.002, 0.035) + 0.15 * _ruido(0.12) * _env(t, 0.001, 0.004)
    elif cat in ("whoosh", "transicao"):
        d = 0.55 if cat == "whoosh" else 0.8
        t = _t(d)
        corte = 300 + 5000 * np.sin(np.pi * t / d) ** 2
        x = _filtro_passa_baixa(_ruido(d, 2), corte) * 3
        x -= _filtro_passa_baixa(x, 250)
        x *= np.sin(np.pi * t / d) ** (1.5 if cat == "whoosh" else 3)
    elif cat == "whoosh_grave":
        t = _t(1.0)
        x = 2.5 * _filtro_passa_baixa(_ruido(1.0, 3), 300 + 700 * np.sin(np.pi * t)) + 0.6 * _seno_varrido(t, 90, 38)
        x *= np.sin(np.pi * t) ** 2
    elif cat == "risco_caneta":
        t = _t(0.4)
        r = _ruido(0.4, 4)
        x = (r - _filtro_passa_baixa(r, 2500)) * (0.6 + 0.4 * np.sin(2 * np.pi * 23 * t) ** 2) * np.sin(np.pi * t / 0.4)
    elif cat == "papel":
        t = _t(0.5)
        rng = np.random.default_rng(5)
        x = np.zeros_like(t)
        for p in rng.uniform(0, 0.45, 60):
            i = int(p * SR)
            n = rng.integers(80, 400)
            x[i:i + n] += rng.standard_normal(min(n, len(x) - i)) * rng.uniform(.2, 1)
        x = x - _filtro_passa_baixa(x, 1500)
        x *= _env(t, 0.01, 0.25)
    elif cat == "impacto":
        t = _t(1.4)
        x = 1.2 * _seno_varrido(t, 75, 32) * _env(t, 0.003, 0.45) + 0.8 * _filtro_passa_baixa(_ruido(1.4, 6), 900) * _env(t, 0.001, 0.08)
    elif cat == "baque":
        t = _t(0.45)
        x = _seno_varrido(t, 140, 48) * _env(t, 0.002, 0.09) + 0.5 * _filtro_passa_baixa(_ruido(0.45, 7), 1200) * _env(t, 0.001, 0.02)
    elif cat == "tick":
        t = _t(0.04)
        x = np.sin(2 * np.pi * 3200 * t) * _env(t, 0.0005, 0.006)
    elif cat == "ding":
        t = _t(1.6)
        x = _sino(t, 1320)
    elif cat == "notificacao":
        t = _t(1.0)
        x = _sino(t, 988, decai=0.5)
        x[int(0.13 * SR):] += _sino(t[: len(t) - int(0.13 * SR)], 1319, decai=0.6)
    elif cat == "moeda":
        t = _t(0.9)
        parc = ((1, 1), (1.47, .7), (2.13, .5), (3.1, .3))
        x = _sino(t, 2100, parc, decai=0.35)
        x[int(0.09 * SR):] += 0.6 * _sino(t[: len(t) - int(0.09 * SR)], 2180, parc, decai=0.25)
    elif cat == "caixa_registradora":
        t = _t(1.6)
        rng = np.random.default_rng(9)
        mec = np.zeros_like(t)
        for p in np.linspace(0, 0.25, 9) + rng.uniform(0, .01, 9):
            i = int(p * SR)
            mec[i:i + 300] += rng.standard_normal(300) * np.exp(-np.arange(300) / 60)
        x = 0.7 * (mec - _filtro_passa_baixa(mec, 1800))
        i = int(0.3 * SR)
        x[i:] += _sino(t[: len(t) - i], 2637, decai=0.8)
        m = np.concatenate([np.zeros(int(0.32 * SR)), sintetizar("moeda")])[: len(x)]
        x[: len(m)] += 0.5 * m
    elif cat == "bip":
        t = _t(0.14)
        x = np.sign(np.sin(2 * np.pi * 1000 * t)) * 0.4 * _env(t, 0.003, 0.08)
    elif cat == "drone":
        t = _t(5.0)
        x = (np.sin(2 * np.pi * 55 * t) + 0.7 * np.sin(2 * np.pi * 55.6 * t) + 0.3 * np.sin(2 * np.pi * 110.3 * t))
        x *= (0.75 + 0.25 * np.sin(2 * np.pi * 0.3 * t)) * np.minimum(1, t / 1.2) * np.minimum(1, (5 - t) / 1.5)
    elif cat == "glitch":
        t = _t(0.5)
        rng = np.random.default_rng(11)
        bloco = int(0.025 * SR)
        x = np.repeat(rng.standard_normal(len(t) // bloco + 1), bloco)[: len(t)] * np.sign(np.sin(2 * np.pi * 180 * t))
        x *= (rng.random(len(t) // bloco + 1).repeat(bloco)[: len(t)] > 0.35) * _env(t, 0.001, 0.25)
    elif cat == "riser":
        t = _t(2.0)
        x = _seno_varrido(t, 120, 900) * (t / 2.0) ** 2 + 0.4 * _ruido(2.0, 12) * (t / 2.0) ** 3
    elif cat == "digitar":
        t = _t(0.9)
        rng = np.random.default_rng(13)
        x = np.zeros_like(t)
        for p in np.cumsum(rng.uniform(0.05, 0.11, 14)):
            i = int(p * SR)
            if i + 400 < len(x):
                x[i:i + 400] += rng.standard_normal(400) * np.exp(-np.arange(400) / 50)
    else:
        return sintetizar("pop")
    x = np.asarray(x, dtype=np.float64)
    return (x / (np.max(np.abs(x)) or 1) * 0.9).astype(np.float32)


# ---------------------------------------------------------------- busca
def _cache(cat: str) -> Path:
    p = BIBLIOTECA / "sfx" / cat
    p.mkdir(parents=True, exist_ok=True)
    return p


def _arquivos(pasta: Path) -> list[Path]:
    if not pasta.is_dir():
        return []
    return sorted(p for p in pasta.iterdir() if p.suffix.lower() in EXT and not p.name.startswith("_"))


def credito_de(arq: Path) -> dict | None:
    c = Path(str(arq) + ".credito.json")
    return json.loads(c.read_text()) if c.exists() else None


def _sintese(cat: str) -> Path:
    dest = _cache(cat) / "_sintetico.wav"
    if not dest.exists():
        sf.write(dest, sintetizar(cat), SR)
    return dest


def arquivo(nome: str, semente: str = "") -> tuple[Path, float]:
    """Devolve (arquivo, ganho_db) para um efeito. Varia o arquivo dentro da categoria pela semente."""
    cat = APELIDOS.get(nome, nome)
    if cat not in CATEGORIAS:
        cat = "pop"
    opcoes = _arquivos(_cache(cat)) + _arquivos(SONS_REPO / "sfx" / cat) or [_sintese(cat)]
    k = int(hashlib.md5(semente.encode()).hexdigest(), 16) % len(opcoes)
    return opcoes[k], CATEGORIAS[cat][1]


# ---------------------------------------------------------------- trilha
def trilha(clima: str, duracao: float, pasta_job: Path, arquivo_fixo: str | None = None) -> Path | None:
    """arquivo_fixo: caminho ou URL de uma trilha escolhida por você (opção 'trilha_arquivo').
    Sem ela, sorteia (fixo por vídeo) uma faixa da pasta do clima; sem nenhuma faixa, devolve None."""
    if arquivo_fixo:
        if arquivo_fixo.startswith("http"):
            dest = pasta_job / ("trilha_escolhida" + (Path(arquivo_fixo.split("?")[0]).suffix or ".mp3"))
            dest.write_bytes(httpx.get(arquivo_fixo, timeout=60, follow_redirects=True).content)
            return dest
        for p in (Path(arquivo_fixo), BIBLIOTECA / "trilha" / arquivo_fixo, SONS_REPO / "trilha" / arquivo_fixo):
            if p.exists():
                return p
    for p in (BIBLIOTECA / "trilha" / clima, SONS_REPO / "trilha" / clima, BIBLIOTECA / "trilha", SONS_REPO / "trilha"):
        faixas = sorted(f for f in p.rglob("*") if f.suffix.lower() in EXT) if p.is_dir() else []
        if faixas:
            return faixas[int(hashlib.md5(pasta_job.name.encode()).hexdigest(), 16) % len(faixas)]
    return None
