# Worker de edição: Python (API + áudio) + Node/Playwright (render do artifact) + FFmpeg + Kokoro (voz grátis)
# CPU:  docker build -t fabrica-worker .
# GPU:  docker build --build-arg BASE=pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime --build-arg IA=1 -t fabrica-worker-gpu .
ARG BASE=python:3.12-slim-bookworm
FROM ${BASE}
ARG IA=0
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg curl unzip ca-certificates fontconfig espeak-ng \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# fontes da marca (as mesmas do artifact) para título e legenda dos verticais
COPY docker/baixar_fontes.sh /tmp/
RUN bash /tmp/baixar_fontes.sh /usr/share/fonts/truetype/fabrica && fc-cache -f

WORKDIR /app
COPY worker/requirements*.txt worker/
RUN pip install --no-cache-dir -r worker/requirements.txt \
    && if [ "$IA" = "1" ]; then pip install --no-cache-dir -r worker/requirements-ia.txt; fi

COPY renderer/package.json renderer/
RUN cd renderer && npm install --omit=dev && npx playwright install --with-deps chromium

COPY renderer/ renderer/
COPY worker/ worker/
COPY prompts/ prompts/
# sua pasta de efeitos e trilhas (sons/sfx/<categoria>/, sons/trilha/<clima>/)
COPY sons/ sons/
COPY docker/baixar_modelos.sh docker/

# Kokoro ONNX + vozes pt-BR e Natural Earth (mapas com nomes em português)
RUN bash docker/baixar_modelos.sh /app/modelos

ENV FABRICA_DADOS=/dados FABRICA_PROMPTS=/app/prompts FABRICA_MODELOS=/app/modelos FABRICA_MODELOS_VOZ=/dados/modelos \
    FABRICA_RENDERER=/app/renderer/render_artifact.mjs FABRICA_SONS=/app/sons
WORKDIR /app/worker
EXPOSE 8000
# Railway (e outros) passam a porta em $PORT; "::" escuta em IPv4 e IPv6 (a rede interna do Railway usa IPv6)
CMD ["sh", "-c", "uvicorn app.main:app --host :: --port ${PORT:-8000}"]
