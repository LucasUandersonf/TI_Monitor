# agent/agent.py
import os
import time
import socket
import psutil
import logging
from dotenv import load_dotenv
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
from datetime import datetime

load_dotenv()

COLLECTOR_URL = os.getenv("COLLECTOR_URL", "http://localhost:8000/api/v1/metrics")
API_TOKEN = os.getenv("API_TOKEN", "changeme")
INTERVAL = int(os.getenv("INTERVAL_SECONDS", "100"))
HOST_OVERRIDE = os.getenv("HOST_OVERRIDE")  # útil para testes locais

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Requests session com retries
session = requests.Session()
retries = Retry(total=3, backoff_factor=2, status_forcelist=(500,502,503,504))
session.mount("http://", HTTPAdapter(max_retries=retries))
session.mount("https://", HTTPAdapter(max_retries=retries))

FALLBACK_LOG = os.getenv("FALLBACK_LOG", "agent_fallback.log")

def collect():
    host = HOST_OVERRIDE or socket.gethostname()
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    # coleta de todas as unidades/discos do servidor
    disk_units = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disk_units.append({
                "name": part.device,
                "used_gb": round(usage.used / (1024**3), 2),
                "total_gb": round(usage.total / (1024**3), 2)
            })
        except PermissionError:
            continue  # ignorar partições inacessíveis

    payload = {
        "host": host,
        "cpu_percent": cpu,
        "memory_percent": mem.percent,
        "memory_used_gb": round(mem.used / (1024**3), 2),
        "memory_total_gb": round(mem.total / (1024**3), 2),
        "disk_percent": disk.percent,
        "disk_used_gb": round(disk.used / (1024**3), 2),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "disk_units": disk_units,   # NOVO: lista de unidades
        "timestamp": int(time.time())
    }
    return payload

def fallback_store(payload):
    try:
        with open(FALLBACK_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.utcnow().isoformat(), "payload": payload}) + "\n")
        logging.info("Salvo fallback localmente")
    except Exception as e:
        logging.error(f"Erro ao gravar fallback: {e}")

def send(payload):
    headers = {"token": API_TOKEN, "Content-Type": "application/json"}
    try:
        resp = session.post(COLLECTOR_URL, json=payload, headers=headers, timeout=8)
        if resp.status_code == 200:
            logging.info(f"Enviado: {payload['host']}")
        else:
            logging.warning(f"Resposta inesperada {resp.status_code}: {resp.text}")
            fallback_store(payload)
    except Exception as e:
        logging.error(f"Erro no envio: {e}")
        fallback_store(payload)

def main():
    logging.info("Agent iniciado")
    while True:
        try:
            data = collect()
            logging.debug(f"Dados coletados: {data}")
            send(data)
        except Exception as e:
            logging.error(f"Erro no loop do agente: {e}")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()