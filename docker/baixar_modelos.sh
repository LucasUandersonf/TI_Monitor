#!/usr/bin/env bash
# Baixa os modelos e dados usados pela edição (roda no build do Docker; pode rodar de novo à mão).
#   Kokoro-82M v1.0 ONNX quantizado + vozes pt-BR (Apache 2.0)   ~ 92 MB
#   Piper pt_BR-faber-medium (voz alternativa, MIT)                ~ 63 MB   (PIPER=0 pula)
#   Natural Earth 1:50m admin-0 map units (domínio público)       ~ 3 MB -> mundo_pt.json
set -euo pipefail
DEST="${1:-/app/modelos}"
HF=https://huggingface.co
mkdir -p "$DEST/kokoro" "$DEST/piper" "$DEST/natural_earth"

curl -fsSL -o "$DEST/kokoro/model_quantized.onnx" "$HF/onnx-community/Kokoro-82M-v1.0-ONNX/resolve/main/onnx/model_quantized.onnx"
for v in pm_alex pm_santa pf_dora; do
  curl -fsSL -o "$DEST/kokoro/$v.bin" "$HF/onnx-community/Kokoro-82M-v1.0-ONNX/resolve/main/voices/$v.bin"
done
python3 - "$DEST/kokoro" <<'PY'
import sys, numpy as np, pathlib
d = pathlib.Path(sys.argv[1])
vozes = {v: np.fromfile(d / f"{v}.bin", dtype=np.float32).reshape(-1, 1, 256) for v in ("pm_alex", "pm_santa", "pf_dora")}
with open(d / "voices_ptbr.bin", "wb") as f:
    np.savez(f, **vozes)
PY

if [ "${PIPER:-1}" = "1" ]; then
  B="$HF/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium"
  curl -fsSL -o "$DEST/piper/pt_BR-faber-medium.onnx" "$B/pt_BR-faber-medium.onnx"
  curl -fsSL -o "$DEST/piper/pt_BR-faber-medium.onnx.json" "$B/pt_BR-faber-medium.onnx.json"
fi

curl -fsSL -o /tmp/ne50.geojson https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_map_units.geojson
cd /app/worker && FABRICA_MODELOS="$DEST" python3 -c "from pathlib import Path; from app.etapas import mapas; print(mapas.preparar(Path('/tmp/ne50.geojson')))"
rm -f /tmp/ne50.geojson
echo "modelos prontos em $DEST"
