"""
Montagem final com FFmpeg:
  - transições entre cenas (xfade nativo ou gl-transitions)
  - mixagem: narração + efeitos (numpy, posição exata) + trilha com ducking (sidechain) + loudnorm
  - acabamento: textura de papel, grão de filme e vinheta sutis
  - descrição do YouTube com capítulos (0:00 ...) e créditos das músicas e efeitos usados
  - 16:9 com legenda em .srt (YouTube) e, se pedido, queimada
  - 9:16 composto: fundo desfocado, cena ampliada no meio, título fixo no topo, legenda palavra a palavra
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np

from ..config import BIBLIOTECA, LUFS_ALVO, RESOLUCAO, TEXTURA_PAPEL
from . import sons

SR = 48000
FONTES = "/usr/share/fonts/truetype/fabrica"
def _variar(x: np.ndarray, semente: str) -> np.ndarray:
    """Cada uso do mesmo efeito sai levemente diferente: tom ±4% e volume ±1,5 dB."""
    h = int(hashlib.md5(semente.encode()).hexdigest()[:8], 16)
    fator = 1 + ((h % 1000) / 1000 - 0.5) * 0.08
    ganho = 10 ** ((((h // 1000) % 1000) / 1000 - 0.5) * 3 / 20)
    n = max(1, int(len(x) / fator))
    return (np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x) * ganho).astype(np.float32)


def ff(*args: str):
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], capture_output=True, text=True)
    if r.returncode != 0:
        erro = (r.stderr or "").strip()
        print(f"[ffmpeg] falhou ({r.returncode}): {erro[-3000:]}", flush=True)
        motivo = "memória insuficiente (o processo foi encerrado)" if r.returncode in (-9, 137) else (erro.splitlines()[-1] if erro else f"código {r.returncode}")
        raise RuntimeError(f"FFmpeg falhou: {motivo[:400]}")


def _ler(arquivo: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(arquivo), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def _gravar(audio: np.ndarray, saida: Path):
    p = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", str(saida)],
                       input=np.clip(audio, -1, 1).astype(np.float32).tobytes(), check=True)
    return p


MASTER_VOZ = ("highpass=f=75,deesser=i=0.35:m=0.5:f=0.5:s=o,"
              "equalizer=f=220:t=q:w=1.0:g=-1.5,equalizer=f=3200:t=q:w=1.4:g=2,equalizer=f=9000:t=h:w=1:g=1,"
              "acompressor=threshold=-20dB:ratio=3:attack=6:release=90:makeup=2")


# ---------------------------------------------------------------- áudio
def audio(plano: dict, pasta: Path, clima: str = "reflexivo", com_trilha: bool = True, trilha_fixa: str | None = None) -> Path:
    total = int((plano["duracao"] + 0.5) * SR)
    narr, efx = np.zeros(total, np.float32), np.zeros(total, np.float32)
    usados = set()
    for c in plano["cenas"]:
        f = _ler(Path(c["fala"]["arquivo"]))
        i = int((c["inicio"] + c["fala"]["em"]) * SR)
        narr[i:i + len(f)] += f[: max(0, total - i)]
        sfx = list(c["sfx"])
        if c["transicao"] and c["cauda"] >= 0.1:  # som da transição centrado no corte (corte seco: sem som)
            sfx.append({"tipo": "transicao" if c["transicao"] != "fade" else "whoosh", "em": c["dur"] - c.get("corte", 0) + c["cauda"] / 2 - 0.15})
        for s in sfx:
            arq, ganho = sons.arquivo(s["tipo"], f"{c['indice']}-{s['tipo']}-{s['em']}")
            usados.add(str(arq))
            x = _variar(_ler(arq), f"{c['indice']}-{s['tipo']}-{s['em']}") * (10 ** (ganho / 20))
            j = int((c["inicio"] + s["em"]) * SR)
            if 0 <= j < total:
                efx[j:j + len(x)] += x[: total - j]
    _gravar(narr, pasta / "narracao_bruta.wav")
    # masterização da voz (cadeia de estúdio): corta graves de ruído, controla o "s" chiado,
    # tira o embolado dos médios-graves, dá presença e segura a dinâmica
    ff("-i", str(pasta / "narracao_bruta.wav"), "-af", MASTER_VOZ, "-ar", str(SR), str(pasta / "narracao.wav"))
    _gravar(efx, pasta / "efeitos.wav")

    trilha = sons.trilha(clima, plano["duracao"], pasta, trilha_fixa) if com_trilha else None
    if trilha:
        usados.add(str(trilha))
    # créditos que a licença exige (CC0 marcado com "credito_obrigatorio": false não entra na descrição)
    creditos = [c for c in (sons.credito_de(Path(u)) for u in sorted(usados)) if c and c.get("credito_obrigatorio", True)]
    (pasta / "creditos.json").write_text(json.dumps(creditos, ensure_ascii=False, indent=1))
    saida = pasta / "audio_final.wav"
    mix = pasta / "audio_mix.wav"
    if trilha:
        # trilha em loop, -22 dB de base, abaixa mais quando há voz (ducking), fade no fim
        d = plano["duracao"]
        ff("-i", str(pasta / "narracao.wav"), "-i", str(pasta / "efeitos.wav"), "-stream_loop", "-1", "-i", str(trilha),
           "-filter_complex",
           f"[2:a]atrim=0:{d},volume=-22dB,afade=in:d=2,afade=out:st={max(0, d - 3)}:d=3,aresample={SR}[m];"
           f"[0:a]asplit[v][sc];[m][sc]sidechaincompress=threshold=0.02:ratio=6:attack=15:release=350[md];"
           f"[v][1:a][md]amix=inputs=3:normalize=0[o]",
           "-map", "[o]", "-ar", str(SR), str(mix))
    else:
        ff("-i", str(pasta / "narracao.wav"), "-i", str(pasta / "efeitos.wav"),
           "-filter_complex", "[0:a][1:a]amix=inputs=2:normalize=0[o]", "-map", "[o]", "-ar", str(SR), str(mix))
    return _normalizar(mix, saida)


def _normalizar(entrada: Path, saida: Path) -> Path:
    """loudnorm em duas passadas: mede o áudio inteiro e depois corrige de forma linear (sem 'bombear')."""
    alvo = f"I={LUFS_ALVO}:TP=-1.5:LRA=11"
    # compressão leve + limitador antes: tira os picos dos efeitos, que impediam o ganho linear de chegar ao alvo
    preparado = entrada.with_name(entrada.stem + "_comp.wav")
    ff("-i", str(entrada), "-af", "acompressor=threshold=-20dB:ratio=2.5:attack=8:release=150:makeup=2,"
       "alimiter=limit=0.5:attack=2:release=60:level=false", "-ar", str(SR), str(preparado))
    entrada = preparado
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(entrada), "-af", f"loudnorm={alvo}:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True)
    txt = r.stderr
    m = json.loads(txt[txt.rindex("{"): txt.rindex("}") + 1])
    ff("-i", str(entrada), "-af",
       f"loudnorm={alvo}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
       f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true",
       "-ar", str(SR), str(saida))
    return saida


# ---------------------------------------------------------------- vídeo
def _xfade(clips: list[Path], cenas: list[dict], base: float, saida: Path, preset: str = "medium"):
    """Junta poucos clipes com transição. Offsets relativos ao início do primeiro clipe do grupo."""
    if len(clips) == 1:
        ff("-i", str(clips[0]), "-c", "copy", str(saida))
        return
    entradas = sum((["-i", str(c)] for c in clips), [])
    partes, atual = [], "[0:v]"
    for k in range(1, len(clips)):
        ant = cenas[k - 1]
        nome, d = ant["transicao"] or "fade", ant["cauda"] or 0.04
        off = round(cenas[k].get("v_inicio", cenas[k]["inicio"]) - base, 3)
        out = f"[v{k}]"
        partes.append(f"{atual}[{k}:v]xfade=transition={nome}:duration={d}:offset={off}{out}")
        atual = out
    ff(*entradas, "-filter_complex", ";".join(partes), "-map", atual, "-c:v", "libx264", "-preset", preset,
       "-crf", "16", "-pix_fmt", "yuv420p", str(saida))


def juntar(clips: list[Path], plano: dict, saida: Path, grupo: int = 8, nivel: int = 0) -> Path:
    """Encadeia as cenas com transição, em blocos de `grupo` cenas para caber na memória
    (65 cenas de uma vez passam de 5 GB). Cada bloco termina com a "cauda" da última cena,
    então a transição entre blocos é feita do mesmo jeito que entre cenas."""
    cenas = plano["cenas"]
    if len(clips) <= grupo:
        _xfade(clips, cenas, cenas[0].get("v_inicio", cenas[0]["inicio"]), saida)
        return saida
    blocos, info = [], []
    for g in range(0, len(clips), grupo):
        sub_c, sub_cl = cenas[g: g + grupo], clips[g: g + grupo]
        arq = saida.with_name(f"{saida.stem}_n{nivel}_bloco{g // grupo:02d}.mp4")
        _xfade(sub_cl, sub_c, sub_c[0].get("v_inicio", sub_c[0]["inicio"]), arq)
        blocos.append(arq)
        ult = sub_c[-1]
        info.append({"inicio": sub_c[0].get("v_inicio", sub_c[0]["inicio"]), "transicao": ult["transicao"], "cauda": ult["cauda"]})
    juntar(blocos, {"cenas": info}, saida, grupo, nivel + 1)
    for b in blocos:
        b.unlink(missing_ok=True)
    return saida

ACABAMENTO = "noise=alls=2:allf=t,vignette=angle=PI/7"


def textura_papel(w: int, h: int) -> Path:
    """Textura de papel gerada uma vez (ruído em várias escalas + fibras), cinza médio para mesclar em soft light."""
    arq = BIBLIOTECA / f"_textura_papel_{w}x{h}.png"
    if arq.exists():
        return arq
    rng = np.random.default_rng(42)
    tex = np.zeros((h, w), np.float32)
    for escala, peso in ((2, .5), (8, .3), (32, .2)):
        base = rng.standard_normal((h // escala + 2, w // escala + 2)).astype(np.float32)
        tex += peso * np.kron(base, np.ones((escala, escala), np.float32))[:h, :w]
    for _ in range(900):  # fibras
        x, y, comp, ang = rng.integers(0, w), rng.integers(0, h), rng.integers(20, 90), rng.uniform(0, np.pi)
        xs = np.clip((x + np.cos(ang) * np.arange(comp)).astype(int), 0, w - 1)
        ys = np.clip((y + np.sin(ang) * np.arange(comp)).astype(int), 0, h - 1)
        tex[ys, xs] += rng.uniform(.6, 1.4)
    tex = (tex - tex.mean()) / (tex.std() or 1)
    img = np.clip(128 + tex * 22, 0, 255).astype(np.uint8)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}", "-i", "-",
                    str(arq)], input=img.tobytes(), check=True)
    return arq


def _papel(entrada: str, w: int, h: int, idx: int) -> tuple[list[str], str, str]:
    """Devolve (args de entrada, filtro, rótulo de saída) para mesclar a textura de papel."""
    if TEXTURA_PAPEL <= 0:
        return [], "", entrada
    tex = textura_papel(w, h)
    filtro = (f"[{idx}:v]format=gbrp[tx];{entrada}format=gbrp[base];"
              f"[base][tx]blend=all_mode=softlight:all_opacity={TEXTURA_PAPEL}:shortest=1,format=yuv420p[papel];")
    return ["-loop", "1", "-i", str(tex)], filtro, "[papel]"


def final_169(video: Path, audio_: Path, saida: Path, legenda: Path | None = None) -> Path:
    h = RESOLUCAO
    w = int(round(h * 16 / 9 / 2) * 2)
    args_tex, f_tex, rot = _papel("[0:v]", w, h, 2)
    taxa = {1080: 16, 1440: 30, 2160: 60}.get(h, int(16 * (h / 1080) ** 2))
    vf = ACABAMENTO + (f",subtitles={legenda}:fontsdir={FONTES}" if legenda else "")
    ff("-i", str(video), "-i", str(audio_), *args_tex, "-filter_complex", f"{f_tex}{rot}{vf}[v]", "-map", "[v]", "-map", "1:a", "-c:v", "libx264",
       "-preset", "slow", "-crf", "20", "-maxrate", f"{taxa}M", "-bufsize", f"{taxa * 2}M", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-shortest",
       "-movflags", "+faststart", str(saida))
    return saida


def final_916(video: Path, audio_: Path, legenda_ass: Path, titulo: str, chapeu: str, saida: Path) -> Path:
    """Cena 16:9 ampliada (1404x790, corta as bordas) no meio de um fundo desfocado da própria cena."""
    linhas, atual = [], ""
    for w in titulo.upper().split():
        if len(atual) + len(w) + 1 > 16 and atual:
            linhas.append(atual)
            atual = w
        else:
            atual = (atual + " " + w).strip()
    linhas.append(atual)
    arq_tit = saida.with_suffix(".titulo.txt")
    arq_tit.write_text("\n".join(linhas[:3]), encoding="utf-8")
    cha = chapeu.replace("'", "’").replace(":", "\\:").upper()
    fonte_t = f"{FONTES}/BebasNeue-Regular.ttf"
    fonte_c = f"{FONTES}/BarlowCondensed-Bold.ttf"
    args_tex, f_tex, rot = _papel("[c]", 1080, 1920, 2)
    fc = (
        "[0:v]split[a][b];"
        "[a]scale=-2:1920,crop=1080:1920,boxblur=40:3,eq=brightness=-0.42:saturation=0.7[fundo];"
        "[b]scale=1404:-2,crop=1080:790[meio];"
        "[fundo][meio]overlay=0:470[c];"
        f"{f_tex}{rot}drawtext=fontfile={fonte_c}:text='{cha}':fontcolor=0xD7FF3A:fontsize=36:x=70:y=150,"
        f"drawtext=fontfile={fonte_t}:textfile={arq_tit}:fontcolor=white:fontsize=104:x=70:y=200:line_spacing=-6,"
        f"{ACABAMENTO},subtitles={legenda_ass}:fontsdir={FONTES}[v]"
    )
    ff("-i", str(video), "-i", str(audio_), *args_tex, "-filter_complex", fc, "-map", "[v]", "-map", "1:a",
       "-c:v", "libx264", "-preset", "slow", "-crf", "21", "-maxrate", "10M", "-bufsize", "20M", "-pix_fmt", "yuv420p", "-r", "30",
       "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(saida))
    return saida


# ---------------------------------------------------------------- legendas
def _ts(s: float, ass: bool = False) -> str:
    h, m, sec = int(s // 3600), int(s % 3600 // 60), s % 60
    return f"{h}:{m:02d}:{sec:05.2f}" if ass else f"{h:02d}:{m:02d}:{sec:06.3f}".replace(".", ",")


def _palavras_globais(plano: dict) -> list[dict]:
    out = []
    for c in plano["cenas"]:
        hot = {h.lower().strip(".,!?…") for h in c["destaques"]}
        for w in c["palavras"]:
            out.append({"w": w["w"], "ini": c["inicio"] + w["ini"], "fim": c["inicio"] + w["fim"],
                        "hot": w["w"].lower().strip(".,!?…") in hot, "cena": c["indice"]})
    return out


def srt(plano: dict, saida: Path, max_palavras: int = 9) -> Path:
    blocos, atual = [], []
    for w in _palavras_globais(plano):
        if atual and (len(atual) >= max_palavras or w["cena"] != atual[0]["cena"] or atual[-1]["w"][-1:] in ".!?"):
            blocos.append(atual)
            atual = []
        atual.append(w)
    if atual:
        blocos.append(atual)
    linhas = []
    for i, b in enumerate(blocos, 1):
        fim = b[-1]["fim"] + 0.2
        if i < len(blocos):
            fim = min(fim, blocos[i][0]["ini"] - 0.01)
        linhas.append(f"{i}\n{_ts(b[0]['ini'])} --> {_ts(fim)}\n{' '.join(w['w'] for w in b)}\n")
    saida.write_text("\n".join(linhas), encoding="utf-8")
    return saida


def ass_palavra_a_palavra(plano: dict, saida: Path, por_bloco: int = 3) -> Path:
    """Legenda vertical: blocos de até 3 palavras; a palavra falada fica lima (destaque: magenta)."""
    cab = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\n\n"
           "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
           "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
           "MarginL, MarginR, MarginV, Encoding\n"
           "Style: Leg,Barlow ExtraBold,86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,9,0,2,60,60,360,1\n\n"
           "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    ws = _palavras_globais(plano)
    blocos, atual = [], []
    for w in ws:
        if atual and (len(atual) >= por_bloco or w["cena"] != atual[0]["cena"] or atual[-1]["w"][-1:] in ".!?,"):
            blocos.append(atual)
            atual = []
        atual.append(w)
    if atual:
        blocos.append(atual)
    ev = []
    for n, b in enumerate(blocos):
        limite = blocos[n + 1][0]["ini"] if n + 1 < len(blocos) else 1e9
        for k, w in enumerate(b):
            ini = w["ini"]
            fim = b[k + 1]["ini"] if k + 1 < len(b) else min(w["fim"] + 0.25, limite)
            txt = []
            for j, x in enumerate(b):
                p = x["w"].upper().replace("{", "").replace("}", "")
                if j == k:
                    cor = "&H8C50F0&" if x["hot"] else "&H3AFFD7&"   # BGR: magenta F0508C / lima D7FF3A
                    txt.append(f"{{\\c{cor}\\fscx108\\fscy108}}{p}{{\\c&HFFFFFF&\\fscx100\\fscy100}}")
                else:
                    txt.append(p)
            ev.append(f"Dialogue: 0,{_ts(ini, True)},{_ts(fim, True)},Leg,,0,0,0,,{' '.join(txt)}")
    saida.write_text(cab + "\n".join(ev) + "\n", encoding="utf-8")
    return saida


# ---------------------------------------------------------------- descrição do YouTube
def _mmss(s: float) -> str:
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def descricao(plano: dict, titulo: str, creditos: list[dict], saida: Path) -> Path:
    """Capítulos clicáveis do YouTube (precisa começar em 0:00, ter 3+ capítulos de 10 s ou mais) e créditos."""
    caps = [(0.0, "Abertura")]
    for c in plano["cenas"]:
        if c.get("capitulo") and c.get("titulo_capitulo"):
            if c["inicio"] < 1:
                caps[0] = (0.0, c["titulo_capitulo"])
            elif c["inicio"] - caps[-1][0] >= 10:
                caps.append((c["inicio"], c["titulo_capitulo"]))
    linhas = [titulo, ""]
    if len(caps) >= 3:
        linhas += ["Capítulos"] + [f"{_mmss(t)} {nome}" for t, nome in caps] + [""]
    if creditos:
        linhas.append("Créditos de áudio")
        for c in creditos:
            partes = [c.get("titulo"), f"por {c['autor']}" if c.get("autor") else None, c.get("fonte"), c.get("licenca"), c.get("url")]
            linhas.append("· " + " · ".join(p for p in partes if p))
    saida.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return saida
