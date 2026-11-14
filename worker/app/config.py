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
# modelo do Whisper (alinhamento da voz Kokoro): fica no volume de dados, baixado na primeira vez que for usado
MODELOS_VOZ = Path(env("FABRICA_MODELOS_VOZ", str(MODELOS)))
PROMPTS = Path(env("FABRICA_PROMPTS", str(RAIZ / "prompts")))
RENDERER = Path(env("FABRICA_RENDERER", str(RAIZ / "renderer" / "render_artifact.mjs")))

# Claude (pauta e escolha dos shorts). O SDK lê ANTHROPIC_API_KEY sozinho.
MODELO_ROTEIRO = env("MODELO_ROTEIRO", "claude-opus-5-5")
ESFORCO_ROTEIRO = env("ESFORCO_ROTEIRO", "high")

# Tendências
YOUTUBE_API_KEY = env("YOUTUBE_API_KEY")
REDDIT_USER_AGENT = env("REDDIT_USER_AGENT", "fabrica-cult/1.0 (coleta de tendencias)")

# Sons e trilha: só arquivos locais. Procura primeiro no volume (dados/biblioteca) e depois na pasta "sons/"
# do repositório (sons/sfx/<categoria>/*.wav, sons/trilha/<clima>/*.mp3). Sem arquivo: efeito sintetizado.
SONS_REPO = Path(env("FABRICA_SONS", str(RAIZ / "sons")))

# Banco
DATABASE_URL = env("DATABASE_URL", "postgresql://fabrica:fabrica@postgres:5432/fabrica")

# Voz ("auto" usa a primeira configurada: elevenlabs > google > kokoro_onnx > estimado)
TTS_MOTOR = env("TTS_MOTOR", "auto")
KOKORO_VOZ = env("KOKORO_VOZ", "pm_alex")       # pm_alex, pm_santa, pf_dora
KOKORO_VELOCIDADE = float(env("KOKORO_VELOCIDADE", "1.0"))
ELEVENLABS_API_KEY = env("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = env("ELEVENLABS_VOICE_ID")
ELEVENLABS_MODELO = env("ELEVENLABS_MODELO", "eleven_multilingual_v2")
ELEVENLABS_VELOCIDADE = float(env("ELEVENLABS_VELOCIDADE", "1.0"))        # 0.7 a 1.2
ELEVENLABS_ESTABILIDADE = float(env("ELEVENLABS_ESTABILIDADE", "0.5"))     # mais alto = mais constante
# Google Cloud TTS: crie uma chave de API no Google Cloud com a "Cloud Text-to-Speech API" ativada.
# Vozes com tempo de cada palavra: pt-BR-Neural2-* e pt-BR-Wavenet-* (as Chirp3-HD não devolvem as marcas)
GOOGLE_TTS_API_KEY = env("GOOGLE_TTS_API_KEY")
GOOGLE_TTS_VOZ = env("GOOGLE_TTS_VOZ", "pt-BR-Neural2-B")
GOOGLE_TTS_VELOCIDADE = float(env("GOOGLE_TTS_VELOCIDADE", "1.05"))
GOOGLE_TTS_TOM = float(env("GOOGLE_TTS_TOM", "0"))

# Imagem (só entra quando o artifact pede, com marcadores data-arte / data-desenho / data-mapa)
FLUX_MODELO = env("FLUX_MODELO", "black-forest-labs/FLUX.1-schnell")
ANIMATED_DRAWINGS_CMD = env("ANIMATED_DRAWINGS_CMD", "")

# Render e acabamento
RENDER_PARALELO = int(env("RENDER_PARALELO", "3"))
FPS = int(env("FPS", "30"))
# altura do vídeo longo: 1080, 1440 ou 2160 (4K). Acima de 1080 o YouTube usa VP9/AV1 e a imagem fica mais limpa
RESOLUCAO = max(1080, int(env("RESOLUCAO", "1440")))   # o renderer não desce de 1080   # 1440p: o YouTube entrega em VP9/AV1, imagem bem mais nítida
MOTION_BLUR = int(env("MOTION_BLUR", "3"))       # subquadros por quadro em movimento (1 = desligado)
TEXTURA_PAPEL = float(env("TEXTURA_PAPEL", "0.07"))  # opacidade da textura de papel (0 = desligada)

# Ritmo
LUFS_ALVO = float(env("LUFS_ALVO", "-14"))

for p in (JOBS, BIBLIOTECA):
    p.mkdir(parents=True, exist_ok=True)
