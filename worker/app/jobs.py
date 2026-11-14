"""Estado de cada produção em disco: dados/jobs/<id>/ (roteiro.json, estado.json, audio/, video/...)."""
import json
import re
import time
import unicodedata
from pathlib import Path

from .config import JOBS


def slug(txt: str, n: int = 40) -> str:
    t = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:n] or "video"


def pasta(job_id: str) -> Path:
    p = JOBS / job_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def novo_id(titulo: str) -> str:
    """Único por envio: data-hora + nome (dois envios do mesmo arquivo não se misturam)."""
    return time.strftime("%Y-%m-%d-%H%M%S-") + slug(titulo, 30)


def ler(job_id: str, nome: str = "roteiro.json"):
    return json.loads((pasta(job_id) / nome).read_text(encoding="utf-8"))


def gravar(job_id: str, dados, nome: str = "roteiro.json") -> Path:
    p = pasta(job_id) / nome
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def etapa(job_id: str, nome: str, status: str, **extra):
    """Registra o andamento (o n8n consulta GET /jobs/<id>)."""
    p = pasta(job_id) / "estado.json"
    est = json.loads(p.read_text()) if p.exists() else {"job_id": job_id, "etapas": {}}
    est["etapas"][nome] = {"status": status, "em": time.strftime("%Y-%m-%dT%H:%M:%S"), **extra}
    est["atual"] = nome
    p.write_text(json.dumps(est, ensure_ascii=False, indent=2))
    return est
