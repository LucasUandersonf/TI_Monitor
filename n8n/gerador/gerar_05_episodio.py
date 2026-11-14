"""Gera n8n/workflows/05_episodio_cenas_premium.json (rode: python3 n8n/gerador/gerar_05_episodio.py).

Fluxo definitivo para episódios em cenas:
  Drive "02 · Episódios"/<pasta do episódio>/  cena-01.mp4 … cena-NN.mp4 + fichas.json (o fichas.json sobe por último)
  → worker edita → Drive "03 · Vídeos prontos"/<pasta do episódio>/  longo, legenda, descrição, shorts
"""
import json
import uuid
from pathlib import Path

_c = [0]


def nid():
    _c[0] += 1
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"fab05-{_c[0]}"))


def node(name, typ, ver, pos, params, **kw):
    n = {"id": nid(), "name": name, "type": typ, "typeVersion": ver, "position": pos, "parameters": params}
    n.update(kw)
    return n


CFG = "$('Config').first().json"


def http(name, pos, method, url, body=None, timeout=120000, arquivo=False, **kw):
    p = {"method": method, "url": url, "options": {"timeout": timeout}}
    if body:
        p.update({"sendBody": True, "specifyBody": "json", "jsonBody": body})
    if arquivo:
        p["options"]["response"] = {"response": {"responseFormat": "file", "outputPropertyName": "data"}}
    return node(name, "n8n-nodes-base.httpRequest", 4.2, pos, p, **kw)


def code(name, pos, js, **kw):
    return node(name, "n8n-nodes-base.code", 2, pos, {"mode": "runOnceForAllItems", "jsCode": js}, **kw)


def rl(v, mode="id"):
    return {"__rl": True, "mode": mode, "value": v}


def iff(name, pos, left, tipo, op, right="", single=False):
    o = {"type": tipo, "operation": op}
    if single:
        o["singleValue"] = True
    return node(name, "n8n-nodes-base.if", 2, pos, {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
        "conditions": [{"id": nid(), "leftValue": left, "rightValue": right, "operator": o}], "combinator": "and"}, "options": {}})


def renomear(name, pos, file_expr, novo, **kw):
    return node(name, "n8n-nodes-base.googleDrive", 3, pos, {"operation": "update", "fileId": rl(file_expr),
                                                             "newUpdatedFileName": novo, "options": {}}, **kw)


CAMPOS = [
    ("worker_url", "https://SEU-WORKER.up.railway.app"),
    ("pasta_episodios", "COLE_AQUI_O_ID_DA_PASTA_02_EPISODIOS"),
    ("pasta_prontos", "COLE_AQUI_O_ID_DA_PASTA_03_VIDEOS_PRONTOS"),
    ("gerar_shorts", "sim"),
    ("clima_trilha", "reflexivo"),
    ("trilha_arquivo", ""),
    ("legenda_queimada_no_longo", "nao"),
    ("telegram_bot_token", ""),
    ("telegram_chat_id", ""),
]

ESCOLHER = r"""// Junta os arquivos de cada pasta de episódio e escolhe o primeiro que está pronto para editar:
// tem "fichas.json" (o sinal de pronto) e ainda não tem "fichas.em_edicao.json" nem "fichas.processado.json".
const pastas = $('Pastas de episódio').all().map(i => i.json).filter(p => p.id);
const porPasta = {};
$input.all().forEach((item, k) => {
  const pi = Array.isArray(item.pairedItem) ? item.pairedItem[0] : item.pairedItem;
  const idx = pi?.item ?? 0;
  if (!item.json.id) return;
  (porPasta[idx] ??= []).push(item.json);
});
const ordem = pastas.map((p, idx) => ({ ...p, idx })).sort((a, b) => a.name.localeCompare(b.name, 'pt'));
for (const p of ordem) {
  const arqs = porPasta[p.idx] || [];
  const nomes = arqs.map(a => a.name.toLowerCase());
  const fichas = arqs.find(a => a.name.toLowerCase() === 'fichas.json');
  if (!fichas || nomes.includes('fichas.em_edicao.json') || nomes.includes('fichas.processado.json')) continue;
  const videos = arqs.filter(a => /\.(mp4|mov|webm|mkv)$/i.test(a.name)).sort((a, b) => a.name.localeCompare(b.name, 'pt', { numeric: true }));
  return [{ json: { pasta_id: p.id, pasta_nome: p.name, fichas_id: fichas.id, videos } }];
}
return [];   // nada novo para editar"""

LER_FICHAS = r"""const ep = $('Escolher episódio').first().json;
const buf = await this.helpers.getBinaryDataBuffer(0, 'data');
let fichas;
try { fichas = JSON.parse(buf.toString('utf8').replace(/^﻿/, '')); }
catch (e) { throw new Error(`fichas.json da pasta "${ep.pasta_nome}" não é um JSON válido: ${e.message}`); }
if (!Array.isArray(fichas.cenas) || !fichas.cenas.length) throw new Error('fichas.json sem a lista "cenas"');
// confere se todos os vídeos citados nas fichas estão na pasta
const naPasta = new Set(ep.videos.map(v => v.name));
const faltando = fichas.cenas.map((c, k) => c.arquivo || `cena-${String(k + 1).padStart(2, '0')}.mp4`).filter(n => !naPasta.has(n));
if (faltando.length) throw new Error(`Faltam ${faltando.length} vídeo(s) na pasta "${ep.pasta_nome}": ${faltando.slice(0, 10).join(', ')}. ` +
  'Suba os vídeos e renomeie fichas.em_edicao.json de volta para fichas.json.');
const cfg = $('Config').first().json;
return [{ json: {
  nome: ep.pasta_nome,
  fichas,
  opcoes: { shorts: cfg.gerar_shorts === 'sim', max_shorts: 3, trilha: true, clima_trilha: cfg.clima_trilha || 'reflexivo',
            trilha_arquivo: cfg.trilha_arquivo || null, legenda_queimada_longo: cfg.legenda_queimada_no_longo === 'sim' }
} }];"""

VIDEOS = r"""// só os vídeos que as fichas usam, na ordem
const ep = $('Escolher episódio').first().json;
const job = $('Criar episódio no worker').first().json;
const quer = new Set(job.arquivos_esperados);
return ep.videos.filter(v => quer.has(v.name)).map(v => ({ json: { id: v.id, name: v.name, job_id: job.job_id } }));"""

ANDAMENTO = r"""const cfg = $('Config').first().json;
const job_id = $('Criar episódio no worker').first().json.job_id;
let e = {};
try { e = await this.helpers.httpRequest({ method: 'GET', url: `${cfg.worker_url}/jobs/${job_id}`, json: true, timeout: 30000 }); }
catch (err) { e = { atual: 'sem resposta do worker', concluido: false }; }
const etapa = e.etapas?.[e.atual] || {};
return [{ json: { job_id, atual: e.atual, concluido: !!e.concluido, erro: e.atual === 'erro' ? (etapa.erro || 'falhou') : null,
                  progresso: etapa.total ? `${etapa.feitas}/${etapa.total}` : null } }];"""

PRONTOS = r"""const cfg = $('Config').first().json;
const job_id = $('Criar episódio no worker').first().json.job_id;
const r = await this.helpers.httpRequest({ method: 'GET', url: `${cfg.worker_url}/jobs/${job_id}/resultado`, json: true, timeout: 30000 });
return r.arquivos.filter(a => a.tipo !== 'metadados').map(a => ({ json: { ...a, job_id, titulo_video: r.titulo, avisos: r.avisos || [], duracao: r.duracao } }));"""

RESUMO = r"""const itens = $('Arquivos prontos').all().map(i => i.json);
const links = $('Salvar no Drive').all().map(i => i.json.webViewLink);
const ep = $('Escolher episódio').first().json;
const pasta = $('Criar pasta do episódio').first().json;
const min = Math.floor(itens[0].duracao / 60), seg = Math.round(itens[0].duracao % 60);
const linhas = [`✅ <b>${itens[0].titulo_video}</b> (${min}:${String(seg).padStart(2, '0')})`, `📁 ${ep.pasta_nome}`];
itens.forEach((a, k) => {
  if (a.tipo === 'longo') linhas.push(`🖥️ <a href="${links[k]}">Vídeo longo 16:9</a>`);
  else if (a.tipo === 'short') linhas.push(`📱 <a href="${links[k]}">${a.titulo || a.nome}</a>${a.legenda_post ? '\n' + a.legenda_post : ''}${a.hashtags ? '\n' + a.hashtags.join(' ') : ''}`);
  else if (a.tipo === 'descricao') linhas.push(`📝 <a href="${links[k]}">Descrição do YouTube (capítulos + créditos)</a>`);
  else if (a.tipo === 'legenda') linhas.push(`💬 <a href="${links[k]}">Legenda .srt</a>`);
});
const avisos = itens[0].avisos || [];
if (avisos.length) linhas.push('', '⚠️ Conferir antes de publicar:', ...avisos.map(a => '• ' + a));
return [{ json: { texto: linhas.join('\n'), pasta_pronta: pasta.id, avisos, arquivos: itens.map((a, k) => ({ tipo: a.tipo, nome: a.nome, link: links[k] })) } }];"""

TG = (f"={{{{ JSON.stringify({{ chat_id: {CFG}.telegram_chat_id, parse_mode: 'HTML', disable_web_page_preview: true, text: $json.texto }}) }}}}")
TG_ERRO = (f"={{{{ JSON.stringify({{ chat_id: {CFG}.telegram_chat_id, text: '❌ Episódio ' + $('Escolher episódio').first().json.pasta_nome + ': ' + $('Ver andamento').last().json.erro }}) }}}}")
URL_TG = f"=https://api.telegram.org/bot{{{{ {CFG}.telegram_bot_token }}}}/sendMessage"

n = [
    node("A cada 10 min", "n8n-nodes-base.scheduleTrigger", 1.2, [0, -120], {"rule": {"interval": [{"field": "minutes", "minutesInterval": 10}]}}),
    node("▶ Testar agora", "n8n-nodes-base.manualTrigger", 1, [0, 120], {}),
    node("Config", "n8n-nodes-base.set", 3.4, [220, 0], {"mode": "manual", "includeOtherFields": False, "assignments": {"assignments": [
        {"id": nid(), "name": k, "value": v, "type": "string"} for k, v in CAMPOS]}, "options": {}},
        notes="PREENCHA: URL do worker e os IDs das pastas 02 · Episódios e 03 · Vídeos prontos (o ID é o final do link da pasta).",
        notesInFlow=True),
    node("Pastas de episódio", "n8n-nodes-base.googleDrive", 3, [440, 0], {"resource": "fileFolder", "searchMethod": "query",
        "queryString": "trashed = false", "returnAll": True,
        "filter": {"folderId": rl(f"={{{{ {CFG}.pasta_episodios }}}}"), "whatToSearch": "folders"},
        "options": {"fields": ["id", "name"]}}, alwaysOutputData=True),
    node("Arquivos de cada pasta", "n8n-nodes-base.googleDrive", 3, [660, 0], {"resource": "fileFolder", "searchMethod": "query",
        "queryString": "trashed = false", "returnAll": True,
        "filter": {"folderId": rl("={{ $json.id }}"), "whatToSearch": "files"},
        "options": {"fields": ["id", "name"]}}, alwaysOutputData=True),
    code("Escolher episódio", [880, 0], ESCOLHER),
    http("Worker está no ar?", [1100, 0], "GET", f"={{{{ {CFG}.worker_url }}}}/saude", None, 60000),
    renomear("Marcar: em edição", [1320, 0], "={{ $('Escolher episódio').first().json.fichas_id }}", "fichas.em_edicao.json"),
    node("Baixar fichas", "n8n-nodes-base.googleDrive", 3, [1540, 0], {"operation": "download",
        "fileId": rl("={{ $('Escolher episódio').first().json.fichas_id }}"), "options": {}}),
    code("Ler fichas", [1760, 0], LER_FICHAS),
    http("Criar episódio no worker", [1980, 0], "POST", f"={{{{ {CFG}.worker_url }}}}/episodio", "={{ JSON.stringify($json) }}", 60000),
    code("Um item por vídeo", [2200, 0], VIDEOS),
    node("Baixar vídeo", "n8n-nodes-base.googleDrive", 3, [2420, 0], {"operation": "download", "fileId": rl("={{ $json.id }}"), "options": {}}),
    node("Enviar vídeo ao worker", "n8n-nodes-base.httpRequest", 4.2, [2640, 0], {
        "method": "POST", "url": f"={{{{ {CFG}.worker_url }}}}/episodio/{{{{ $('Criar episódio no worker').first().json.job_id }}}}/arquivo",
        "sendBody": True, "contentType": "multipart-form-data",
        "bodyParameters": {"parameters": [{"parameterType": "formBinaryData", "name": "arquivo", "inputDataFieldName": "data"}]},
        "options": {"timeout": 300000, "batching": {"batch": {"batchSize": 4, "batchInterval": 0}}}}),
    http("Iniciar edição", [2860, 0], "POST",
         f"={{{{ {CFG}.worker_url }}}}/episodio/{{{{ $('Criar episódio no worker').first().json.job_id }}}}/iniciar", None, 60000,
         executeOnce=True),
    node("Esperar 1 min", "n8n-nodes-base.wait", 1.1, [3080, 0], {"resume": "timeInterval", "amount": 60, "unit": "seconds"}, webhookId=nid()),
    code("Ver andamento", [3300, 0], ANDAMENTO),
    iff("Terminou?", [3520, 0], "={{ $json.concluido }}", "boolean", "true", single=True),
    iff("Deu erro?", [3740, -100], "={{ $json.atual }}", "string", "equals", "erro"),
    renomear("Marcar: erro", [3960, -300], "={{ $('Escolher episódio').first().json.fichas_id }}", "fichas.erro.json"),
    iff("Telegram? (erro)", [4180, -300], f"={{{{ {CFG}.telegram_bot_token }}}}", "string", "notEmpty", single=True),
    http("Avisar erro", [4400, -400], "POST", URL_TG, TG_ERRO, 30000),
    node("Parar com o erro", "n8n-nodes-base.stopAndError", 1, [4620, -300],
         {"errorMessage": "={{ 'A edição falhou: ' + $('Ver andamento').last().json.erro + ' (o arquivo virou fichas.erro.json; renomeie para fichas.json para tentar de novo)' }}"}),
    code("Arquivos prontos", [3960, 0], PRONTOS),
    node("Criar pasta do episódio", "n8n-nodes-base.googleDrive", 3, [4180, 0], {"resource": "folder", "name": "={{ $('Escolher episódio').first().json.pasta_nome }}",
        "driveId": rl("My Drive", "list"), "folderId": rl(f"={{{{ {CFG}.pasta_prontos }}}}"), "options": {}}, executeOnce=True),
    code("Um item por arquivo", [4400, 0], "return $('Arquivos prontos').all().map(i => ({ json: i.json }));"),
    http("Baixar do worker", [4620, 0], "GET", f"={{{{ {CFG}.worker_url }}}}/arquivos/{{{{ $json.job_id }}}}/{{{{ $json.nome }}}}", None, 900000, arquivo=True),
    node("Salvar no Drive", "n8n-nodes-base.googleDrive", 3, [4840, 0], {"name": "={{ $('Um item por arquivo').item.json.nome }}",
        "driveId": rl("My Drive", "list"), "folderId": rl("={{ $('Criar pasta do episódio').first().json.id }}"),
        "inputDataFieldName": "data", "options": {}}),
    renomear("Marcar: processado", [5060, 0], "={{ $('Escolher episódio').first().json.fichas_id }}", "fichas.processado.json", executeOnce=True),
    code("Resumo", [5280, 0], RESUMO),
    iff("Telegram?", [5500, 0], f"={{{{ {CFG}.telegram_bot_token }}}}", "string", "notEmpty", single=True),
    http("Avisar no Telegram", [5720, -100], "POST", URL_TG, TG, 30000),
]
c = {}


def liga(a, b, saida=0):
    c.setdefault(a, {"main": []})
    while len(c[a]["main"]) <= saida:
        c[a]["main"].append([])
    c[a]["main"][saida].append({"node": b, "type": "main", "index": 0})


seq = ["Config", "Pastas de episódio", "Arquivos de cada pasta", "Escolher episódio", "Worker está no ar?", "Marcar: em edição",
       "Baixar fichas", "Ler fichas", "Criar episódio no worker", "Um item por vídeo", "Baixar vídeo", "Enviar vídeo ao worker",
       "Iniciar edição", "Esperar 1 min", "Ver andamento", "Terminou?"]
liga("A cada 10 min", "Config")
liga("▶ Testar agora", "Config")
for a, b in zip(seq, seq[1:]):
    liga(a, b)
liga("Terminou?", "Deu erro?", 0)
liga("Terminou?", "Esperar 1 min", 1)
liga("Deu erro?", "Marcar: erro", 0)
liga("Deu erro?", "Arquivos prontos", 1)
liga("Marcar: erro", "Telegram? (erro)")
liga("Telegram? (erro)", "Avisar erro", 0)
liga("Telegram? (erro)", "Parar com o erro", 1)
liga("Avisar erro", "Parar com o erro")
for a, b in zip(["Arquivos prontos", "Criar pasta do episódio", "Um item por arquivo", "Baixar do worker", "Salvar no Drive",
                 "Marcar: processado", "Resumo", "Telegram?"],
                ["Criar pasta do episódio", "Um item por arquivo", "Baixar do worker", "Salvar no Drive", "Marcar: processado",
                 "Resumo", "Telegram?", "Avisar no Telegram"]):
    liga(a, b)
c["Telegram?"]["main"].append([])
w = {"id": "fabEpisodioCenas", "name": "05 · Episódio em cenas (MP4 + fichas.json → vídeo premium)", "active": False,
     "nodes": n, "connections": c, "settings": {"executionOrder": "v1", "timezone": "America/Sao_Paulo"}, "pinData": {}}
saida = Path(__file__).resolve().parent.parent / "workflows" / "05_episodio_cenas_premium.json"
saida.write_text(json.dumps(w, ensure_ascii=False, indent=2), encoding="utf-8")
print(saida, len(n), "nós")
