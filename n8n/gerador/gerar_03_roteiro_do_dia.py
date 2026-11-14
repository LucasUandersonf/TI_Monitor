"""Gera n8n/workflows/03_roteiro_do_dia.json (rode: python3 n8n/gerador/gerar_03_roteiro_do_dia.py)."""
import json
import uuid
from pathlib import Path

_contador = [0]


def nid():
    """IDs estáveis: gerar de novo não muda os nós."""
    _contador[0] += 1
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"fab03-{_contador[0]}"))
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
def rl(v, mode="id"): return {"__rl": True, "mode": mode, "value": v}
def iff(name, pos, left, tipo, op, right="", single=False):
    o = {"type": tipo, "operation": op}
    if single:
        o["singleValue"] = True
    return node(name, "n8n-nodes-base.if", 2, pos, {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
        "conditions": [{"id": nid(), "leftValue": left, "rightValue": right, "operator": o}], "combinator": "and"}, "options": {}})

CAMPOS = [
    ("worker_url", "http://fabrica-worker.railway.internal:8000"),
    ("planilha_id", "COLE_AQUI_O_ID_DA_PLANILHA"),
    ("drive_pasta_artifacts", "COLE_AQUI_O_ID_DA_PASTA_02_ARTIFACTS"),
    ("drive_pasta_prontos", "COLE_AQUI_O_ID_DA_PASTA_03_VIDEOS_PRONTOS"),
    ("narracao_vem_de", "auto"),
    ("gerar_shorts", "sim"),
    ("clima_trilha", "reflexivo"),
    ("trilha_arquivo", ""),
    ("voz", ""),
    ("limite_minutos", "120"),
    ("testar_com_a_data", ""),
    ("telegram_chat_id", ""),
]

LINHAS_DE_HOJE = r"""// Lê a planilha: colunas "roteiro" e "data" (e, se quiser, "artifact" com o nome do arquivo e "direcao" com o JSON do diretor).
// A data pode vir como data do Excel, "20/11/2026", "2026-11-20" ou "20-11-2026".
const cfg = $('Config').first().json;
const hoje = (cfg.testar_com_a_data || '').trim() || $now.setZone('America/Sao_Paulo').toISODate();

const sem = s => String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').trim().toLowerCase();
function paraISO(v) {
  if (v === null || v === undefined || v === '') return null;
  if (typeof v === 'number') {                       // número de série do Excel (dias desde 1899-12-30)
    const d = new Date(Date.UTC(1899, 11, 30) + Math.round(v) * 86400000);
    return d.toISOString().slice(0, 10);
  }
  if (v instanceof Date) return v.toISOString().slice(0, 10);
  const s = String(v).trim();
  let m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (m) return `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`;
  m = s.match(/^(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})/);  // dia/mês/ano (padrão brasileiro)
  if (m) { const a = m[3].length === 2 ? '20' + m[3] : m[3]; return `${a}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`; }
  if (/^\d{5}(\.\d+)?$/.test(s)) return paraISO(Number(s));
  return null;
}

const saida = [];
$input.all().forEach((item, k) => {
  const linha = {};
  for (const [chave, valor] of Object.entries(item.json)) linha[sem(chave)] = valor;
  const roteiro = String(linha.roteiro ?? '').trim();
  const data = paraISO(linha.data);
  if (!roteiro || data !== hoje) return;
  saida.push({ json: { linha: k + 2, data, roteiro, artifact: String(linha.artifact ?? linha.arquivo ?? '').trim(),
    direcao: String(linha.direcao ?? linha.diretor ?? '').trim() } });
});
// nenhuma linha com a data de hoje: o fluxo para aqui, sem erro
return saida;"""

CASAR = r"""// Para cada linha de hoje, acha o .html na pasta 02 · Artifacts:
//   1. coluna "artifact" (nome do arquivo, ID ou link do Drive)
//   2. senão, arquivo com a data no nome: 2026-11-20 ..., 20-11-2026 ..., 20.11.2026 ...
//   3. senão, se só existe um .html na pasta, usa ele
const linhas = $('Linhas de hoje').all().map(i => i.json);
const arquivos = $input.all().map(i => i.json).filter(f => f.name && /\.html?$/i.test(f.name));
const sem = s => String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
const usados = new Set(), saida = [], faltando = [];
for (const l of linhas) {
  let f = null;
  if (l.artifact) {
    const alvo = sem(l.artifact).replace(/\.html?$/, '');
    f = arquivos.find(a => sem(a.name).replace(/\.html?$/, '') === alvo || l.artifact.includes(a.id));
  }
  if (!f) {
    const [a, m, d] = l.data.split('-');
    const formas = [`${a}-${m}-${d}`, `${d}-${m}-${a}`, `${d}.${m}.${a}`, `${d}_${m}_${a}`, `${a}${m}${d}`];
    f = arquivos.find(x => !usados.has(x.id) && formas.some(fm => x.name.includes(fm)));
  }
  if (!f && arquivos.length === 1 && linhas.length === 1) f = arquivos[0];
  if (!f) { faltando.push(`linha ${l.linha} (${l.data})`); continue; }
  usados.add(f.id);
  saida.push({ json: { ...l, id: f.id, arquivo: f.name, nome_video: f.name.replace(/\.html?$/i, '') } });
}
if (!saida.length) {
  throw new Error(`Tem roteiro para hoje (${faltando.join(', ')}), mas não achei o artifact na pasta 02 · Artifacts. ` +
    `Ponha a data no nome do arquivo (ex.: ${linhas[0].data} meu video.html) ou preencha a coluna "artifact". ` +
    `Arquivos na pasta: ${arquivos.map(a => a.name).join(', ') || 'nenhum .html'}`);
}
return saida;"""

MONTAR = r"""const cfg = $('Config').first().json;
const linhas = $('Casar roteiro com artifact').all().map(i => i.json);
const saida = [];
for (let i = 0; i < $input.all().length; i++) {
  const buf = await this.helpers.getBinaryDataBuffer(i, 'data');
  const l = linhas[i];
  saida.push({ json: {
    nome: l.nome_video,
    data: l.data,
    roteiro: l.roteiro,
    artifact_base64: buf.toString('base64'),
    opcoes: {
      shorts: cfg.gerar_shorts === 'sim', max_shorts: 3, trilha: true,
      clima_trilha: cfg.clima_trilha || 'reflexivo', trilha_arquivo: cfg.trilha_arquivo || null,
      narracao_vem_de: cfg.narracao_vem_de || 'auto',
      voz: cfg.voz || null,
      direcao: l.direcao || null
    }
  } });
}
return saida;"""

GUARDAR = r"""const linhas = $('Casar roteiro com artifact').all().map(i => i.json);
return [{ json: { jobs: $input.all().map((i, k) => ({ job_id: i.json.job_id, nome: linhas[k].nome_video, data: linhas[k].data })), voltas: 0 } }];"""

ANDAMENTO = r"""// Pergunta ao worker como está cada edição (fica em laço até todas terminarem, com limite de tempo)
const cfg = $('Config').first().json;
const limite = Number(cfg.limite_minutos) || 120;          // cada volta espera 1 min
if ($runIndex >= limite) {
  throw new Error(`As edições passaram de ${limite} minutos sem terminar. Veja os logs do fabrica-worker no Railway ` +
    `(jobs: ${$('Guardar jobs').first().json.jobs.map(j => j.job_id).join(', ')}).`);
}
const jobs = $('Guardar jobs').first().json.jobs;
const status = [];
for (const j of jobs) {
  let e = {};
  try { e = await this.helpers.httpRequest({ method: 'GET', url: `${cfg.worker_url}/jobs/${j.job_id}`, json: true, timeout: 30000 }); }
  catch (err) { e = { atual: 'sem resposta', concluido: false }; }   // worker reiniciando: tenta de novo na próxima volta
  const etapa = e.etapas?.[e.atual] || {};
  status.push({ ...j, atual: e.atual, concluido: !!e.concluido, erro: e.atual === 'erro' ? (etapa.erro || 'falhou') : null,
                progresso: etapa.total ? `${etapa.feitas}/${etapa.total}` : undefined });
}
return [{ json: { todos_terminaram: status.every(s => s.concluido), voltas: $runIndex + 1, jobs: status } }];"""

PRONTOS = r"""// Lista os arquivos prontos de cada edição que deu certo
const cfg = $('Config').first().json;
const st = $input.first().json.jobs;
const itens = [];
for (const j of st.filter(s => s.atual === 'concluido')) {
  const r = await this.helpers.httpRequest({ method: 'GET', url: `${cfg.worker_url}/jobs/${j.job_id}/resultado`, json: true, timeout: 30000 });
  for (const a of r.arquivos.filter(a => a.tipo !== 'metadados')) {
    itens.push({ json: { ...a, job_id: j.job_id, titulo_video: r.titulo, data: j.data, avisos: r.avisos || [],
      nota: r.qualidade ? r.qualidade.nota : null } });
  }
}
if (!itens.length) {
  throw new Error('Nenhuma edição terminou bem: ' + st.map(s => `${s.nome}: ${s.erro || s.atual}`).join(' | '));
}
return itens;"""

RESUMO = r"""const itens = $('Arquivos prontos').all().map(i => i.json);
const links = $input.all().map(i => i.json.webViewLink);
const erros = $('Ver andamento').last().json.jobs.filter(j => j.erro).map(j => `${j.nome}: ${j.erro}`);
const porVideo = {};
itens.forEach((a, k) => { (porVideo[a.titulo_video] ??= []).push({ tipo: a.tipo, nome: a.nome, link: links[k], titulo: a.titulo, legenda_post: a.legenda_post, hashtags: a.hashtags, nota: a.nota }); });
const linhas = [];
for (const [titulo, arqs] of Object.entries(porVideo)) {
  linhas.push(`✅ <b>${titulo}</b>`);
  for (const a of arqs) {
    if (a.tipo === 'longo') linhas.push(`🖥️ <a href="${a.link}">Vídeo longo 16:9</a>`);
    else if (a.tipo === 'short') linhas.push(`📱 <a href="${a.link}">${a.titulo || a.nome}</a>${a.legenda_post ? '\n' + a.legenda_post : ''}${a.hashtags ? '\n' + a.hashtags.join(' ') : ''}`);
    else if (a.tipo === 'descricao') linhas.push(`📝 <a href="${a.link}">Descrição do YouTube</a>`);
    else if (a.tipo === 'legenda') linhas.push(`💬 <a href="${a.link}">Legenda .srt</a>`);
    else if (a.tipo === 'relatorio') linhas.push(`🔎 <a href="${a.link}">Relatório de qualidade</a> · nota ${a.nota ?? '?'}/10`);
    else if (a.tipo === 'tempos') linhas.push(`⏱️ <a href="${a.link}">Tempo de cada cena</a>`);
  }
}
if (erros.length) linhas.push('', '❌ ' + erros.join('\n❌ '));
return [{ json: { texto: linhas.join('\n'), videos: porVideo, erros } }];"""

n = [
    node("Todo dia 6h13", "n8n-nodes-base.scheduleTrigger", 1.2, [0, -120], {"rule": {"interval": [{"field": "cronExpression", "expression": "13 6 * * *"}]}}),
    node("▶ Testar agora", "n8n-nodes-base.manualTrigger", 1, [0, 120], {}),
    node("Config", "n8n-nodes-base.set", 3.4, [220, 0], {"mode": "manual", "includeOtherFields": False, "assignments": {"assignments": [
        {"id": nid(), "name": k, "value": v, "type": "string"} for k, v in CAMPOS]}, "options": {}},
        notes="PREENCHA: ID da planilha e das pastas. voz: vazio (a do worker) | google | elevenlabs | kokoro_onnx. "
              "narracao_vem_de: auto | roteiro | artifact. testar_com_a_data: vazio (hoje) ou 2026-11-20. "
              "Telegram: ponha o chat_id e escolha a credencial no último nó.",
        notesInFlow=True),
    # o worker dorme quando parado (Railway): a primeira chamada o acorda, por isso o tempo longo e as novas tentativas
    http("Worker está no ar?", [440, 0], "GET", f"={{{{ {CFG}.worker_url }}}}/saude", None, 120000,
         retryOnFail=True, maxTries=4, waitBetweenTries=5000),
    node("Baixar planilha", "n8n-nodes-base.googleDrive", 3, [660, 0], {"operation": "download", "fileId": rl(f"={{{{ {CFG}.planilha_id }}}}"),
        "options": {"googleFileConversion": {"conversion": {"sheetsToFormat": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}}}},
        notes="Funciona com Excel (.xlsx) salvo no Drive ou com Planilha Google.", notesInFlow=True),
    node("Ler planilha", "n8n-nodes-base.extractFromFile", 1, [880, 0], {"operation": "xlsx", "binaryPropertyName": "data", "options": {"headerRow": True}}),
    code("Linhas de hoje", [1100, 0], LINHAS_DE_HOJE),
    node("Arquivos da pasta", "n8n-nodes-base.googleDrive", 3, [1320, 0], {"resource": "fileFolder", "searchMethod": "query",
        # o Drive só busca pelo começo das palavras; o filtro de .html fica no nó seguinte
        "queryString": "trashed = false", "returnAll": True,
        "filter": {"folderId": rl(f"={{{{ {CFG}.drive_pasta_artifacts }}}}"), "whatToSearch": "files"},
        "options": {"fields": ["id", "name"]}}, executeOnce=True, alwaysOutputData=True),
    code("Casar roteiro com artifact", [1540, 0], CASAR),
    node("Baixar artifact", "n8n-nodes-base.googleDrive", 3, [1760, 0], {"operation": "download", "fileId": rl("={{ $json.id }}"), "options": {}}),
    code("Montar pedido", [1980, 0], MONTAR),
    http("Enviar para edição", [2200, 0], "POST", f"={{{{ {CFG}.worker_url }}}}/edicao", "={{ JSON.stringify($json) }}", 120000),
    code("Guardar jobs", [2420, 0], GUARDAR),
    node("Esperar 1 min", "n8n-nodes-base.wait", 1.1, [2640, 0], {"resume": "timeInterval", "amount": 60, "unit": "seconds"}, webhookId=nid()),
    code("Ver andamento", [2860, 0], ANDAMENTO),
    iff("Todos terminaram?", [3080, 0], "={{ $json.todos_terminaram }}", "boolean", "true", single=True),
    code("Arquivos prontos", [3300, -100], PRONTOS),
    http("Baixar do worker", [3520, -100], "GET", f"={{{{ {CFG}.worker_url }}}}/arquivos/{{{{ $json.job_id }}}}/{{{{ $json.nome }}}}", None, 600000, arquivo=True),
    node("Salvar no Drive", "n8n-nodes-base.googleDrive", 3, [3740, -100], {
        "name": "={{ $('Arquivos prontos').item.json.data }} · {{ $('Arquivos prontos').item.json.titulo_video }} · {{ $('Arquivos prontos').item.json.nome }}",
        "driveId": rl("My Drive", "list"), "folderId": rl(f"={{{{ {CFG}.drive_pasta_prontos }}}}"), "inputDataFieldName": "data", "options": {}}),
    code("Resumo", [3960, -100], RESUMO),
    iff("Tem Telegram?", [4180, -100], f"={{{{ {CFG}.telegram_chat_id }}}}", "string", "notEmpty", single=True),
    # token fica numa credencial do n8n (não no fluxo): escolha a credencial "Telegram API" neste nó depois de importar
    node("Avisar no Telegram", "n8n-nodes-base.telegram", 1.2, [4400, -200], {
        "chatId": f"={{{{ {CFG}.telegram_chat_id }}}}", "text": "={{ $json.texto }}",
        "additionalFields": {"appendAttribution": False, "disable_web_page_preview": True, "parse_mode": "HTML"}}),
]
c = {}
def liga(a, b, saida=0):
    c.setdefault(a, {"main": []})
    while len(c[a]["main"]) <= saida:
        c[a]["main"].append([])
    c[a]["main"][saida].append({"node": b, "type": "main", "index": 0})
for a, b in [("Todo dia 6h13", "Config"), ("▶ Testar agora", "Config"), ("Config", "Worker está no ar?"),
             ("Worker está no ar?", "Baixar planilha"), ("Baixar planilha", "Ler planilha"), ("Ler planilha", "Linhas de hoje"),
             ("Linhas de hoje", "Arquivos da pasta"), ("Arquivos da pasta", "Casar roteiro com artifact"),
             ("Casar roteiro com artifact", "Baixar artifact"), ("Baixar artifact", "Montar pedido"),
             ("Montar pedido", "Enviar para edição"), ("Enviar para edição", "Guardar jobs"), ("Guardar jobs", "Esperar 1 min"),
             ("Esperar 1 min", "Ver andamento"), ("Ver andamento", "Todos terminaram?"),
             ("Arquivos prontos", "Baixar do worker"), ("Baixar do worker", "Salvar no Drive"), ("Salvar no Drive", "Resumo"),
             ("Resumo", "Tem Telegram?")]:
    liga(a, b)
liga("Todos terminaram?", "Arquivos prontos", 0)
liga("Todos terminaram?", "Esperar 1 min", 1)
liga("Tem Telegram?", "Avisar no Telegram", 0)
c["Tem Telegram?"]["main"].append([])
w = {"id": "fabRoteiroDoDia1", "name": "03 · Roteiro do dia (planilha + artifact → vídeos prontos)", "active": False,
     "nodes": n, "connections": c, "settings": {"executionOrder": "v1", "timezone": "America/Sao_Paulo"}, "pinData": {}}
saida = Path(__file__).resolve().parent.parent / "workflows" / "03_roteiro_do_dia.json"
saida.write_text(json.dumps(w, ensure_ascii=False, indent=2), encoding="utf-8")
print(saida, len(n), "nós")
