"""Gera n8n/workflows/06_preparar_elevenlabs.json (rode: python3 n8n/gerador/gerar_06_preparar_elevenlabs.py).

Rode UMA vez depois de pôr a chave da ElevenLabs no worker:
  1. confere se a voz ativa é a ElevenLabs e mostra o saldo
  2. mostra quantos sons a biblioteca moderna vai ter
  3. com gerar_sons = sim, gera os sons (uma vez só; os vídeos reaproveitam para sempre)
"""
import json
import uuid
from pathlib import Path

_c = [0]


def nid():
    _c[0] += 1
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"fab06-{_c[0]}"))


def node(name, typ, ver, pos, params, **kw):
    n = {"id": nid(), "name": name, "type": typ, "typeVersion": ver, "position": pos, "parameters": params}
    n.update(kw)
    return n


CFG = "$('Config').first().json"


def http(name, pos, method, url, body=None, timeout=120000):
    p = {"method": method, "url": url, "options": {"timeout": timeout}}
    if body:
        p.update({"sendBody": True, "specifyBody": "json", "jsonBody": body})
    return node(name, "n8n-nodes-base.httpRequest", 4.2, pos, p)


def code(name, pos, js):
    return node(name, "n8n-nodes-base.code", 2, pos, {"mode": "runOnceForAllItems", "jsCode": js})


CAMPOS = [
    ("worker_url", "http://fabrica-worker.railway.internal:8000"),
    ("gerar_sons", "nao"),
    ("limite_creditos_sons", "1500"),
]

n = [
    node("▶ Preparar agora", "n8n-nodes-base.manualTrigger", 1, [0, 0], {}),
    node("Config", "n8n-nodes-base.set", 3.4, [220, 0], {"mode": "manual", "includeOtherFields": False, "assignments": {"assignments": [
        {"id": nid(), "name": k, "value": v, "type": "string"} for k, v in CAMPOS]}, "options": {}},
        notes="1ª vez: deixe gerar_sons = nao e rode para ver o saldo e a prévia. Depois ponha sim e rode de novo.",
        notesInFlow=True),
    http("Estado do worker", [440, 0], "GET", f"={{{{ {CFG}.worker_url }}}}/saude", None, 120000),
    code("Conferir voz", [660, 0], """const s = $json;
const ativa = s.voz && s.voz.ativa;
if (ativa !== 'elevenlabs') {
  throw new Error(`A voz ativa do worker é "${ativa}". No Railway (serviço fabrica-worker → Variables) confira ` +
    `ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID e TTS_MOTOR=elevenlabs.`);
}
const el = s.voz.elevenlabs || {};
return [{ json: { voz: ativa, modelo: el.modelo, saldo: el.saldo, sons: s.sons_biblioteca } }];"""),
    http("Biblioteca de sons", [880, 0], "POST", f"={{{{ {CFG}.worker_url }}}}/sfx/biblioteca",
         f"={{{{ JSON.stringify({{ confirmar: {CFG}.gerar_sons === 'sim', limite_creditos: Number({CFG}.limite_creditos_sons) || 1500 }}) }}}}",
         1800000),
    code("Resultado", [1100, 0], """const v = $('Conferir voz').first().json;
const r = $json;
return [{ json: {
  voz: `${v.voz} · modelo ${v.modelo}`,
  saldo_elevenlabs: v.saldo ? v.saldo.restante : 'não consegui ler (dê à chave a permissão User: read)',
  sons: r.previa ? `${r.previa.a_gerar} sons a gerar (${r.previa.segundos_a_gerar} s de áudio). Para gerar: gerar_sons = sim`
                 : `${(r.gerados || []).length} sons gerados · créditos gastos: ${r.creditos_gastos ?? '?'} · saldo: ${r.saldo ?? '?'}`,
  erros: r.erros || []
} }];"""),
]
c = {}
for a, b in zip([x["name"] for x in n], [x["name"] for x in n][1:]):
    c[a] = {"main": [[{"node": b, "type": "main", "index": 0}]]}
w = {"id": "fabPrepararEleven1", "name": "06 · Preparar ElevenLabs (conferir voz + sons modernos)", "active": False,
     "nodes": n, "connections": c, "settings": {"executionOrder": "v1", "timezone": "America/Sao_Paulo"}, "pinData": {}}
saida = Path(__file__).resolve().parent.parent / "workflows" / "06_preparar_elevenlabs.json"
saida.write_text(json.dumps(w, ensure_ascii=False, indent=2), encoding="utf-8")
print(saida, len(n), "nós")
