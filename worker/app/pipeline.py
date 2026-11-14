"""
Edição completa de um artifact (ou de um artifact em várias partes):

  artifact(s) ─► extrair cenas, animações e marcadores
     ─► camadas pedidas pelo artifact (mapa Natural Earth, arte FLUX/vtracer, desenho AnimatedDrawings)
     ─► narração por cena (ElevenLabs | Google TTS | Kokoro): a duração de cada cena vem da fala
     ─► tempo das palavras (da própria voz | Whisper | energia) + boca (envelope)
     ─► plano de edição (duração, relógio, punch-in, tremor, Lottie, sons, transições)
     ─► render 16:9 quadro a quadro com motion blur ─► transições ─► mix (voz + SFX + trilha) ─► acabamento
     ─► longo_16x9.mp4 + .srt + descrição do YouTube (capítulos e créditos)
     ─► shorts: escolhe trechos ─► render ─► composição 9:16 + legenda palavra a palavra
"""
from __future__ import annotations

import json
import shutil
import traceback
from pathlib import Path

import httpx

from . import jobs
from .etapas import alinhamento, camadas, direcao, montagem, narracao, plano, qualidade, render, roteiro_texto, shorts

PADRAO = {"shorts": True, "legenda_queimada_longo": False, "clima_trilha": "reflexivo", "trilha": True,
          "trilha_arquivo": None, "preset": "medium", "max_shorts": 3,
          "roteiro": None, "narracao_vem_de": "auto", "titulo": None, "direcao": None,
          "voz": None}   # None = a voz do worker (TTS_MOTOR); ou "elevenlabs" | "google" | "kokoro_onnx" só neste vídeo


def _fala(texto: str, arq: Path, tem_boca: bool, anterior: str = "", seguinte: str = "", motor: str | None = None) -> dict:
    f = narracao.falar(texto, arq, motor=motor, anterior=anterior, seguinte=seguinte)
    ws, metodo = alinhamento.palavras(arq, texto, f["duracao"], f.pop("palavras_tts", None))
    f.update(palavras=ws, alinhamento=metodo)
    if tem_boca:
        f["boca"], f["boca_metodo"] = alinhamento.boca(arq, texto)
    return f


def editar(job_id: str, artifact: Path | list[Path], opcoes: dict | None = None, callback_url: str | None = None) -> dict:
    op = {**PADRAO, **(opcoes or {})}
    voz = (op.get("voz") or "").strip() or None
    if voz in ("auto", "padrao", "padrão"):
        voz = None
    p = jobs.pasta(job_id)
    saida = p / "saida"
    saida.mkdir(exist_ok=True)
    avisos: list[str] = []
    try:
        fontes = artifact if isinstance(artifact, list) else [artifact]
        arts = []
        for k, a in enumerate(fontes, 1):
            destino = p / f"artifact_{k:02d}.html"
            if a.resolve() != destino.resolve():
                shutil.copy(a, destino)
            arts.append(destino)

        jobs.etapa(job_id, "extrair", "rodando")
        ext = render.extrair_partes(arts)
        cenas, meta = ext["cenas"], ext["meta"]
        # roteiro da planilha: título e, se for o caso, a narração das cenas
        modo, av = roteiro_texto.aplicar(cenas, op.get("roteiro"), op.get("narracao_vem_de", "auto"))
        avisos += av
        avisos += direcao.aplicar(cenas, op.get("direcao"))  # JSON do diretor (coluna "direcao" da planilha)
        meta["titulo"] = (op.get("titulo") or meta.get("titulo")
                          or (roteiro_texto.titulo(op["roteiro"]) if op.get("roteiro") else None)
                          or meta.get("titulo_documento") or "Vídeo")
        jobs.etapa(job_id, "extrair", "ok", cenas=len(cenas), partes=len(arts), titulo=meta["titulo"], narracao=modo)

        jobs.etapa(job_id, "camadas", "rodando")
        n_camadas = 0
        for c in cenas:
            c["camadas"], av = camadas.da_cena(c, p / "camadas")
            n_camadas += len(c["camadas"])
            avisos += [f"cena {c['indice']}: {a}" for a in av]
        jobs.gravar(job_id, ext, "cenas.json")
        jobs.etapa(job_id, "camadas", "ok", camadas=n_camadas, avisos=avisos)

        jobs.etapa(job_id, "narracao", "rodando")
        (p / "audio").mkdir(exist_ok=True)
        creditos_voz = qualidade.conferir_creditos(cenas, avisos, voz)   # para ANTES de gastar, se não der para terminar
        falas = []
        for k, c in enumerate(cenas):
            ant = cenas[k - 1]["narracao"] if k > 0 else ""
            seg = cenas[k + 1]["narracao"] if k + 1 < len(cenas) else ""
            falas.append(_fala(c["narracao"], p / "audio" / f"cena_{k:03d}.wav", c.get("tem_boca", False), ant, seg, voz))
            jobs.etapa(job_id, "narracao", "rodando", feitas=len(falas), total=len(cenas))
        creditos_voz["gastos"] = round(sum(f.get("caracteres", 0) for f in falas) * narracao.custo_por_caractere())
        creditos_voz["cenas_do_cache"] = sum(1 for f in falas if f.get("do_cache"))
        jobs.gravar(job_id, falas, "falas.json")
        jobs.etapa(job_id, "narracao", "ok", motor=falas[0]["motor"] if falas else None,
                   alinhamento=falas[0]["alinhamento"] if falas else None,
                   boca=next((f.get("boca_metodo") for f in falas if f.get("boca_metodo")), None))
        if falas and falas[0]["motor"] == "estimado":
            avisos.append("nenhuma voz disponível: narração em silêncio (configure ElevenLabs ou Google TTS; a Kokoro vem no worker)")

        # ---------------- vídeo longo 16:9
        pl = plano.montar(cenas, falas)
        jobs.gravar(job_id, pl, "plano_longo.json")
        jobs.etapa(job_id, "render_longo", "rodando", segundos=pl["duracao"])
        clips = render.renderizar(arts, pl, p / "clips_longo", op["preset"])
        mudo = montagem.juntar(clips, pl, p / "longo_mudo.mp4")
        jobs.etapa(job_id, "render_longo", "ok")

        jobs.etapa(job_id, "mixagem_longo", "rodando")
        aud = montagem.audio(pl, p, op["clima_trilha"], op["trilha"], op.get("trilha_arquivo"))
        leg = montagem.srt(pl, saida / "longo_16x9.srt")
        final = montagem.final_169(mudo, aud, saida / "longo_16x9.mp4", leg if op["legenda_queimada_longo"] else None)
        creditos = json.loads((p / "creditos.json").read_text())
        desc = montagem.descricao(pl, meta.get("titulo", ""), creditos, saida / "descricao_youtube.txt")
        jobs.etapa(job_id, "conferencia", "rodando")
        qa = qualidade.conferir(pl, cenas, final, saida, meta.get("titulo", ""), creditos_voz, avisos)
        jobs.etapa(job_id, "conferencia", "ok", nota=qa["nota"], problemas=len(qa["problemas"]))
        resultado = {"job_id": job_id, "titulo": meta.get("titulo"), "duracao": pl["duracao"],
                     "longo": {"video": str(final), "legenda": str(leg), "descricao": str(desc)},
                     "shorts": [], "avisos": avisos, "qualidade": {"nota": qa["nota"], "problemas": qa["problemas"]},
                     "relatorio": qa["arquivos"], "creditos_elevenlabs": creditos_voz,
                     "motores": {"voz": falas[0]["motor"] if falas else None,
                                 "alinhamento": falas[0]["alinhamento"] if falas else None}}
        jobs.etapa(job_id, "mixagem_longo", "ok")

        # ---------------- shorts 9:16
        if op["shorts"]:
            jobs.etapa(job_id, "shorts", "rodando")
            try:
                escolhidos = shorts.escolher(meta, cenas, [f["duracao"] for f in falas])[: op["max_shorts"]]
            except Exception:  # sem ANTHROPIC_API_KEY (e sem META.shorts no artifact): escolha automática
                escolhidos = shorts.automatico(meta, cenas, [f["duracao"] for f in falas], op["max_shorts"])
            for k, s in enumerate(escolhidos, 1):
                ps = p / f"short_{k}"
                (ps / "audio").mkdir(parents=True, exist_ok=True)
                sub_cenas = [cenas[i] for i in s["cenas"]]
                sub_falas = [falas[i] for i in s["cenas"]]
                if s.get("gancho_falado"):
                    c0 = sub_cenas[0]
                    sub_falas[0] = _fala(f"{s['gancho_falado']} {c0['narracao']}", ps / "audio" / "abertura.wav",
                                         c0.get("tem_boca", False), motor=voz)
                pls = plano.montar(sub_cenas, sub_falas, curto=True)
                jobs.gravar(job_id, pls, f"short_{k}/plano.json")
                clips_s = render.renderizar(arts, pls, ps / "clips", op["preset"])
                mudo_s = montagem.juntar(clips_s, pls, ps / "mudo.mp4")
                aud_s = montagem.audio(pls, ps, op["clima_trilha"], op["trilha"], op.get("trilha_arquivo"))
                ass = montagem.ass_palavra_a_palavra(pls, ps / "legenda.ass")
                video_s = montagem.final_916(mudo_s, aud_s, ass, s.get("titulo") or meta.get("titulo", ""),
                                             s.get("chapeu", ""), saida / f"short_{k}_9x16.mp4")
                info = {**s, "video": str(video_s), "duracao": pls["duracao"]}
                (saida / f"short_{k}.json").write_text(json.dumps(info, ensure_ascii=False, indent=2))
                resultado["shorts"].append(info)
            jobs.etapa(job_id, "shorts", "ok", quantidade=len(resultado["shorts"]))

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
