"""Gera n8n/workflows/04_cadastrar_minha_voz.json (rode: python3 n8n/gerador/gerar_04_cadastrar_voz.py)."""
import json
import uuid
from pathlib import Path

_c = [0]


def nid():
    _c[0] += 1
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"fab04-{_c[0]}"))


def node(name, typ, ver, pos, params, **kw):
    n = {"id": nid(), "name": name, "type": typ, "typeVersion": ver, "position": pos, "parameters": params}
    n.update(kw)
    return n


CFG = "$('Config').first().json"


def http(name, pos, method, url, body=None, timeout=120000, arquivo=False):
    p = {"method": method, "url": url, "options": {"timeout": timeout}}
    if body:
        p.update({"sendBody": True, "specifyBody": "json", "jsonBody": body})
    if arquivo:
        p["options"]["response"] = {"response": {"responseFormat": "file", "outputPropertyName": "data"}}
    return node(name, "n8n-nodes-base.httpRequest", 4.2, pos, p)


def code(name, pos, js):
    return node(name, "n8n-nodes-base.code", 2, pos, {"mode": "runOnceForAllItems", "jsCode": js})


def rl(v, mode="id"):
    return {"__rl": True, "mode": mode, "value": v}


CAMPOS = [
    ("worker_url", "https://SEU-WORKER.up.railway.app"),
    ("drive_pasta_voz", "COLE_AQUI_O_ID_DA_PASTA_04_MINHA_VOZ"),
    ("nome_do_arquivo", "minha_voz.m4a"),
    ("frase_de_teste", "Seu cérebro não está procurando a verdade. Está procurando conforto. E em 2023, 90 MI de pessoas provaram isso."),
    ("motores_para_comparar", "clone_qwen3,clone_chatterbox,kokoro_onnx"),
]

n = [
    node("▶ Cadastrar agora", "n8n-nodes-base.manualTrigger", 1, [0, 0], {}),
    node("Config", "n8n-nodes-base.set", 3.4, [220, 0], {"mode": "manual", "includeOtherFields": False, "assignments": {"assignments": [
        {"id": nid(), "name": k, "value": v, "type": "string"} for k, v in CAMPOS]}, "options": {}},
        notes="Grave 20 a 30 s falando como narrador, num lugar silencioso (celular serve). Ponha o arquivo na pasta 04 · Minha voz.",
        notesInFlow=True),
    http("Worker está no ar?", [440, 0], "GET", f"={{{{ {CFG}.worker_url }}}}/saude", None, 60000),
    node("Procurar gravação", "n8n-nodes-base.googleDrive", 3, [660, 0], {"resource": "fileFolder", "searchMethod": "name",
        "queryString": f"={{{{ {CFG}.nome_do_arquivo.replace(/\\.[^.]+$/, '') }}}}", "returnAll": True,
        "filter": {"folderId": rl(f"={{{{ {CFG}.drive_pasta_voz }}}}"), "whatToSearch": "files"},
        "options": {"fields": ["id", "name"]}}, alwaysOutputData=True),
    code("Achou?", [880, 0], f"""const alvo = {CFG}.nome_do_arquivo.trim().toLowerCase();
const achados = $input.all().map(i => i.json).filter(f => f.name);
const f = achados.find(x => x.name.toLowerCase() === alvo) || achados.find(x => /\\.(wav|mp3|m4a|ogg|opus|webm|aac|flac)$/i.test(x.name));
if (!f) throw new Error(`Não achei a gravação "${{alvo}}" na pasta da voz. Achei: ${{achados.map(x => x.name).join(', ') || 'nada'}}`);
return [{{ json: f }}];"""),
    node("Baixar gravação", "n8n-nodes-base.googleDrive", 3, [1100, 0], {"operation": "download", "fileId": rl("={{ $json.id }}"), "options": {}}),
    code("Montar pedido", [1320, 0], """const buf = await this.helpers.getBinaryDataBuffer(0, 'data');
return [{ json: { audio_base64: buf.toString('base64'), nome_arquivo: $('Achou?').first().json.name } }];"""),
    http("Cadastrar voz no worker", [1540, 0], "POST", f"={{{{ {CFG}.worker_url }}}}/voz/referencia", "={{ JSON.stringify($json) }}", 900000),
    http("Gerar prévias", [1760, 0], "POST", f"={{{{ {CFG}.worker_url }}}}/voz/teste",
         f"={{{{ JSON.stringify({{ texto: {CFG}.frase_de_teste, motores: {CFG}.motores_para_comparar.split(',').map(s => s.trim()).filter(Boolean) }}) }}}}",
         3600000),
    code("Uma prévia por item", [1980, 0], """const r = $json.resultados.filter(x => x.arquivo);
if (!r.length) throw new Error('Nenhuma prévia foi gerada: ' + JSON.stringify($json.resultados));
return r.map(x => ({ json: x }));"""),
    http("Baixar prévia", [2200, 0], "GET", f"={{{{ {CFG}.worker_url }}}}/voz/arquivo/{{{{ $json.arquivo }}}}", None, 120000, arquivo=True),
    node("Salvar prévia no Drive", "n8n-nodes-base.googleDrive", 3, [2420, 0], {
        "name": "=prévia · {{ $('Uma prévia por item').item.json.motor }}.wav",
        "driveId": rl("My Drive", "list"), "folderId": rl(f"={{{{ {CFG}.drive_pasta_voz }}}}"), "inputDataFieldName": "data", "options": {}}),
    code("Resultado", [2640, 0], """const cad = $('Cadastrar voz no worker').first().json;
const prev = $('Uma prévia por item').all().map(i => i.json);
const links = $input.all().map(i => i.json.webViewLink);
return [{ json: {
  voz_cadastrada: cad.ok, trecho_usado_segundos: cad.duracao_referencia, fala_acima_do_ruido_db: cad.fala_acima_do_ruido_db,
  transcricao_do_trecho: cad.transcricao, avisos: cad.avisos,
  previas: prev.map((p, k) => ({ motor: p.motor, segundos_para_gerar: p.segundos_para_gerar, link: links[k] })),
  proximo_passo: 'Ouça as prévias. Para usar a sua voz nos vídeos, deixe VOZ_CLONE_MOTOR no worker com o motor que preferir (qwen3 ou chatterbox).'
} }];"""),
]
c = {}
for a, b in zip([x["name"] for x in n], [x["name"] for x in n][1:]):
    c[a] = {"main": [[{"node": b, "type": "main", "index": 0}]]}
w = {"id": "fabCadastrarVoz1", "name": "04 · Cadastrar minha voz (gravação no Drive → voz clonada + prévias)", "active": False,
     "nodes": n, "connections": c, "settings": {"executionOrder": "v1", "timezone": "America/Sao_Paulo"}, "pinData": {}}
saida = Path(__file__).resolve().parent.parent / "workflows" / "04_cadastrar_minha_voz.json"
saida.write_text(json.dumps(w, ensure_ascii=False, indent=2), encoding="utf-8")
print(saida, len(n), "nós")
