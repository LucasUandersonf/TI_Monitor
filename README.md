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
 │ 3. narração por cena ........ ElevenLabs, Google TTS ou      │
 │                               Kokoro (grátis, no worker)      │
 │ 4. tempo de cada palavra .... vem da voz (ElevenLabs/Google),│
 │                               Whisper (Kokoro) ou energia     │
 │ 5. boca do Pensador ......... envelope da voz                │
 │ 6. plano de edição .......... duração real, relógio das      │
 │                               animações, punch-in, Lottie    │
 │ 7. render quadro a quadro ... Playwright + motion blur       │
 │ 8. transições ............... FFmpeg xfade                   │
 │ 9. sons ..................... pasta sons/sfx (sua) → síntese │
 │10. trilha ................... sua → pasta sons/trilha → nada │
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
| Punch-in | Zoom rápido de 4,5 % no instante em que cada palavra `hot` é dita | tempo das palavras + renderer |
| Tremor | Sacudida curta no impacto do cartão de capítulo | renderer |
| Boca | A boca do Pensador muda de forma com a fala (9 formas) | envelope da voz |
| Motion blur | 3 subquadros com obturador de 180°, só nos quadros em que algo entra rápido (pop, slide, grow) ou a câmera dá punch-in | Playwright + FFmpeg tmix |
| Lottie | Acento animado em cima do elemento que acabou de entrar, na palavra forte (`biblioteca/lottie/destaque.json`), e qualquer Lottie que a cena pedir | lottie-web + rlottie |
| Mapa | O artifact põe um marcador `data-mapa="PRT,BRA" data-rota="PRT>BRA"`; entra o mapa do Natural Earth com nomes em português e a rota desenhando | Natural Earth |
| Arte | Marcador `data-arte="prompt"` (FLUX, GPU) ou `data-arte-arquivo="foto.png"`; a imagem vira SVG chapado | FLUX.1 schnell + vtracer |
| Desenho animado | Marcador `data-desenho="mascote"` anima um desenho seu | AnimatedDrawings |
| Efeitos sonoros automáticos | Lê as animações do artifact: `pop` → pop, `slideL/R` → whoosh, `grow` → whoosh grave, `draw` curto → caneta, `toss` → papel, capítulo → impacto | pasta `sons/sfx/` (Kenney, Sonniss...) ou síntese própria |
| Transições | Dissolve de 0,3 s entre cenas; transição forte (circleopen / CrossZoom) antes de cada capítulo; som de transição no corte | FFmpeg xfade |
| Trilha | Em loop, −22 dB, abaixa sozinha quando há voz (sidechain), fade in/out | pasta `sons/trilha/` |
| Acabamento | Textura de papel, grão de filme leve, vinheta, loudness −14 LUFS | numpy + FFmpeg |
| Descrição do YouTube | Capítulos clicáveis (0:00 Abertura, 1:12 ...) a partir dos cartões de capítulo e créditos de todas as músicas e efeitos baixados | FFmpeg + worker |
| Legendas | `.srt` para o longo; no vertical, blocos de 3 palavras com a palavra falada em lima e as de destaque em magenta | tempo das palavras + libass |
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
├── sons/                       SUA pasta de efeitos e trilhas (veja sons/README.md)
├── prompts/                    DNA do canal, escolha de pauta, roteiro, escolha de shorts
├── db/schema.sql               tendências, pautas, vídeos
├── n8n/workflows/              00_teste_rapido, 01_pauta_diaria, 02_edicao_artifact, 03_roteiro_do_dia, 05_episodio, 06_preparar_elevenlabs
├── n8n/plugin/                 nó "Fábrica Cult" para o n8n
├── docs/COLAR_NA_CONVERSA_DE_ARTIFACTS.md   contrato para a sua conversa de artifacts
└── exemplos/                   seu artifact de teste + vídeos gerados no teste
```

---

## Instalação

**1. Servidor.** Qualquer máquina com Docker, sem GPU. A imagem tem só o necessário: FFmpeg, Chromium (render), Kokoro (voz grátis) e faster-whisper.

**2. Chaves.** Copie `.env.exemplo` para `.env` e preencha:
- `ANTHROPIC_API_KEY`: pautas, roteiro e escolha dos shorts
- `YOUTUBE_API_KEY`: YouTube Data API v3 (grátis no Google Cloud)
- **Voz** (escolha uma; `TTS_MOTOR=auto` usa a primeira configurada):
  - `GOOGLE_TTS_API_KEY`: Google Cloud TTS, **melhor custo-benefício**. Ative a "Cloud Text-to-Speech API" num projeto do Google Cloud e crie uma chave de API. A cota grátis mensal das vozes Neural2/WaveNet cobre dezenas de vídeos. Voz padrão `pt-BR-Neural2-B` (masculina; `-A` e `-C` são femininas), em `GOOGLE_TTS_VOZ`.
  - `ELEVENLABS_API_KEY` + `ELEVENLABS_VOICE_ID`: voz premium (paga; o plano grátis não permite uso comercial).
  - nenhuma: Kokoro, grátis, roda no próprio worker.
  - As três devolvem o tempo de cada palavra, então a cena dura exatamente a fala e os destaques entram na palavra.
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

**4. Sons.** Ponha os seus efeitos em `sons/sfx/<categoria>/` e as trilhas em `sons/trilha/<clima>/`, faça commit e pronto (guia e categorias em `sons/README.md`). Nenhuma API de busca: categoria vazia vira um efeito sintetizado; sem trilha, o vídeo sai com voz e efeitos.

Outros arquivos opcionais ficam no volume do worker (`dados/biblioteca/`):
```
biblioteca/
├── lottie/destaque.json   (acento automático nas palavras fortes; outros .json a cena pode pedir pelo nome)
├── arte/                  (imagens suas para data-arte-arquivo)
└── desenhos/              (desenhos para data-desenho, fundo branco)
```

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
- Voz: `GOOGLE_TTS_API_KEY` (ou as da ElevenLabs). Sem chave, usa a Kokoro.
- Na rede interna do Railway, o n8n chama `http://fabrica-worker.railway.internal:8000` (já é o padrão no fluxo 03).

**6. n8n** (o seu, ou o do compose em http://localhost:5678)
- Credenciais: Google Drive OAuth2.
- **Roteiro numa planilha (colunas roteiro e data):** importe `n8n/workflows/03_roteiro_do_dia.json` e siga `docs/FLUXO_ROTEIRO_DO_DIA.md`.
- **Primeiro teste:** importe `n8n/workflows/00_teste_rapido.json` e siga `docs/COMO_TESTAR_NO_N8N.md` (você clica em executar e os vídeos aparecem no Drive).
- Depois: Import → `n8n/workflows/01_pauta_diaria.json` e `02_edicao_artifact.json`.
- Abra o nó **Config** de cada fluxo e preencha: URL do worker, chat do Telegram (o token fica na credencial "Telegram API" do nó de aviso), IDs das pastas do Drive, clima ou arquivo da trilha e `publicar_youtube` (`sim` sobe o longo como privado, com capítulos e créditos na descrição).
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
`GET /saude` mostra qual voz está ativa e quantos efeitos e trilhas o worker achou nas pastas.
`POST /voz/teste` gera a mesma frase com cada voz para você comparar.

---

## Tempo e custo

- **Render:** o gargalo, porque cada quadro é uma captura do Chromium. No teste deste projeto (máquina de nuvem modesta, 3 renders em paralelo, 30 fps) foram cerca de 7 minutos de render por minuto de vídeo. O tempo cai quase em linha reta com mais núcleos e `RENDER_PARALELO` maior; numa máquina dedicada de 16 núcleos, um longo de 15 min deve ficar em torno de 1 hora. Se precisar de mais velocidade, `FPS=24` corta 20 %.
- **Claude:** só a pauta (uma vez por dia), o roteiro e a escolha dos shorts. A edição em si não usa IA paga.
- **Voz:** Google TTS dentro da cota grátis, ou Kokoro (grátis). ElevenLabs só se você quiser a voz premium.
- **Tudo o mais é open source e roda no worker.**

## Próximos passos

- Publicação automática: o n8n tem nó do YouTube; TikTok exige app aprovado na API de Content Posting.
- Lottie: se quiser acentos prontos (brilho, confete, sublinhado), dá para injetar lottie-web no render com o mesmo controle quadro a quadro.
