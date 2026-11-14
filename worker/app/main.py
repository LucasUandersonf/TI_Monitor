"""
API do worker (o n8n conversa só com ela).

  POST /edicao                 recebe o artifact (arquivo, base64 ou caminho) e começa a edição em segundo plano
  GET  /jobs/{id}              andamento de cada etapa
  GET  /jobs/{id}/resultado    caminhos e metadados dos vídeos prontos
  GET  /arquivos/{id}/{nome}   baixa um arquivo da pasta saida/ (o n8n sobe para o Drive)

  POST /pauta/tendencias       coleta e grava as tendências do dia
  POST /pauta/candidatos       3 temas candidatos a partir das tendências
  POST /pauta/roteiro          roteiro em texto para a conversa de artifacts
"""
from __future__ import annotations

import base64
import json
import os
import re
import threading
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import db, jobs, pauta, pipeline
from .fontes import tendencias

app = FastAPI(title="Fábrica Cult · worker de edição")


# fila: no máximo N edições ao mesmo tempo (o render usa todos os núcleos); as outras esperam a vez
FILA = threading.Semaphore(int(os.environ.get("EDICOES_SIMULTANEAS", "1")))


def _iniciar(job_id: str, artifact, opcoes: dict, callback_url: str | None):
    def rodar():
        jobs.etapa(job_id, "fila", "esperando")
        with FILA:
            r = pipeline.editar(job_id, artifact, opcoes, callback_url)
            try:
                db.salvar_video(job_id, r)
            except Exception:
                pass
    threading.Thread(target=rodar, daemon=True).start()


class PedidoEdicao(BaseModel):
    artifact_base64: str | None = None     # conteúdo do .html em base64 (vindo do Google Drive no n8n)
    artifacts_base64: list[str] = []       # ou várias partes, na ordem (parte 1, parte 2...)
    artifact_caminho: str | None = None    # ou um caminho já presente no volume compartilhado
    nome: str = "video"
    roteiro: str | None = None             # texto da coluna "roteiro" da planilha
    data: str | None = None                # coluna "data" (só vai para o registro)
    opcoes: dict = {}
    callback_url: str | None = None        # webhook do n8n chamado no fim (sucesso ou erro)


@app.post("/edicao")
def edicao(p: PedidoEdicao):
    job_id = jobs.novo_id(p.nome)
    conteudos = [base64.b64decode(b) for b in p.artifacts_base64]
    if p.artifact_base64:
        conteudos.append(base64.b64decode(p.artifact_base64))
    elif not conteudos and p.artifact_caminho and Path(p.artifact_caminho).exists():
        conteudos.append(Path(p.artifact_caminho).read_bytes())
    if not conteudos:
        raise HTTPException(400, "Envie artifact_base64, artifacts_base64 ou artifact_caminho.")
    destinos = []
    for k, c in enumerate(conteudos, 1):
        d = jobs.pasta(job_id) / f"artifact_{k:02d}.html"
        d.write_bytes(c)
        destinos.append(d)
    opcoes = {**p.opcoes}
    if p.roteiro:
        opcoes["roteiro"] = p.roteiro
    jobs.gravar(job_id, {"nome": p.nome, "data": p.data, "roteiro": p.roteiro, "opcoes": opcoes}, "pedido.json")
    _iniciar(job_id, destinos, opcoes, p.callback_url)
    return {"job_id": job_id, "status": "iniciado"}


@app.post("/edicao/upload")
async def edicao_upload(arquivo: UploadFile = File(...), opcoes: str = Form("{}"), callback_url: str = Form("")):
    job_id = jobs.novo_id(Path(arquivo.filename or "video").stem)
    destino = jobs.pasta(job_id) / "artifact_01.html"
    destino.write_bytes(await arquivo.read())
    _iniciar(job_id, destino, json.loads(opcoes or "{}"), callback_url or None)
    return {"job_id": job_id, "status": "iniciado"}


# ---------------------------------------------------------------- episódio em cenas (MP4 + fichas.json)
class PedidoEpisodio(BaseModel):
    nome: str = "episodio"
    fichas: dict                            # conteúdo do fichas.json
    opcoes: dict = {}
    callback_url: str | None = None


@app.post("/episodio")
def episodio_criar(p: PedidoEpisodio):
    """1º passo: manda o fichas.json. Devolve o job e a lista de vídeos que o worker espera receber."""
    if not p.fichas.get("cenas"):
        raise HTTPException(400, "fichas.json sem a lista 'cenas'")
    job_id = jobs.novo_id(p.nome)
    jobs.gravar(job_id, p.fichas, "fichas.json")
    jobs.gravar(job_id, {"nome": p.nome, "opcoes": p.opcoes, "callback_url": p.callback_url}, "pedido.json")
    (jobs.pasta(job_id) / "cenas").mkdir(exist_ok=True)
    esperados = [Path(c.get("arquivo") or f"cena-{k + 1:02d}.mp4").name for k, c in enumerate(p.fichas["cenas"])]
    jobs.etapa(job_id, "recebendo_cenas", "rodando", esperadas=len(esperados))
    return {"job_id": job_id, "arquivos_esperados": esperados}


@app.post("/episodio/{job_id}/arquivo")
async def episodio_arquivo(job_id: str, arquivo: UploadFile = File(...)):
    """2º passo: um vídeo de cena por chamada (multipart, campo 'arquivo')."""
    if not (jobs.pasta(job_id) / "fichas.json").exists():
        raise HTTPException(404, "job não encontrado")
    nome = Path(arquivo.filename or "").name
    if not re.fullmatch(r"[\w .()\-]+\.(mp4|mov|webm|mkv)", nome, re.I):
        raise HTTPException(400, f"nome de arquivo inválido: {nome!r}")
    destino = jobs.pasta(job_id) / "cenas" / nome
    with open(destino, "wb") as f:
        while bloco := await arquivo.read(1 << 20):
            f.write(bloco)
    return {"ok": True, "arquivo": nome, "bytes": destino.stat().st_size}


@app.post("/episodio/{job_id}/iniciar")
def episodio_iniciar(job_id: str):
    """3º passo: confere se todas as cenas chegaram e põe o episódio na fila de edição."""
    from . import pipeline_clipes
    pasta = jobs.pasta(job_id)
    if not (pasta / "fichas.json").exists():
        raise HTTPException(404, "job não encontrado")
    fichas = jobs.ler(job_id, "fichas.json")
    pedido = jobs.ler(job_id, "pedido.json")
    esperados = [Path(c.get("arquivo") or f"cena-{k + 1:02d}.mp4").name for k, c in enumerate(fichas["cenas"])]
    faltando = [n for n in esperados if not (pasta / "cenas" / n).exists()]
    if faltando:
        raise HTTPException(409, f"faltam {len(faltando)} vídeo(s): {', '.join(faltando[:10])}")

    def rodar():
        jobs.etapa(job_id, "fila", "esperando")
        with FILA:
            r = pipeline_clipes.editar(job_id, pedido.get("opcoes"), pedido.get("callback_url"))
            try:
                db.salvar_video(job_id, r)
            except Exception:
                pass
    threading.Thread(target=rodar, daemon=True).start()
    return {"job_id": job_id, "status": "na fila", "cenas": len(esperados)}


@app.get("/jobs/{job_id}")
def estado(job_id: str):
    p = jobs.pasta(job_id) / "estado.json"
    if not p.exists():
        raise HTTPException(404, "job não encontrado")
    est = json.loads(p.read_text())
    est["concluido"] = est.get("atual") in ("concluido", "erro")
    return est


@app.get("/jobs/{job_id}/resultado")
def resultado(job_id: str):
    p = jobs.pasta(job_id) / "resultado.json"
    if not p.exists():
        raise HTTPException(404, "ainda não terminou")
    r = json.loads(p.read_text())
    # lista simples para o n8n iterar e subir para o Drive
    arquivos = [{"nome": Path(r["longo"]["video"]).name, "tipo": "longo"},
                {"nome": Path(r["longo"]["legenda"]).name, "tipo": "legenda"}]
    if r["longo"].get("descricao") and Path(r["longo"]["descricao"]).exists():
        r["descricao_texto"] = Path(r["longo"]["descricao"]).read_text(encoding="utf-8")
    if r["longo"].get("descricao"):
        arquivos.append({"nome": Path(r["longo"]["descricao"]).name, "tipo": "descricao"})
    for tipo, caminho in (r.get("relatorio") or {}).items():   # relatorio_qualidade.txt e tempos_das_cenas.csv
        if Path(caminho).exists():
            arquivos.append({"nome": Path(caminho).name, "tipo": tipo})
    for k, s in enumerate(r["shorts"], 1):
        arquivos += [{"nome": Path(s["video"]).name, "tipo": "short", "titulo": s.get("titulo"),
                      "legenda_post": s.get("legenda_post"), "hashtags": s.get("hashtags")},
                     {"nome": f"short_{k}.json", "tipo": "metadados"}]
    r["arquivos"] = arquivos
    return r


@app.get("/arquivos/{job_id}/{nome}")
def arquivo(job_id: str, nome: str):
    p = (jobs.pasta(job_id) / "saida" / nome).resolve()
    if not str(p).startswith(str((jobs.pasta(job_id) / "saida").resolve())) or not p.exists():
        raise HTTPException(404, "arquivo não encontrado")
    return FileResponse(p, filename=nome)


# ---------------------------------------------------------------- sua voz
class PedidoVoz(BaseModel):
    audio_base64: str                       # gravação da sua voz (wav, mp3, m4a, ogg...)
    nome_arquivo: str = "gravacao.m4a"


@app.post("/voz/referencia")
def voz_referencia(p: PedidoVoz):
    """Cadastra a sua voz: limpa a gravação, escolhe o melhor trecho e transcreve."""
    from .etapas import referencia
    from .config import BIBLIOTECA
    bruto = BIBLIOTECA / "voz" / ("_entrada" + (Path(p.nome_arquivo).suffix or ".wav"))
    bruto.parent.mkdir(parents=True, exist_ok=True)
    bruto.write_bytes(base64.b64decode(p.audio_base64))
    r = referencia.preparar(bruto)
    bruto.unlink(missing_ok=True)
    from .etapas import narracao
    narracao._motor.cache_clear()          # a partir de agora a narração usa a sua voz
    return r


class PedidoTesteVoz(BaseModel):
    texto: str = ("Seu cérebro não está procurando a verdade. Está procurando conforto. "
                  "E em dois mil e vinte e três, noventa milhões de pessoas provaram isso.")
    motores: list[str] = ["clone_qwen3", "clone_chatterbox", "kokoro_onnx"]


@app.post("/voz/teste")
def voz_teste(p: PedidoTesteVoz):
    """Gera a mesma frase com cada motor, para você ouvir e escolher (arquivos em /voz/arquivo/<nome>)."""
    import time as _t
    from .config import BIBLIOTECA
    from .etapas import narracao, voz_clonada
    pasta = BIBLIOTECA / "voz" / "testes"
    pasta.mkdir(parents=True, exist_ok=True)
    out = []
    for motor in p.motores:
        arq = pasta / f"teste_{motor}.wav"
        t0 = _t.time()
        try:
            if motor.startswith("clone_"):
                r = voz_clonada.falar(p.texto, arq, motor.removeprefix("clone_"))
            else:
                r = narracao.falar(p.texto, arq, motor=motor)
            out.append({"motor": motor, "arquivo": arq.name, "duracao": round(r["duracao"], 2),
                        "segundos_para_gerar": round(_t.time() - t0, 1), "conferencia": r.get("conferencia")})
        except Exception as e:
            out.append({"motor": motor, "erro": str(e)[:300]})
    return {"texto": p.texto, "resultados": out}


@app.post("/voz/baixar-modelos")
def voz_baixar_modelos(motores: str = "qwen3_tts_base,whisper_small"):
    """Baixa os pesos antes do primeiro vídeo (opcional: sem isso, baixa na primeira vez que usar)."""
    from .etapas import modelos
    feitos = {}
    for nome in [m.strip() for m in motores.split(",") if m.strip()]:
        feitos[nome] = str(modelos.baixar(nome))
    return {"ok": True, "baixados": feitos}


@app.get("/voz/arquivo/{nome}")
def voz_arquivo(nome: str):
    from .config import BIBLIOTECA
    base = (BIBLIOTECA / "voz" / "testes").resolve()
    arq = (base / nome).resolve()
    if not str(arq).startswith(str(base)) or not arq.exists():
        raise HTTPException(404, "arquivo não encontrado")
    return FileResponse(arq, filename=nome)


# ---------------------------------------------------------------- pauta
@app.post("/pauta/tendencias")
def pauta_tendencias(limite: int = 60):
    r = tendencias.coletar(db.temas_recentes(), limite)
    try:
        db.salvar_tendencias(r["itens"])
    except Exception as e:
        r["erros"]["banco"] = str(e)[:200]
    return r


class PedidoCandidatos(BaseModel):
    itens: list[dict]


@app.post("/pauta/candidatos")
def pauta_candidatos(p: PedidoCandidatos):
    return pauta.candidatos(p.itens, db.temas_recentes())


class PedidoRoteiro(BaseModel):
    tema: dict


@app.post("/pauta/roteiro")
def pauta_roteiro(p: PedidoRoteiro):
    r = pauta.roteiro(p.tema)
    try:
        r["pauta_id"] = db.salvar_pauta(p.tema, r)
    except Exception:
        pass
    return r


def _motor_seguro() -> str:
    from .etapas import narracao
    try:
        return narracao.motor_atual()
    except Exception as e:
        return f"ERRO: {e}"


def _sfx_plano() -> dict:
    from .etapas import sfx_eleven
    return sfx_eleven.plano()


# ---------------------------------------------------------------- ElevenLabs
class PedidoSons(BaseModel):
    confirmar: bool = False              # false = só mostra o que seria gerado
    refazer: bool = False                # true = gera de novo os que já existem
    limite_creditos: int = 1500          # para no meio se passar disso


@app.post("/sfx/biblioteca")
def sfx_biblioteca(p: PedidoSons):
    """Gera (uma vez) a biblioteca de efeitos modernos com a ElevenLabs Sound Effects."""
    from .etapas import sfx_eleven
    if not p.confirmar:
        return {"previa": sfx_eleven.plano(), "como_gerar": "mande de novo com confirmar: true"}
    return sfx_eleven.gerar(p.refazer, p.limite_creditos)


@app.get("/elevenlabs/saldo")
def elevenlabs_saldo():
    from .etapas import narracao
    return {"modelo": narracao.ELEVENLABS_MODELO, "saldo": narracao.saldo_elevenlabs(),
            "creditos_por_caractere": narracao.custo_por_caractere()}


@app.get("/saude")
def saude():
    from .etapas import alinhamento, camadas, mapas, narracao
    from .config import ACE_STEP_CMD, ANIMATED_DRAWINGS_CMD, FREESOUND_TOKEN, MOTION_BLUR, OPENVERSE_ATIVO, TEXTURA_PAPEL
    import shutil
    try:
        import torch
        gpu = torch.cuda.is_available()
    except Exception:
        gpu = False
    try:
        import vtracer  # noqa: F401
        vt = True
    except Exception:
        vt = False
    return {"ok": True, "gpu": gpu,
            "voz": {"ativa": _motor_seguro(), "motores": narracao.disponiveis(),
                    "elevenlabs": {"modelo": narracao.ELEVENLABS_MODELO, "saldo": narracao.saldo_elevenlabs() if narracao.ELEVENLABS_API_KEY else None}},
            "sons_biblioteca": _sfx_plano(),
            "alinhamento": "whisperx" if alinhamento._whisperx() else "energia (ou ElevenLabs, quando for a voz)",
            "boca": "rhubarb" if shutil.which("rhubarb") else "envelope",
            "sons": {"freesound": bool(FREESOUND_TOKEN), "stable_audio": gpu, "sintese": True},
            "trilha": {"openverse": OPENVERSE_ATIVO, "ace_step": bool(ACE_STEP_CMD)},
            "imagem": {"mapas": mapas.disponivel(), "vtracer": vt, "flux": gpu, "animated_drawings": bool(ANIMATED_DRAWINGS_CMD)},
            "lottie": {"destaque": camadas.lottie_da_biblioteca("destaque") is not None},
            "acabamento": {"motion_blur": MOTION_BLUR, "textura_papel": TEXTURA_PAPEL}}
