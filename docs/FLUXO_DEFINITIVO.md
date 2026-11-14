# Fluxo definitivo · Fábrica Cult

```
 Conversa do ROTEIRO ──► texto das cenas (PROMPT_ROTEIRO.md)
          │
 Conversa do VÍDEO ────► HTML com as cenas animadas + data-palavra (COLAR_NA_CONVERSA_DE_ARTIFACTS.md)
          │
 (opcional) DIRETOR ───► JSON com as decisões por palavra (PROMPT_DIRETOR.md)
          │
 Drive: HTML em "02 · Artifacts"  +  planilha: roteiro | data | artifact | direcao
          │
 n8n 03 (todo dia 6h13) ─► worker no Railway
          │   1. confere o saldo da ElevenLabs ANTES de gastar (se não der, para sem gastar nada)
          │   2. narra cada cena na ElevenLabs (com o texto das cenas vizinhas = entonação contínua;
          │      cache: rodar de novo não cobra o que já foi narrado)
          │   3. tempo exato de cada palavra (vem da própria ElevenLabs)
          │   4. plano: a fala manda no tempo, elementos entram na palavra, câmera viva, corte em L
          │   5. render quadro a quadro + transições + efeitos + trilha com ducking + -14 LUFS
          │   6. CONFERÊNCIA: lê o vídeo pronto e gera o relatório de qualidade
          │   7. shorts 9:16 (escolha automática, ou a sua em META.shorts)
          ▼
 Drive "03 · Vídeos prontos": vídeo longo, shorts, legenda .srt, descrição do YouTube,
                              relatorio_qualidade.txt, tempos_das_cenas.csv
```

## Configuração (uma vez só)

1. **Chave da ElevenLabs no worker.** No Railway: projeto → serviço `fabrica-worker` → **Variables** → adicione:
   - `ELEVENLABS_API_KEY` = sua chave (ElevenLabs → Developers → API Keys; dê as permissões *Text to Speech*, *Sound Effects* e *User: read*)
   - `ELEVENLABS_VOICE_ID` = ID da voz (ElevenLabs → Vozes → clique na voz → *Copy voice ID*). Pode ser a sua voz clonada lá dentro.
   - Já deixei `TTS_MOTOR=elevenlabs` e `ELEVENLABS_MODELO=eleven_multilingual_v2`.
   - Opcionais: `ELEVENLABS_VELOCIDADE` (0.7 a 1.2, padrão 1.0) e `ELEVENLABS_ESTABILIDADE` (padrão 0.5; mais alto = voz mais constante).
2. **n8n:** importe `06_preparar_elevenlabs.json` e rode. Ele confere a voz e mostra o saldo.
   Depois ponha `gerar_sons = sim` e rode de novo: gera a biblioteca de efeitos modernos (uma vez só, limite de 1.500 créditos).
3. **n8n:** reimporte `03_roteiro_do_dia.json` (lê a coluna `direcao` e sobe o relatório) e copie de novo os IDs no nó Config.
4. **Planilha:** colunas `roteiro`, `data`, `artifact` e (opcional) `direcao`.

## Rotina de cada vídeo

1. Conversa do roteiro → texto das cenas.
2. Conversa do vídeo → HTML (cada elemento com `data-palavra`).
3. (Opcional) conversa do diretor → JSON na coluna `direcao`.
4. Salve o HTML em "02 · Artifacts" e preencha a linha da planilha com a data do dia.
5. Às 6h13 o vídeo é feito sozinho. Abra o **relatório de qualidade** e o **tempos_das_cenas.csv** (o tempo real de cada imagem).

## O que é ajustado sozinho (não precisa fazer nada)

| Problema | Ajuste automático |
|---|---|
| Fala mais rápida que a animação (imagem parada) | a cena dura o tempo da fala; animações aceleradas até 2x |
| Fala mais lenta que a animação | animações desaceleradas até 0,6x |
| Elemento entrando antes ou depois da palavra | entra ~0,1 s antes da palavra (diretor > data-palavra > texto igual na fala) |
| Mais de 1,5 s sem nada novo na tela | micro punch-in numa palavra do trecho + zoom lento contínuo |
| Silêncio entre cenas | 0,2 s entre frases; a próxima imagem entra durante a última palavra |
| Entonação "recomeçando" a cada cena | a ElevenLabs recebe o texto da cena anterior e da seguinte |
| Efeito sonoro repetitivo | variação sorteada + tom e volume levemente diferentes a cada uso |
| Volume diferente entre vídeos | mixagem em duas passadas para -14 LUFS, pico até -1,5 dBFS |
| Vídeo que falhou no meio | rodar de novo não cobra de novo as cenas já narradas (cache) |
| Créditos insuficientes | para ANTES de narrar, sem gastar nada, e diz quanto falta |
| Muitas cenas (memória) | junção em blocos de 8 |

## O que o relatório aponta para você corrigir na conversa

- palavra do `data-palavra` ou do diretor que não está na narração
- cena com mais de 13 s de fala (divida em duas)
- cena com animação longa demais para a fala (menos elementos)
- imagem parada, tela preta, silêncio, volume fora do padrão, vídeo e áudio com durações diferentes
- nota de 0 a 10 por vídeo

## Custos

- **ElevenLabs:** Multilingual v2 = 1 crédito por caractere. Um vídeo de ~5.000 caracteres (65 cenas, ~6 min) ≈ 5.000 créditos.
  Com `ELEVENLABS_MODELO=eleven_flash_v2_5` cai pela metade (qualidade um pouco menor).
- **Railway:** ~US$ 0,10 a 0,30 por vídeo (o worker dorme quando não está trabalhando).
