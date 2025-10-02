# collector/collector.py
import os
import logging
import json
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from .database import SessionLocal, engine, Base
from .models import Metric
from sqlalchemy import desc

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN", "changeme")
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI()
templates = Jinja2Templates(directory=TEMPLATES_DIR)
Base.metadata.create_all(bind=engine)

# Payload atualizado com unidades de disco
class DiskUnit(BaseModel):
    name: str
    used_gb: float
    total_gb: float

class MetricPayload(BaseModel):
    host: str
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    disk_units: list[DiskUnit]
    timestamp: int

def verify_token(token: str):
    if not token or token != API_TOKEN:
        logging.warning("Token inválido recebido")
        raise HTTPException(status_code=401, detail="Token inválido")

@app.post("/api/v1/metrics")
def receive_metrics(payload: MetricPayload, token: str = Header(...)):
    verify_token(token)
    db = SessionLocal()
    try:
        m = Metric(
            host=payload.host,
            cpu_percent=payload.cpu_percent,
            memory_percent=payload.memory_percent,
            memory_used_gb=payload.memory_used_gb,
            memory_total_gb=payload.memory_total_gb,
            disk_percent=payload.disk_percent,
            disk_used_gb=payload.disk_used_gb,
            disk_total_gb=payload.disk_total_gb,
            disk_units=json.dumps([u.dict() for u in payload.disk_units]),
            timestamp=payload.timestamp
        )
        db.add(m)
        db.commit()
        logging.info(f"Recebido métricas de {payload.host}")
        return {"status": "ok"}
    except Exception as e:
        db.rollback()
        logging.error(f"Erro ao salvar métrica: {e}")
        raise HTTPException(status_code=500, detail="Erro interno")
    finally:
        db.close()

@app.get("/api/v1/metrics", response_class=JSONResponse)
def get_metrics(token: str = Header(...), limit: int = Query(100, ge=1, le=1000)):
    verify_token(token)
    db = SessionLocal()
    try:
        rows = db.query(Metric).order_by(desc(Metric.timestamp)).limit(limit).all()
        result = [
            {
                "host": r.host,
                "cpu_percent": r.cpu_percent,
                "memory_percent": r.memory_percent,
                "memory_used_gb": r.memory_used_gb,
                "memory_total_gb": r.memory_total_gb,
                "disk_percent": r.disk_percent,
                "disk_used_gb": r.disk_used_gb,
                "disk_total_gb": r.disk_total_gb,
                "disk_units": r.disk_units,
                "timestamp": r.timestamp
            }
            for r in rows
        ]
        return result
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request, "token": API_TOKEN})
