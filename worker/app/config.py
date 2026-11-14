"""Configuração central do worker. Tudo vem de variáveis de ambiente (ver .env.exemplo)."""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent  # pasta do projeto (no container: /app)


def env(nome: str, padrao: str = "", *apelidos: str) -> str:
    for n in (nome, *apelidos):
        if os.environ.get(n):
            return os.environ[n]
    return padrao


DADOS = Path(env("FABRICA_DADOS", str(RAIZ / "dados")))
JOBS = DADOS / "jobs"
BIBLIOTECA = DADOS / "biblioteca"          # sincronizada com a pasta do Drive (sfx, trilhas, voz, lottie, desenhos)
MODELOS = Path(env("FABRICA_MODELOS", str(RAIZ / "modelos")))   # Kokoro ONNX, Natural Earth (baixados no build)
# vozes clonadas e Whisper (~6 GB): ficam no volume de dados, baixadas uma vez na primeira vez que forem usadas
MODELOS_VOZ = Path(env("FABRICA_MODELOS_VOZ", str(MODELOS)))
PROMPTS = Path(env("FABRICA_PROMPTS", str(RAIZ / "prompts")))
RENDERER = Path(env("FABRICA_RENDERER", str(RAIZ / "renderer" / "render_artifact.mjs")))

# Claude (pauta e escolha dos shorts). O SDK lê ANTHROPIC_API_KEY sozinho.
MODELO_ROTEIRO = env("MODELO_ROTEIRO", "claude-opus-5-5")
ESFORCO_ROTEIRO = env("ESFORCO_ROTEIRO", "high")

# Tendências
YOUTUBE_API_KEY = env("YOUTUBE_API_KEY")
REDDIT_USER_AGENT = env("REDDIT_USER_AGENT", "fabrica-cult/1.0 (coleta de tendencias)")

# Sons e trilha
FREESOUND_TOKEN = env("FREESOUND_TOKEN", "", "FREESOUND_API_KEY")
OPENVERSE_ATIVO = env("OPENVERSE_ATIVO", "1") == "1"
ACE_STEP_CMD = env("ACE_STEP_CMD", "")          # ex.: "acestep --prompt {prompt} --duration {duracao} --output {saida}"

# Banco
DATABASE_URL = env("DATABASE_URL", "postgresql://fabrica:fabrica@postgres:5432/fabrica")

# Voz ("auto" usa a melhor disponível: elevenlabs > chatterbox > kokoro_onnx > kokoro > piper > estimado)
TTS_MOTOR = env("TTS_MOTOR", "auto")
TTS_VOZ_REFERENCIA = env("TTS_VOZ_REFERENCIA", str(BIBLIOTECA / "voz" / "referencia.wav"))
KOKORO_VOZ = env("KOKORO_VOZ", "pm_alex")       # pm_alex, pm_santa, pf_dora
KOKORO_VELOCIDADE = float(env("KOKORO_VELOCIDADE", "1.0"))
ELEVENLABS_API_KEY = env("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = env("ELEVENLABS_VOICE_ID")
ELEVENLABS_MODELO = env("ELEVENLABS_MODELO", "eleven_multilingual_v2")
PIPER_MODEL = env("PIPER_MODEL", str(MODELOS / "piper" / "pt_BR-faber-medium.onnx"))
PIPER_BIN = env("PIPER_BIN", "piper")

# Voz clonada grátis (sua voz): qwen3 (mais rápido em CPU) ou chatterbox (mais expressivo, melhor com GPU)
VOZ_CLONE_MOTOR = env("VOZ_CLONE_MOTOR", "qwen3")

# Sincronia
WHISPERX_MODELO = env("WHISPERX_MODELO", "large-v3")
RHUBARB_BIN = env("RHUBARB_BIN", "rhubarb")

# Imagem (só entra quando o artifact pede, com marcadores data-arte / data-desenho / data-mapa)
FLUX_MODELO = env("FLUX_MODELO", "black-forest-labs/FLUX.1-schnell")
ANIMATED_DRAWINGS_CMD = env("ANIMATED_DRAWINGS_CMD", "")

# Render e acabamento
TRANSICAO_MOTOR = env("TRANSICAO_MOTOR", "xfade")  # xfade | gltransition
GL_TRANSITIONS_DIR = Path(env("GL_TRANSITIONS_DIR", "/opt/gl-transitions/transitions"))
RENDER_PARALELO = int(env("RENDER_PARALELO", "3"))
FPS = int(env("FPS", "30"))
# altura do vídeo longo: 1080, 1440 ou 2160 (4K). Acima de 1080 o YouTube usa VP9/AV1 e a imagem fica mais limpa
RESOLUCAO = int(env("RESOLUCAO", "1080"))
MOTION_BLUR = int(env("MOTION_BLUR", "3"))       # subquadros por quadro em movimento (1 = desligado)
TEXTURA_PAPEL = float(env("TEXTURA_PAPEL", "0.07"))  # opacidade da textura de papel (0 = desligada)

# Ritmo
LUFS_ALVO = float(env("LUFS_ALVO", "-14"))

for p in (JOBS, BIBLIOTECA):
    p.mkdir(parents=True, exist_ok=True)
