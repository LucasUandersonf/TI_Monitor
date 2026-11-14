"""
Efeitos sonoros e trilha.

Cada efeito (categoria, ex.: "pop") é buscado nesta ordem:
  1. biblioteca local  dados/biblioteca/sfx/<categoria>/*.wav|ogg|mp3   (Kenney + Sonniss, sincronizada do Drive)
  2. Freesound API     só licença CC0, salva no cache da categoria          (FREESOUND_API_KEY)
  3. Stable Audio Open gera pelo texto, salva no cache                       (GPU)
  4. síntese própria   sons desenhados em numpy (pop, whoosh, moeda, ding, caixa registradora...)

Trilha: biblioteca/trilha/<clima>/  ->  ACE-Step (ACE_STEP_CMD)  ->  Openverse (CC0/CC-BY, com crédito)

Todo arquivo baixado ganha um "<arquivo>.credito.json"; a edição junta os créditos usados na descrição do vídeo.
"""
from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
from pathlib import Path

import httpx
import numpy as np
import soundfile as sf

from ..config import ACE_STEP_CMD, BIBLIOTECA, FREESOUND_TOKEN, OPENVERSE_ATIVO

SR = 48000
EXT = (".wav", ".ogg", ".mp3", ".flac")

# categoria -> (busca no Freesound, prompt do Stable Audio, ganho em dB)
CATEGORIAS = {
    "pop":                ("pop bubble ui", "short soft cartoon pop, clean ui sound", -13),
    "whoosh":             ("whoosh swoosh fast", "fast airy whoosh transition, cinematic", -15),
    "whoosh_grave":       ("deep whoosh cinematic", "deep low cinematic whoosh, sub swell", -14),
    "risco_caneta":       ("marker pen writing scribble", "felt marker drawing a quick line on paper", -17),
    "papel":              ("paper crumple throw", "paper being crumpled and tossed", -15),
    "impacto":            ("cinematic hit boom", "deep cinematic impact boom, short tail", -11),
    "baque":              ("thud body fall", "heavy soft thud on wooden floor", -12),
    "tick":               ("ui tick click soft", "soft clock tick, subtle ui", -19),
    "ding":               ("bell ding single", "single clean bell ding", -15),
    "notificacao":        ("phone notification ding", "smartphone notification two note chime", -15),
    "moeda":              ("coin drop single", "single metal coin drop on table", -15),
    "caixa_registradora": ("cash register cha ching", "old cash register cha-ching with bell", -14),
    "transicao":          ("transition swoosh riser short", "short riser into swoosh transition", -16),
    "bip":                ("lab beep", "single electronic beep", -17),
    "drone":              ("dark ambient drone", "dark low ambient drone, slow", -23),
}
APELIDOS = {"impacto_grave": "impacto", "transicao_capitulo": "impacto", "papel_amassado": "papel",
            "drone_grave": "drone", "whoosh_curto": "whoosh", "slide": "whoosh", "dinheiro": "moeda",
            "sino": "ding", "queda": "baque", "relogio": "tick", "digitacao": "tick", "coracao": "baque"}


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
    else:
        return sintetizar("pop")
    x = np.asarray(x, dtype=np.float64)
    return (x / (np.max(np.abs(x)) or 1) * 0.9).astype(np.float32)


# ---------------------------------------------------------------- busca
def _cache(cat: str) -> Path:
    p = BIBLIOTECA / "sfx" / cat
    p.mkdir(parents=True, exist_ok=True)
    return p


def _credito(arq: Path, dados: dict):
    Path(str(arq) + ".credito.json").write_text(json.dumps(dados, ensure_ascii=False))


def credito_de(arq: Path) -> dict | None:
    c = Path(str(arq) + ".credito.json")
    return json.loads(c.read_text()) if c.exists() else None


def _freesound(cat: str) -> Path | None:
    if not FREESOUND_TOKEN:
        return None
    try:
        r = httpx.get("https://freesound.org/apiv2/search/text/", timeout=20, params={
            "query": CATEGORIAS[cat][0], "filter": 'license:"Creative Commons 0" duration:[0.05 TO 4]',
            "fields": "id,name,previews,license,username,url", "sort": "rating_desc", "page_size": 5,
            "token": FREESOUND_TOKEN})
        r.raise_for_status()
        for s in r.json().get("results", []):
            url = s["previews"].get("preview-hq-mp3")
            if url:
                dest = _cache(cat) / f"freesound_{s['id']}.mp3"
                dest.write_bytes(httpx.get(url, timeout=30).content)
                _credito(dest, {"fonte": "Freesound", "titulo": s["name"], "autor": s["username"],
                                "licenca": "CC0", "url": s.get("url")})
                return dest
    except Exception:
        return None
    return None


def _stable_audio(cat: str) -> Path | None:
    try:
        import torch
        if not torch.cuda.is_available():
            return None
        from diffusers import StableAudioPipeline
        pipe = StableAudioPipeline.from_pretrained("stabilityai/stable-audio-open-1.0", torch_dtype=torch.float16).to("cuda")
        audio = pipe(CATEGORIAS[cat][1], negative_prompt="low quality, music, voice", num_inference_steps=100,
                     audio_end_in_s=2.0, num_waveforms_per_prompt=1).audios[0]
        dest = _cache(cat) / "stableaudio_1.wav"
        sf.write(dest, audio.T.float().cpu().numpy(), pipe.vae.sampling_rate)
        _credito(dest, {"fonte": "Stable Audio Open (gerado)", "licenca": "Stability AI Community License"})
        return dest
    except Exception:
        return None


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
    opcoes = sorted(p for p in _cache(cat).iterdir() if p.suffix in EXT and not p.name.startswith("_"))
    if not opcoes:
        achado = _freesound(cat) or _stable_audio(cat)
        opcoes = [achado] if achado else [_sintese(cat)]
    k = int(hashlib.md5(semente.encode()).hexdigest(), 16) % len(opcoes)
    return opcoes[k], CATEGORIAS[cat][2]


# ---------------------------------------------------------------- trilha
BUSCA_TRILHA = {"reflexivo": "lofi chill piano", "misterio": "dark ambient mysterious", "tensao": "cinematic tension pulse"}
PROMPT_ACE = {"misterio": "dark ambient, lo-fi, soft piano, mysterious, 80 bpm, instrumental",
              "reflexivo": "lo-fi chillhop, warm rhodes, vinyl crackle, 75 bpm, instrumental",
              "tensao": "cinematic pulse, minimal synth, building tension, 90 bpm, instrumental"}


def _openverse(clima: str, duracao: float) -> Path | None:
    if not OPENVERSE_ATIVO:
        return None
    pasta = BIBLIOTECA / "trilha" / clima
    pasta.mkdir(parents=True, exist_ok=True)
    try:
        r = httpx.get("https://api.openverse.org/v1/audio/", timeout=20, headers={"User-Agent": "fabrica-cult/1.0"},
                      params={"q": BUSCA_TRILHA.get(clima, clima), "license": "cc0,by", "category": "music",
                              "length": "long", "mature": "false", "page_size": 20})
        r.raise_for_status()
        for a in r.json().get("results", []):
            if (a.get("duration") or 0) < 90_000 or not a.get("url"):
                continue
            ext = Path(a["url"].split("?")[0]).suffix or ".mp3"
            dest = pasta / f"openverse_{a['id']}{ext}"
            dest.write_bytes(httpx.get(a["url"], timeout=60, follow_redirects=True).content)
            _credito(dest, {"fonte": "Openverse", "titulo": a.get("title"), "autor": a.get("creator"),
                            "licenca": f"{a.get('license', '').upper()} {a.get('license_version', '')}".strip(),
                            "url": a.get("foreign_landing_url") or a.get("url")})
            return dest
    except Exception:
        return None
    return None


def _ace_step(clima: str, duracao: float, pasta_job: Path) -> Path | None:
    if not ACE_STEP_CMD:
        return None
    saida = pasta_job / "trilha_acestep.wav"
    cmd = ACE_STEP_CMD.format(prompt=shlex.quote(PROMPT_ACE.get(clima, clima)), duracao=int(min(duracao, 240)),
                              saida=shlex.quote(str(saida)))
    if subprocess.run(cmd, shell=True).returncode == 0 and saida.exists():
        _credito(saida, {"fonte": "ACE-Step (gerado)", "licenca": "Apache-2.0"})
        return saida
    return None


def trilha(clima: str, duracao: float, pasta_job: Path, arquivo_fixo: str | None = None) -> Path | None:
    """arquivo_fixo: caminho ou URL de uma trilha escolhida por você (campo 'trilha' nas opções)."""
    if arquivo_fixo:
        if arquivo_fixo.startswith("http"):
            dest = pasta_job / ("trilha_escolhida" + (Path(arquivo_fixo.split("?")[0]).suffix or ".mp3"))
            dest.write_bytes(httpx.get(arquivo_fixo, timeout=60, follow_redirects=True).content)
            return dest
        if Path(arquivo_fixo).exists():
            return Path(arquivo_fixo)
    base = BIBLIOTECA / "trilha"
    for p in (base / clima, base):
        if p.exists():
            faixas = sorted(f for f in p.rglob("*") if f.suffix in EXT)
            if faixas:
                return faixas[int(hashlib.md5(pasta_job.name.encode()).hexdigest(), 16) % len(faixas)]
    return _ace_step(clima, duracao, pasta_job) or _openverse(clima, duracao)
