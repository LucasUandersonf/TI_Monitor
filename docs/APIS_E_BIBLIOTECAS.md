# APIs e bibliotecas usadas na edição

Inventário do que a Fábrica Cult **usa hoje**, o que cada peça faz, se é obrigatória e **se foi testada de verdade** no desenvolvimento. As licenças vêm de conhecimento geral e não foram reconferidas; confirme antes de distribuir o código ou usar comercialmente.

Legenda do teste: ✅ rodou de ponta a ponta · 🔌 código pronto, não testado ao vivo (rede bloqueada ou precisa de GPU/chave)

## 1. Voz (narração)

O worker escolhe sozinho a melhor disponível (`TTS_MOTOR=auto`), nesta ordem:

| Motor | Licença | Precisa | Teste | Observação |
|---|---|---|---|---|
| **ElevenLabs** (`/with-timestamps`) | serviço pago | `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` | 🔌 | Também devolve o tempo de cada letra |
| **Sua voz clonada: Qwen3-TTS Base 0.6B** (`qwen-tts`) | Apache 2.0 ✅ | voz cadastrada; CPU ou GPU | ✅ | Padrão para clonagem. Semelhança 0,925 com a referência; ~4 s de CPU por 1 s de fala |
| **Sua voz clonada: Chatterbox Multilingual** (`chatterbox-tts` 0.1.7) | MIT ✅ | voz cadastrada; melhor com GPU | ✅ | `VOZ_CLONE_MOTOR=chatterbox`. Semelhança 0,939; ~6,4 s de CPU por 1 s de fala |
| **Kokoro-82M v1.0 ONNX** (quantizado) via `kokoro-onnx` | Apache 2.0 | CPU | ✅ | Vozes `pm_alex`, `pm_santa`, `pf_dora`; usada quando não há voz cadastrada |
| Kokoro (PyTorch) | Apache 2.0 | CPU/GPU | 🔌 | Mesmas vozes, se preferir o pacote `kokoro` |
| **Piper** `pt_BR-faber-medium` | MIT (voz: ver card) | CPU | ✅ | Voz local alternativa |

Detalhes, gravação e medições: `docs/VOZ_CLONADA.md`.

Pesquisadas e **não usadas** por causa da licença (proíbem uso comercial, e o canal é monetizado): XTTS-v2 (Coqui Public Model License), F5-TTS (CC-BY-NC), Fish Speech / OpenAudio (CC-BY-NC-SA).

⚠️ `kokoro-onnx` puxa `phonemizer` e o espeak-ng (GPL-3.0). Usar no seu servidor não traz obrigação; só pesa se você distribuir o software.

## 2. Sincronia

| Peça | Licença | Teste | Uso |
|---|---|---|---|
| **WhisperX** | BSD | 🔌 (GPU recomendada) | Tempo exato de cada palavra (alinhamento forçado com o texto do artifact) |
| **faster-whisper** (modelo small, int8) | MIT | ✅ | Em CPU: tempo de cada palavra (~2 s por cena) e conferência da voz clonada (refaz a frase se a fala não bater com o texto) |
| Preparação do texto para fala (nossa) | — | ✅ | Números, dinheiro, porcentagem e ordinais por extenso; dicionário de pronúncia `biblioteca/voz/pronuncia.txt` |
| Alinhamento por energia (nosso) | — | ✅ | Sem WhisperX: acha as pausas reais no áudio e casa com a pontuação |
| **Rhubarb Lip Sync** | MIT | 🔌 (download do GitHub bloqueado aqui; instalado no Docker) | 9 formas de boca a partir da fala |
| Boca por envelope (nosso) | — | ✅ | Sem Rhubarb: volume e brilho do som viram formas de boca |

## 3. Sons e trilha

| Peça | Licença | Precisa | Teste | Uso |
|---|---|---|---|---|
| Biblioteca local (Kenney, Sonniss) | CC0 / licença Sonniss | arquivos na pasta | ✅ (vazia no teste) | Primeira escolha para cada efeito |
| **Freesound API** | sons CC0 (filtro) | `FREESOUND_API_KEY` | 🔌 | Baixa e guarda no cache com crédito |
| **Stable Audio Open** | Stability AI Community | GPU | 🔌 | Gera o efeito pelo texto quando não há arquivo |
| Síntese própria (numpy) | — | nada | ✅ | 15 efeitos: pop, whoosh, whoosh grave, caneta, papel, impacto, baque, tick, ding, notificação, moeda, caixa registradora, transição, bip, drone |
| **ACE-Step** | Apache 2.0 | GPU + `ACE_STEP_CMD` | 🔌 | Gera a trilha pelo clima |
| **Openverse API** | faixas CC0 / CC-BY | nada (rede liberada para `api.openverse.org`) | 🔌 | Busca trilha longa; o crédito entra na descrição |
| Trilha sua | da faixa | campo `trilha_arquivo` no Config do n8n | ✅ | URL ou arquivo |

## 4. Imagem (só quando o artifact pede, com marcadores)

| Peça | Licença | Precisa | Teste | Uso |
|---|---|---|---|---|
| **Natural Earth 1:50m** admin-0 map units | domínio público | nada (baixado no build) | ✅ | `data-mapa`: mapa no estilo da marca, nomes em português, rota animada |
| **vtracer** | MIT | nada | ✅ | Converte a imagem em SVG chapado |
| **FLUX.1 schnell** | Apache 2.0 | GPU | 🔌 | `data-arte="prompt"`: gera a ilustração |
| **Meta AnimatedDrawings** | MIT | instalação própria + `ANIMATED_DRAWINGS_CMD` | 🔌 | `data-desenho`: dá movimento a um desenho |

## 5. Movimento e acabamento

| Peça | Licença | Teste | Uso |
|---|---|---|---|
| **Playwright + Chromium** | Apache 2.0 / BSD | ✅ | Toca o artifact e captura cada quadro |
| **lottie-web** | MIT | ✅ | Animações Lottie por cima da cena, controladas quadro a quadro |
| **rlottie** (`rlottie-python`) | MIT / LGPL | ✅ | Valida e mede cada .json Lottie antes do render |
| Motion blur por supersampling (nosso) | — | ✅ | 3 subquadros só nos quadros com movimento rápido |
| Punch-in, tremor, relógio das animações (nosso) | — | ✅ | Câmera e sincronia com a fala |
| Textura de papel (nossa, numpy) | — | ✅ | Mesclada em soft light, 7 % |
| Masterização da voz (FFmpeg) | — | ✅ | Passa-alta, de-esser, equalização de presença e compressão na faixa de narração |
| Render em 1440p / 4K | — | ✅ | `RESOLUCAO=1440` ou `2160`: o YouTube usa VP9/AV1 acima de 1080p e a imagem fica mais limpa |
| **FFmpeg** (xfade, tmix, sidechaincompress, loudnorm, libass) | LGPL/GPL | ✅ | Transições, mix, legendas, codificação |
| **gl-transitions** | MIT | 🔌 (precisa FFmpeg com o filtro `gltransition`) | Transições GLSL |
| Fontes Bebas Neue, Barlow, Barlow Condensed, Permanent Marker | OFL | ✅ | Título e legenda dos verticais |

## 6. Pauta e publicação

| API | Precisa | Teste | Uso |
|---|---|---|---|
| **Anthropic Claude** (`claude-opus-5-5`) | `ANTHROPIC_API_KEY` | 🔌 | Pautas, roteiro em texto, escolha dos trechos dos shorts |
| **YouTube Data API v3** | `YOUTUBE_API_KEY` | 🔌 | Vídeos em alta (BR e EUA) |
| Google Trends RSS, Wikipedia Pageviews, Reddit | nada | 🔌 (bloqueados aqui) | Tendências |
| **YouTube (upload)** no n8n | OAuth no n8n | 🔌 | Sobe o longo como privado, com descrição, capítulos e créditos |
| **Google Drive** no n8n | OAuth no n8n | 🔌 | Entrada dos artifacts e entrega dos vídeos |
| **Telegram Bot API** | token | 🔌 | Aprovação de pauta e aviso de vídeo pronto |
| **Railway** | conta | 🔌 | Hospeda o worker (`railway.json` + Dockerfile) |
| Postgres | — | ✅ (esquema) | Tendências, pautas, vídeos |

## 7. Domínios de rede

- **Build:** `huggingface.co` (+ CDN), `raw.githubusercontent.com`, `github.com` (Rhubarb, gl-transitions), `fonts.googleapis.com` / `fonts.gstatic.com`, `deb.nodesource.com`, PyPI, npm.
- **Execução:** `api.elevenlabs.io`, `freesound.org`, `api.openverse.org` (+ hosts das faixas), `api.anthropic.com`, `www.googleapis.com`, `trends.google.com`, `wikimedia.org`, `www.reddit.com`, `api.telegram.org` — cada um só se você usar a peça correspondente.
