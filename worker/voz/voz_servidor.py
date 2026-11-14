"""
Servidor de voz clonada: roda num ambiente Python próprio (cada modelo pede uma versão diferente
do transformers) e fica com o modelo carregado. O worker conversa com ele por stdin/stdout,
uma linha JSON por pedido.

    python voz_servidor.py qwen3        (Qwen3-TTS Base, Apache 2.0)
    python voz_servidor.py chatterbox   (Chatterbox Multilingual, MIT)

Pedido:  {"cmd": "falar", "texto": "...", "saida": "/tmp/x.wav", "ref": "/voz/referencia.wav",
          "ref_texto": "o que foi dito na referência (opcional)", "semente": 7,
          "exagero": 0.5, "ritmo": 0.5}
Resposta: {"ok": true, "duracao": 3.2, "sr": 24000}   ou   {"ok": false, "erro": "..."}

Variáveis: VOZ_MODELOS (pasta dos pesos), VOZ_DISPOSITIVO (auto|cpu|cuda), VOZ_THREADS.
"""
import json
import os
import sys
import time
import traceback

import numpy as np
import soundfile as sf
import torch

MOTOR = sys.argv[1] if len(sys.argv) > 1 else "qwen3"
PESOS = os.environ.get("VOZ_MODELOS", "/app/modelos/voz")
DISP = os.environ.get("VOZ_DISPOSITIVO", "auto")
if DISP == "auto":
    DISP = "cuda" if torch.cuda.is_available() else "cpu"
if os.environ.get("VOZ_THREADS"):
    torch.set_num_threads(int(os.environ["VOZ_THREADS"]))


def responder(d):
    sys.stdout.write(json.dumps(d, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def carregar():
    if MOTOR == "qwen3":
        from qwen_tts import Qwen3TTSModel
        pasta = os.path.join(PESOS, os.environ.get("QWEN3_PASTA", "qwen3_tts_base"))
        dtype = torch.bfloat16 if DISP == "cuda" else torch.float32
        return Qwen3TTSModel.from_pretrained(pasta, device_map=DISP if DISP == "cpu" else "cuda:0", dtype=dtype)
    if MOTOR == "chatterbox":
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        return ChatterboxMultilingualTTS.from_local(os.path.join(PESOS, "chatterbox_mtl"), DISP)
    raise SystemExit(f"motor desconhecido: {MOTOR}")


modelo = carregar()
prompts = {}  # cache da voz de referência (qwen3)


def falar(p):
    torch.manual_seed(int(p.get("semente", 7)))
    np.random.seed(int(p.get("semente", 7)))
    if MOTOR == "qwen3":
        chave = (p["ref"], p.get("ref_texto") or "")
        if chave not in prompts:
            if p.get("ref_texto"):
                prompts[chave] = modelo.create_voice_clone_prompt(ref_audio=p["ref"], ref_text=p["ref_texto"])
            else:
                prompts[chave] = modelo.create_voice_clone_prompt(ref_audio=p["ref"], x_vector_only_mode=True)
        wavs, sr = modelo.generate_voice_clone(text=p["texto"], language="Portuguese", voice_clone_prompt=prompts[chave])
        audio = np.asarray(wavs[0], dtype=np.float32)
    else:
        wav = modelo.generate(p["texto"], language_id="pt", audio_prompt_path=p["ref"],
                              exaggeration=float(p.get("exagero", 0.5)), cfg_weight=float(p.get("ritmo", 0.5)))
        audio, sr = wav.squeeze().cpu().numpy().astype(np.float32), modelo.sr
    sf.write(p["saida"], audio, sr)
    return {"ok": True, "duracao": len(audio) / sr, "sr": sr}


responder({"ok": True, "pronto": MOTOR, "dispositivo": DISP})
for linha in sys.stdin:
    try:
        p = json.loads(linha)
        if p.get("cmd") == "ping":
            responder({"ok": True, "motor": MOTOR, "dispositivo": DISP})
            continue
        t = time.time()
        r = falar(p)
        r["segundos"] = round(time.time() - t, 2)
        responder(r)
    except Exception as e:
        responder({"ok": False, "erro": f"{e}", "trace": traceback.format_exc()[-800:]})
