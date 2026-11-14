# Worker de edição: Python (API + áudio) + Node/Playwright (render do artifact) + FFmpeg + Rhubarb + modelos
# CPU:  docker build -t fabrica-worker .
# GPU:  docker build --build-arg BASE=pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime --build-arg IA=1 -t fabrica-worker-gpu .
ARG BASE=python:3.12-slim-bookworm
FROM ${BASE}
ARG IA=0
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg curl unzip git ca-certificates fontconfig espeak-ng \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Rhubarb Lip Sync (boca sincronizada)
RUN curl -fsSL -o /tmp/rh.zip https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v1.14.0/Rhubarb-Lip-Sync-1.14.0-Linux.zip \
    && unzip -q /tmp/rh.zip -d /opt && ln -s /opt/Rhubarb-Lip-Sync-1.14.0-Linux/rhubarb /usr/local/bin/rhubarb && rm /tmp/rh.zip

# gl-transitions (shaders GLSL; usados se o FFmpeg tiver o filtro gltransition)
RUN git clone --depth 1 https://github.com/gl-transitions/gl-transitions /opt/gl-transitions

# fontes da marca (as mesmas do artifact) para título e legenda dos verticais
COPY docker/baixar_fontes.sh /tmp/
RUN bash /tmp/baixar_fontes.sh /usr/share/fonts/truetype/fabrica && fc-cache -f

WORKDIR /app
COPY worker/requirements*.txt worker/
RUN pip install --no-cache-dir -r worker/requirements.txt \
    && if [ "$IA" = "1" ]; then pip install --no-cache-dir -r worker/requirements-ia.txt; fi

# ---------- voz clonada grátis: um ambiente Python por modelo (cada um pede uma versão do transformers)
# PyTorch: na imagem GPU já vem; na de CPU instala a versão só-CPU (bem menor)
ARG VOZ_CLONE=1
RUN if [ "$VOZ_CLONE" = "1" ]; then \
      (python -c "import torch" 2>/dev/null || pip install --no-cache-dir torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cpu) && \
      python -m venv --system-site-packages /opt/voz/qwen3 && \
      /opt/voz/qwen3/bin/pip install --no-cache-dir qwen-tts soundfile && \
      python -m venv --system-site-packages /opt/voz/chatterbox && \
      /opt/voz/chatterbox/bin/pip install --no-cache-dir "numpy==1.26.4" "librosa==0.10.0" "resampy==0.4.3" s3tokenizer \
        "transformers==4.46.3" "diffusers==0.29.0" "omegaconf==2.3.0" "resemble-perth==1.0.1" "silero-vad==5.1.2" \
        "conformer==0.3.2" safetensors soundfile huggingface_hub && \
      /opt/voz/chatterbox/bin/pip install --no-cache-dir --no-deps "chatterbox-tts==0.1.7" ; \
    fi

COPY renderer/package.json renderer/
RUN cd renderer && npm install --omit=dev && npx playwright install --with-deps chromium

COPY renderer/ renderer/
COPY worker/ worker/
COPY prompts/ prompts/
COPY docker/baixar_modelos.sh docker/

# Kokoro ONNX + vozes pt-BR, Piper pt-BR e Natural Earth (mapas com nomes em português)
RUN bash docker/baixar_modelos.sh /app/modelos

ENV FABRICA_DADOS=/dados FABRICA_PROMPTS=/app/prompts FABRICA_MODELOS=/app/modelos FABRICA_MODELOS_VOZ=/dados/modelos \
    VOZ_PYTHON_QWEN3=/opt/voz/qwen3/bin/python VOZ_PYTHON_CHATTERBOX=/opt/voz/chatterbox/bin/python \
    FABRICA_RENDERER=/app/renderer/render_artifact.mjs PIPER_MODEL=/app/modelos/piper/pt_BR-faber-medium.onnx
WORKDIR /app/worker
EXPOSE 8000
# Railway (e outros) passam a porta em $PORT
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
