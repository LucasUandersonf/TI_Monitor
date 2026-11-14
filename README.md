# Fábrica Cult · edição automática de artifacts em vídeo (n8n)

Você gera o artifact animado na sua conversa (o "Motor de Cenas"), salva o `.html` numa pasta do Google Drive, e o n8n devolve no Drive:

- **vídeo longo 16:9** (1920×1080, 30 fps, −14 LUFS) + legenda `.srt` para subir no YouTube
- **até 3 shorts 9:16** (1080×1920) com legenda palavra por palavra, título fixo no topo, texto do post e hashtags

A edição **não redesenha nada**: o visual é 100% o do seu artifact. Ela entra só para melhorar o que já existe: voz, sincronia, câmera, sons, trilha, transições, legenda e acabamento.

---

## Como funciona

```
 ┌───────────── 01 · Pauta diária (n8n, opcional) ─────────────┐
 │ 8h12 → tendências BR + gringa (YouTube, Google Trends,       │
 │        Wikipedia, Reddit) → Postgres                          │
 │      → Claude sugere 3 pautas → Telegram (você toca em 1)     │
 │      → Claude escreve o roteiro → Drive "01 · Roteiros"       │
 └───────────────────────────────┬──────────────────────────────┘
                                 ▼
      você cola o roteiro na conversa de artifacts e salva o .html
                      no Drive "02 · Artifacts"
                                 ▼
 ┌───────────── 02 · Edição do artifact (n8n + worker) ─────────┐
 │ 1. extrai as cenas: narração, duração e cada animação CSS    │
 │ 2. camadas pedidas .......... mapa Natural Earth, arte FLUX→ │
 │                               vtracer, desenho AnimatedDrawings│
 │ 3. narração por cena ........ SUA VOZ clonada (Qwen3-TTS ou  │
 │                               Chatterbox), ElevenLabs, Kokoro │
 │ 4. tempo de cada palavra .... ElevenLabs, WhisperX ou energia│
 │ 5. boca do Pensador ......... Rhubarb ou envelope da voz     │
 │ 6. plano de edição .......... duração real, relógio das      │
 │                               animações, punch-in, Lottie    │
 │ 7. render quadro a quadro ... Playwright + motion blur       │
 │ 8. transições ............... xfade ou gl-transitions        │
 │ 9. sons ..................... Kenney/Sonniss → Freesound →   │
 │                               Stable Audio → síntese própria │
 │10. trilha ................... sua → biblioteca → ACE-Step →  │
 │                               Openverse                      │
 │11. mix + acabamento ......... ducking, loudnorm, papel, grão │
 │12. descrição do YouTube ..... capítulos clicáveis + créditos │
 │13. shorts ................... Claude escolhe os trechos       │
 │                               → composição 9:16 + legenda     │
 └───────────────────────────────┬──────────────────────────────┘
                                 ▼
          Drive "03 · Vídeos prontos" + aviso no Telegram
```

### O que a edição acrescenta ao artifact

| Camada | O que faz | Ferramenta |
|---|---|---|
| Duração | Cada cena passa a durar o tempo da fala real + respiro, nunca menos que a última animação | plano de edição |
| Relógio das animações | Se a fala ficou mais longa que a cena original, as animações do artifact desaceleram na mesma proporção (até 60 %), para cada elemento entrar junto com a frase | renderer |
| Punch-in | Zoom rápido de 4,5 % no instante em que cada palavra `hot` é dita | WhisperX + renderer |
| Tremor | Sacudida curta no impacto do cartão de capítulo | renderer |
| Boca | A boca do Pensador muda de forma com a fala (9 formas) | Rhubarb ou envelope da voz |
| Motion blur | 3 subquadros com obturador de 180°, só nos quadros em que algo entra rápido (pop, slide, grow) ou a câmera dá punch-in | Playwright + FFmpeg tmix |
| Lottie | Acento animado em cima do elemento que acabou de entrar, na palavra forte (`biblioteca/lottie/destaque.json`), e qualquer Lottie que a cena pedir | lottie-web + rlottie |
| Mapa | O artifact põe um marcador `data-mapa="PRT,BRA" data-rota="PRT>BRA"`; entra o mapa do Natural Earth com nomes em português e a rota desenhando | Natural Earth |
| Arte | Marcador `data-arte="prompt"` (FLUX, GPU) ou `data-arte-arquivo="foto.png"`; a imagem vira SVG chapado | FLUX.1 schnell + vtracer |
| Desenho animado | Marcador `data-desenho="mascote"` anima um desenho seu | AnimatedDrawings |
| Efeitos sonoros automáticos | Lê as animações do artifact: `pop` → pop, `slideL/R` → whoosh, `grow` → whoosh grave, `draw` curto → caneta, `toss` → papel, capítulo → impacto | Kenney, Sonniss, Freesound, Stable Audio Open |
| Transições | Dissolve de 0,3 s entre cenas; transição forte (circleopen / CrossZoom) antes de cada capítulo; som de transição no corte | FFmpeg xfade ou gl-transitions |
| Trilha | Em loop, −22 dB, abaixa sozinha quando há voz (sidechain), fade in/out | YouTube Audio Library ou ACE-Step |
| Acabamento | Textura de papel, grão de filme leve, vinheta, loudness −14 LUFS | numpy + FFmpeg |
| Descrição do YouTube | Capítulos clicáveis (0:00 Abertura, 1:12 ...) a partir dos cartões de capítulo e créditos de todas as músicas e efeitos baixados | FFmpeg + worker |
| Legendas | `.srt` para o longo; no vertical, blocos de 3 palavras com a palavra falada em lima e as de destaque em magenta | WhisperX + libass |
| 9:16 | Fundo desfocado da própria cena, cena ampliada no meio, título fixo nas fontes da marca | FFmpeg |

Todas as regras ficam em `worker/app/etapas/plano.py` (`REGRAS`) para você ajustar o ritmo.

**Imagem só quando o artifact pede.** Mapa, arte e desenho animado entram apenas onde o artifact colocar um marcador. Sem marcador, nada da sua arte é tocado.

A lista completa de APIs e bibliotecas, com licença e o que foi testado, está em `docs/APIS_E_BIBLIOTECAS.md`.

---

## Estrutura

```
fabrica-cult/
├── docker-compose.yml          n8n + Postgres + worker (perfil cpu ou gpu)
├── .env.exemplo                chaves e IDs das pastas do Drive
├── renderer/render_artifact.mjs  lê e renderiza o artifact quadro a quadro
├── worker/app/
│   ├── main.py                 API que o n8n chama
│   ├── pipeline.py             a edição completa
│   ├── etapas/                 narracao, alinhamento, plano, sons, render, montagem, shorts
│   ├── fontes/tendencias.py    YouTube, Google Trends, Wikipedia, Reddit
│   └── pauta.py                pautas e roteiro (Claude)
├── prompts/                    DNA do canal, escolha de pauta, roteiro, escolha de shorts
├── db/schema.sql               tendências, pautas, vídeos
├── n8n/workflows/              00_teste_rapido, 01_pauta_diaria, 02_edicao_artifact, 03_roteiro_do_dia, 04_cadastrar_minha_voz
├── n8n/plugin/                 nó "Fábrica Cult" para o n8n
├── docs/COLAR_NA_CONVERSA_DE_ARTIFACTS.md   contrato para a sua conversa de artifacts
└── exemplos/                   seu artifact de teste + vídeos gerados no teste
```

---

## Instalação

**1. Servidor.** Qualquer máquina com Docker. Com GPU NVIDIA (8 GB ou mais) você usa Chatterbox, Stable Audio e ACE-Step; sem GPU, roda com Kokoro e WhisperX em CPU (mais lento).

**2. Chaves.** Copie `.env.exemplo` para `.env` e preencha:
- `ANTHROPIC_API_KEY`: pautas, roteiro e escolha dos shorts
- `YOUTUBE_API_KEY`: YouTube Data API v3 (grátis no Google Cloud)
- `FREESOUND_TOKEN`: efeitos sonoros CC0 (grátis em freesound.org/apiv2/apply)
- `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`: aprovação de pauta e aviso de vídeo pronto
- os IDs das 3 pastas do Drive (o ID é o final do link da pasta)

**3. Pastas no Google Drive**
```
Fábrica Cult/
├── 01 · Roteiros          (o n8n salva os roteiros aqui)
├── 02 · Artifacts         (você salva os .html aqui; o n8n vigia esta pasta)
└── 03 · Vídeos prontos    (o n8n entrega aqui)
```
Um artifact único: `Por que GTA 6 mexe com você.html`. Em partes: `Por que GTA 6 mexe com você · parte 1 de 3.html`, `· parte 2 de 3`, `· parte 3 de 3`. A edição só começa quando todas as partes chegam.

**4. Biblioteca de sons** (pasta `dados/biblioteca/`, pode sincronizar com o Drive)
```
biblioteca/
├── sfx/pop/  sfx/whoosh/  sfx/whoosh_grave/  sfx/risco_caneta/  sfx/papel/
│   sfx/impacto/  sfx/tick/  sfx/notificacao/  sfx/transicao/  sfx/bip/  sfx/drone/
├── trilha/reflexivo/  trilha/misterio/  trilha/tensao/     (mp3 da YouTube Audio Library)
├── voz/referencia.wav     (10 a 20 s da voz do canal, para o Chatterbox clonar)
├── lottie/destaque.json   (acento automático nas palavras fortes; outros .json a cena pode pedir pelo nome)
├── arte/                  (imagens suas para data-arte-arquivo)
└── desenhos/              (desenhos para data-desenho, fundo branco)
```
Ponha os packs da Kenney (kenney.nl/assets, CC0) e da Sonniss GDC (sonniss.com/gameaudiogdc) nas categorias. Categoria vazia: o worker busca no Freesound (só CC0, e anota os créditos em `CREDITOS.txt`); sem Freesound, gera com o Stable Audio Open; sem GPU, sintetiza um som básico para não travar.

**5. Subir (sua máquina com Docker)**
```bash
cp .env.exemplo .env
```
```bash
docker compose --profile gpu up -d --build
```
Sem GPU, troque `gpu` por `cpu`.

**5b. Ou no Railway** (sem n8n junto, para usar o seu n8n que já existe)
- Novo projeto → Deploy from GitHub com este repositório. O `railway.json` já aponta para `worker/Dockerfile` e para o health check `/saude`.
- Variables: as mesmas do `.env.exemplo` que você for usar (no mínimo `ANTHROPIC_API_KEY`; `DATABASE_URL` se adicionar um Postgres no projeto).
- Volume montado em `/dados` (os vídeos e a biblioteca ficam lá).
- Gere um domínio público e coloque a URL no nó **Config** dos dois fluxos.
- O Railway não tem GPU: a voz fica com Kokoro ONNX (ou ElevenLabs, se tiver a chave), e FLUX, Stable Audio, Chatterbox e WhisperX ficam desligados sozinhos.

**6. n8n** (o seu, ou o do compose em http://localhost:5678)
- Credenciais: Google Drive OAuth2.
- **Sua voz:** grave 20 a 30 s, ponha na pasta 04 · Minha voz e rode `n8n/workflows/04_cadastrar_minha_voz.json` (guia: `docs/VOZ_CLONADA.md`).
- **Roteiro numa planilha (colunas roteiro e data):** importe `n8n/workflows/03_roteiro_do_dia.json` e siga `docs/FLUXO_ROTEIRO_DO_DIA.md`.
- **Primeiro teste:** importe `n8n/workflows/00_teste_rapido.json` e siga `docs/COMO_TESTAR_NO_N8N.md` (você clica em executar e os vídeos aparecem no Drive).
- Depois: Import → `n8n/workflows/01_pauta_diaria.json` e `02_edicao_artifact.json`.
- Abra o nó **Config** de cada fluxo e preencha: URL do worker, token e chat do Telegram, IDs das pastas do Drive, clima ou arquivo da trilha e `publicar_youtube` (`sim` sobe o longo como privado, com capítulos e créditos na descrição).
- Escolha as credenciais nos nós do Google Drive e, se for publicar, no nó do YouTube (OAuth2).
- Ative os dois fluxos.
- O nó **Fábrica Cult** (pasta `n8n/plugin`, já compilado em `dist/`) aparece na busca de nós para montar fluxos próprios. Para recompilar: `cd n8n/plugin && npm install && npm run build`.

**7. Sua conversa de artifacts.** Cole `docs/COLAR_NA_CONVERSA_DE_ARTIFACTS.md` nas instruções dela. O seu Motor de Cenas atual já cumpre o contrato sem mudar nada.

---

## Testar sem o n8n

```bash
curl -X POST localhost:8000/edicao/upload -F arquivo=@exemplos/artifact_motor_de_cenas.html
```
```bash
curl localhost:8000/jobs/<job_id>
```
```bash
curl -O localhost:8000/arquivos/<job_id>/longo_16x9.mp4
```
`GET /saude` mostra qual voz e qual alinhamento estão ativos.

---

## Tempo e custo

- **Render:** o gargalo, porque cada quadro é uma captura do Chromium. No teste deste projeto (máquina de nuvem modesta, 3 renders em paralelo, 30 fps) foram cerca de 7 minutos de render por minuto de vídeo. O tempo cai quase em linha reta com mais núcleos e `RENDER_PARALELO` maior; numa máquina dedicada de 16 núcleos, um longo de 15 min deve ficar em torno de 1 hora. Se precisar de mais velocidade, `FPS=24` corta 20 %.
- **Claude:** só a pauta (uma vez por dia), o roteiro e a escolha dos shorts. A edição em si não usa IA paga.
- **Tudo o mais é open source e roda na sua máquina.**

## Próximos passos

- Publicação automática: o n8n tem nó do YouTube; TikTok exige app aprovado na API de Content Posting.
- Lottie: se quiser acentos prontos (brilho, confete, sublinhado), dá para injetar lottie-web no render com o mesmo controle quadro a quadro.
- gl-transitions: o Dockerfile já baixa os shaders; para usá-los, compile o FFmpeg com o filtro `gltransition` e mude `TRANSICAO_MOTOR=gltransition`.
