"""
Edição de um EPISÓDIO EM CENAS: uma pasta com cena-01.mp4 … cena-NN.mp4 (já animadas, sem som)
e um fichas.json com a narração, os destaques e a parte de cada cena.

  fichas.json ─► narração de cada cena (sua voz clonada / Kokoro / ElevenLabs), conferida pelo Whisper
     ─► tempo de cada palavra
     ─► cada vídeo é ajustado ao tempo da fala: acelera ou desacelera um pouco (0,8× a 1,35×)
        e, se ainda faltar, segura o último quadro
     ─► punch-in nas palavras de destaque, tremor na abertura de cada parte
     ─► efeitos sonoros: detectados no movimento de cada vídeo (algo surge → pop, algo desliza → whoosh),
        os pedidos no campo "efeito_sonoro" da ficha (ex.: 'bipe antes de "Com todo respeito"')
        e impacto na abertura de cada parte
     ─► transições (dissolve curto entre cenas, transição forte na troca de parte)
     ─► trilha com ducking, masterização da voz, −14 LUFS, textura de papel, grão
     ─► longo_16x9.mp4 + .srt + descrição do YouTube com capítulos (uma por "parte")
     ─► shorts 9:16 com legenda palavra a palavra
"""
from __future__ import annotations

import json
import re
import subprocess
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np

from . import jobs
from .config import FPS, RENDER_PARALELO, RESOLUCAO
from .etapas import alinhamento, montagem, narracao, shorts
from .etapas.sfx_texto import do_texto as _sfx_da_ficha

PADRAO = {"shorts": True, "max_shorts": 3, "clima_trilha": "reflexivo", "trilha": True, "trilha_arquivo": None,
          "legenda_queimada_longo": False, "preset": "medium"}
REGRAS = {
    "respiro": 0.2, "respiro_parte": 0.5, "pausa": 0.3,
    "vel_min": 0.8, "vel_max": 1.35,            # quanto o vídeo de uma cena pode ser esticado/acelerado
    "punch_forca": 1.045, "punch_intervalo_min": 1.2,
    "transicao_parte": ("circleopen", 0.6), "transicao_cena": ("fade", 0.25), "transicao_short": ("fade", 0.18),
    "sfx_max_por_cena": 4, "sfx_intervalo_min": 0.35,
}


def _ffprobe(arq: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(arq)],
                       capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    s = d["streams"][0]
    n, m = s["r_frame_rate"].split("/")
    return {"dur": float(d["format"]["duration"]), "w": s["width"], "h": s["height"], "fps": float(n) / float(m or 1)}


def ler_fichas(fichas: dict, pasta: Path) -> tuple[dict, list[dict], list[str]]:
    avisos, cenas = [], []
    for k, f in enumerate(fichas.get("cenas", [])):
        arq = pasta / Path(f.get("arquivo") or f"cena-{k + 1:02d}.mp4").name
        if not arq.exists():
            raise RuntimeError(f"cena {f.get('cena', k + 1)}: arquivo {arq.name} não chegou")
        p = f.get("parametros") or {}
        src = str(p.get("src") or "")
        if "conferir" in src.lower():
            avisos.append(f"cena {f.get('cena', k + 1)}: fonte do dado marcada para conferir antes de publicar")
        if not (f.get("narracao") or "").strip():
            avisos.append(f"cena {f.get('cena', k + 1)}: sem narração")
        cenas.append({"indice": k, "numero": f.get("cena", k + 1), "arquivo": str(arq), "narracao": (f.get("narracao") or "").strip(),
                      "destaques": f.get("destaques") or [], "parte": f.get("parte") or "", "molde": f.get("molde"),
                      "dur_ficha": float(f.get("duracao_s") or 0), "efeito_sonoro": f.get("efeito_sonoro"), "parametros": p})
    meta = {"titulo": fichas.get("episodio") or fichas.get("titulo") or pasta.name}
    return meta, cenas, avisos


# ---------------------------------------------------------------- movimento -> efeitos
def movimento(arq: Path, fps: int = 15) -> list[tuple[float, str]]:
    """Analisa o vídeo em miniatura: picos de mudança entre quadros = algo apareceu (pop) ou deslizou (whoosh)."""
    w, h = 160, 90
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(arq), "-vf", f"fps={fps},scale={w}:{h},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    q = np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(np.float32)
    if len(q) < 3:
        return []
    d = np.abs(np.diff(q, axis=0)).mean(axis=(1, 2))            # mudança média por quadro
    base = max(np.median(d), 0.15)
    limiar = max(base * 4, 1.2)
    eventos, i = [], 1
    while i < len(d) - 1:
        if d[i] > limiar and d[i] >= d[i - 1] and d[i] >= d[i + 1]:
            # volta até onde o movimento começou e vai até onde terminou
            a = i
            while a > 0 and d[a - 1] > limiar * 0.25:
                a -= 1
            b = i
            while b < len(d) - 1 and d[b + 1] > limiar * 0.25:
                b += 1
            dura = (b - a + 1) / fps
            if dura >= 0.2:            # deslizou / entrou em movimento: whoosh no começo do movimento
                t, tipo = a / fps + 0.02, "whoosh"
            else:                      # surgiu de repente: pop no pico
                t, tipo = (i + 1) / fps - 0.03, "pop"
            if t > 0.15:
                eventos.append((round(t, 3), tipo))
            i = b + 1
        else:
            i += 1
    filtrados = []
    for t, tipo in eventos:
        if not filtrados or t - filtrados[-1][0] >= REGRAS["sfx_intervalo_min"]:
            filtrados.append((t, tipo))
    return filtrados[: REGRAS["sfx_max_por_cena"]]


# ---------------------------------------------------------------- plano
def montar_plano(cenas: list[dict], falas: list[dict], infos: list[dict], movs: list[list], curto: bool = False) -> dict:
    out, t = [], 0.0
    for k, (c, f, info, mov) in enumerate(zip(cenas, falas, infos, movs)):
        nova_parte = k == 0 or c["parte"] != cenas[k - 1]["parte"]
        respiro = REGRAS["respiro_parte"] if nova_parte and not curto and k > 0 else REGRAS["respiro"]
        precisa = respiro + f["duracao"] + REGRAS["pausa"]
        vel = min(REGRAS["vel_max"], max(REGRAS["vel_min"], precisa / info["dur"]))
        dur = round(max(precisa, info["dur"] * vel), 3)
        ws = [{"w": w["w"], "ini": w["ini"] + respiro, "fim": w["fim"] + respiro} for w in f["palavras"]]
        movimento_cam = []
        for h in c["destaques"]:
            m = alinhamento.momento(ws, h)
            if m is not None and all(abs(m - x["em"]) >= REGRAS["punch_intervalo_min"] for x in movimento_cam):
                movimento_cam.append({"tipo": "punch", "em": round(m, 3), "forca": REGRAS["punch_forca"]})
        if nova_parte and k > 0 and not curto:
            movimento_cam.append({"tipo": "tremor", "em": 0.3, "forca": 7, "dur": 0.3})
        sfx = [{"tipo": tipo, "em": round(tm * vel, 3), "origem": "movimento"} for tm, tipo in mov if tm * vel < dur - 0.2]
        sfx += _sfx_da_ficha(c.get("efeito_sonoro"), ws, f["duracao"], respiro)
        if nova_parte and k > 0 and not curto:
            sfx.append({"tipo": "impacto", "em": 0.3, "origem": "parte"})
        sfx.sort(key=lambda s: s["em"])
        prox = cenas[k + 1] if k + 1 < len(cenas) else None
        if prox is None:
            trans = (None, 0.0)
        elif curto:
            trans = REGRAS["transicao_short"]
        else:
            trans = REGRAS["transicao_parte"] if prox["parte"] != c["parte"] else REGRAS["transicao_cena"]
        out.append({
            "indice": c["indice"], "global": k, "numero": c["numero"], "arquivo": c["arquivo"], "inicio": round(t, 3),
            "dur": dur, "velocidade": round(vel, 4),
            "dur_video": info["dur"], "cauda": trans[1], "transicao": trans[0],
            "capitulo": nova_parte, "titulo_capitulo": c["parte"] if nova_parte else None,
            "fala": {"arquivo": f["arquivo"], "em": respiro, "duracao": f["duracao"]},
            "palavras": ws, "destaques": c["destaques"], "movimento": movimento_cam, "sfx": sfx,
        })
        t += dur
    return {"duracao": round(t, 3), "cenas": out}


# ---------------------------------------------------------------- vídeo de cada cena
def _expr_zoom(movs: list[dict]) -> str:
    termos = []
    for m in movs:
        e = m["em"]
        if m["tipo"] == "punch":
            a = m.get("forca", 1.045) - 1
            r = f"clip((t-{e - 0.12:.3f})/0.12\\,0\\,1)"
            d = f"if(gt(t\\,{e + 0.5:.3f})\\,clip(1-(t-{e + 0.5:.3f})/0.7\\,0\\,1)\\,1)"
            termos.append(f"{a:.4f}*pow({r}*{d}\\,2)*(3-2*{r}*{d})")
        elif m["tipo"] == "tremor":
            termos.append(f"0.03*between(t\\,{e - 0.02:.3f}\\,{e + m.get('dur', 0.3) + 0.1:.3f})")
    return "1" + "".join("+" + x for x in termos)


def _expr_tremor(movs: list[dict], eixo: str) -> str:
    for m in movs:
        if m["tipo"] == "tremor":
            e, d, amp = m["em"], m.get("dur", 0.3), m.get("forca", 7) * RESOLUCAO / 1080
            onda = f"sin(97*t)" if eixo == "x" else f"0.7*cos(83*t)"
            return f"+{amp:.1f}*{onda}*clip(1-(t-{e:.3f})/{d:.3f}\\,0\\,1)*gte(t\\,{e:.3f})"
    return ""


def preparar_cena(c: dict, saida: Path, preset: str = "medium") -> Path:
    H = RESOLUCAO
    W = int(round(H * 16 / 9 / 2) * 2)
    total = c["dur"] + c["cauda"]
    vel = c["velocidade"]
    z = _expr_zoom(c["movimento"])
    vf = (f"setpts={vel:.5f}*PTS,fps={FPS},"
          f"scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x0B0B0F,setsar=1,"
          f"tpad=stop_mode=clone:stop_duration={total + 1:.3f},trim=duration={total:.3f},setpts=PTS-STARTPTS,"
          f"scale=w='trunc(iw*({z})/2)*2':h='trunc(ih*({z})/2)*2':eval=frame:flags=bicubic,"
          f"crop={W}:{H}:'(in_w-out_w)/2{_expr_tremor(c['movimento'], 'x')}':'(in_h-out_h)/2{_expr_tremor(c['movimento'], 'y')}',"
          f"format=yuv420p")
    montagem.ff("-i", c["arquivo"], "-an", "-vf", vf, "-c:v", "libx264", "-preset", preset, "-crf", "17", "-r", str(FPS), str(saida))
    return saida


def renderizar(plano: dict, pasta: Path, preset: str) -> list[Path]:
    pasta.mkdir(parents=True, exist_ok=True)
    saidas = [pasta / f"cena_{c['global']:03d}.mp4" for c in plano["cenas"]]
    with ThreadPoolExecutor(max(1, RENDER_PARALELO)) as ex:
        list(ex.map(lambda par: preparar_cena(par[0], par[1], preset), zip(plano["cenas"], saidas)))
    return saidas


# ---------------------------------------------------------------- shorts sem Claude
def _shorts_padrao(cenas: list[dict], falas: list[dict], titulo: str) -> list[dict]:
    """Sem chave da Anthropic: o short é a primeira parte (o gancho), se couber em 20 a 60 s."""
    primeira = cenas[0]["parte"] if cenas else ""
    idx = [c["indice"] for c in cenas if c["parte"] == primeira]
    dur = sum(falas[i]["duracao"] + 0.5 for i in idx)
    if 20 <= dur <= 60:
        return [{"titulo": titulo, "chapeu": primeira[:20], "cenas": idx, "gancho_falado": ""}]
    while idx and dur > 60:
        dur -= falas[idx.pop()]["duracao"] + 0.5
    return [{"titulo": titulo, "chapeu": primeira[:20], "cenas": idx, "gancho_falado": ""}] if dur >= 20 else []


# ---------------------------------------------------------------- tudo
def editar(job_id: str, opcoes: dict | None = None, callback_url: str | None = None) -> dict:
    op = {**PADRAO, **(opcoes or {})}
    p = jobs.pasta(job_id)
    saida = p / "saida"
    saida.mkdir(exist_ok=True)
    avisos: list[str] = []
    try:
        fichas = json.loads((p / "fichas.json").read_text(encoding="utf-8"))
        jobs.etapa(job_id, "conferir_cenas", "rodando")
        meta, cenas, av = ler_fichas(fichas, p / "cenas")
        avisos += av
        infos = [_ffprobe(Path(c["arquivo"])) for c in cenas]
        movs = [movimento(Path(c["arquivo"])) for c in cenas]
        jobs.etapa(job_id, "conferir_cenas", "ok", cenas=len(cenas), titulo=meta["titulo"], avisos=avisos)

        jobs.etapa(job_id, "narracao", "rodando")
        (p / "audio").mkdir(exist_ok=True)
        falas = []
        for c in cenas:
            arq = p / "audio" / f"cena_{c['indice']:03d}.wav"
            f = narracao.falar(c["narracao"] or "…", arq)
            ws, metodo = alinhamento.palavras(arq, c["narracao"], f["duracao"], f.pop("palavras_tts", None))
            f.update(palavras=ws, alinhamento=metodo)
            falas.append(f)
            jobs.etapa(job_id, "narracao", "rodando", feitas=len(falas), total=len(cenas), motor=f["motor"])
        jobs.gravar(job_id, falas, "falas.json")
        jobs.etapa(job_id, "narracao", "ok", motor=falas[0]["motor"] if falas else None,
                   alinhamento=falas[0]["alinhamento"] if falas else None)

        pl = montar_plano(cenas, falas, infos, movs)
        jobs.gravar(job_id, pl, "plano_longo.json")
        jobs.etapa(job_id, "video_longo", "rodando", segundos=pl["duracao"])
        clips = renderizar(pl, p / "clips_longo", op["preset"])
        mudo = montagem.juntar(clips, pl, p / "longo_mudo.mp4")
        aud = montagem.audio(pl, p, op["clima_trilha"], op["trilha"], op.get("trilha_arquivo"))
        leg = montagem.srt(pl, saida / "longo_16x9.srt")
        final = montagem.final_169(mudo, aud, saida / "longo_16x9.mp4", leg if op["legenda_queimada_longo"] else None)
        creditos = json.loads((p / "creditos.json").read_text())
        desc = montagem.descricao(pl, meta["titulo"], creditos, saida / "descricao_youtube.txt")
        if avisos:
            with open(desc, "a", encoding="utf-8") as fh:
                fh.write("\n# CONFERIR ANTES DE PUBLICAR (apague esta parte)\n" + "\n".join(f"- {a}" for a in avisos) + "\n")
        resultado = {"job_id": job_id, "titulo": meta["titulo"], "duracao": pl["duracao"],
                     "longo": {"video": str(final), "legenda": str(leg), "descricao": str(desc)}, "shorts": [],
                     "avisos": avisos, "motores": {"voz": falas[0]["motor"] if falas else None,
                                                   "alinhamento": falas[0]["alinhamento"] if falas else None}}
        jobs.etapa(job_id, "video_longo", "ok")

        if op["shorts"]:
            jobs.etapa(job_id, "shorts", "rodando")
            try:
                escolhidos = shorts.escolher({"titulo": meta["titulo"]},
                                             [{"indice": c["indice"], "narracao": c["narracao"]} for c in cenas],
                                             [f["duracao"] for f in falas])
            except Exception as e:  # sem chave da Anthropic ou erro: usa o gancho
                avisos.append(f"shorts escolhidos pela regra do gancho ({str(e)[:80]})")
                escolhidos = _shorts_padrao(cenas, falas, meta["titulo"])
            for k, s in enumerate(escolhidos[: op["max_shorts"]], 1):
                ps = p / f"short_{k}"
                (ps / "audio").mkdir(parents=True, exist_ok=True)
                sub_c = [cenas[i] for i in s["cenas"]]
                sub_f = [dict(falas[i]) for i in s["cenas"]]
                if s.get("gancho_falado"):
                    arq = ps / "audio" / "abertura.wav"
                    texto = f"{s['gancho_falado']} {sub_c[0]['narracao']}"
                    f0 = narracao.falar(texto, arq)
                    ws, _ = alinhamento.palavras(arq, texto, f0["duracao"], f0.pop("palavras_tts", None))
                    f0["palavras"] = ws
                    sub_f[0] = f0
                pls = montar_plano(sub_c, sub_f, [infos[i] for i in s["cenas"]], [movs[i] for i in s["cenas"]], curto=True)
                clips_s = renderizar(pls, ps / "clips", op["preset"])
                mudo_s = montagem.juntar(clips_s, pls, ps / "mudo.mp4")
                aud_s = montagem.audio(pls, ps, op["clima_trilha"], op["trilha"], op.get("trilha_arquivo"))
                ass = montagem.ass_palavra_a_palavra(pls, ps / "legenda.ass")
                video_s = montagem.final_916(mudo_s, aud_s, ass, s.get("titulo") or meta["titulo"], s.get("chapeu", ""),
                                             saida / f"short_{k}_9x16.mp4")
                info = {**s, "video": str(video_s), "duracao": pls["duracao"]}
                (saida / f"short_{k}.json").write_text(json.dumps(info, ensure_ascii=False, indent=2))
                resultado["shorts"].append(info)
            jobs.etapa(job_id, "shorts", "ok", quantidade=len(resultado["shorts"]))

        resultado["avisos"] = avisos
        jobs.gravar(job_id, resultado, "resultado.json")
        jobs.etapa(job_id, "concluido", "ok", avisos=avisos)
    except Exception as e:
        resultado = {"job_id": job_id, "erro": str(e), "trace": traceback.format_exc()[-3000:], "avisos": avisos}
        jobs.etapa(job_id, "erro", "falhou", erro=str(e))
    if callback_url:
        try:
            httpx.post(callback_url, json=resultado, timeout=30)
        except Exception:
            pass
    return resultado
