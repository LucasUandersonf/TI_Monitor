# Pasta de sons (efeitos e trilhas)

O worker usa **só arquivos locais**, sem nenhuma API de busca. Ponha aqui os seus arquivos,
faça commit e o Railway publica junto com o worker.

## O que já vem incluído (tudo CC0: uso comercial, sem crédito obrigatório)

Sem música de fundo: o fluxo 03 manda os vídeos só com voz e efeitos (`trilha: false`).

- **40 efeitos** em 16 categorias (`sfx/`), da biblioteca **SFXMint** (CC0, sons gerados com Stable Audio;
  coletânea em huggingface.co/datasets/flreey/sfxmint-cc0-sound-effects). Já aparados (começam no ataque,
  sem silêncio antes), com fade no fim e o mesmo pico de volume.
- Sem arquivo para `digitar` e `caixa_registradora`: esses dois são sintetizados.

Cada arquivo tem um `.credito.json` ao lado com a origem. Como são CC0, não entram na descrição do vídeo.
Para trocar ou acrescentar, é só pôr arquivos nas pastas (vários na mesma pasta = o worker alterna).

```
sons/
  sfx/<categoria>/qualquer_nome.wav   (ou .mp3 .ogg .flac)
  trilha/<clima>/qualquer_nome.mp3    (climas usados na opção clima_trilha: reflexivo, misterio, tensao...)
  trilha/qualquer_nome.mp3            (reserva: usada quando a pasta do clima está vazia)
```

## Categorias de efeito

| Pasta | Quando toca |
|---|---|
| `pop` | elemento aparecendo (ícone, número, cartão) |
| `whoosh` | deslizes e transições curtas |
| `whoosh_grave` | entrada de capítulo, câmera grande |
| `transicao` | corte entre cenas com transição longa |
| `impacto` | revelação, número forte, troca de parte |
| `baque` | algo caindo |
| `risco_caneta` | traço sendo desenhado |
| `papel` | papel amassado |
| `tick` | relógio, clique de interface |
| `ding` / `notificacao` | sino, celular |
| `moeda` / `caixa_registradora` | dinheiro |
| `bip` | censura |
| `glitch` / `riser` / `drone` / `digitar` | erro digital, tensão subindo, fundo grave, teclado |

Vários arquivos na mesma pasta = o worker alterna entre eles (fixo por cena, então refazer
o vídeo dá o mesmo resultado) e muda levemente o tom a cada uso.

**Pasta vazia não é erro:** o efeito é sintetizado na hora. **Sem trilha:** o vídeo sai só
com voz e efeitos.

## De onde tirar (grátis, uso comercial liberado)

- **Kenney.nl** (Audio): CC0, sem crédito. Ótimo para `pop`, `tick`, `whoosh`.
- **Sonniss GDC Bundle**: grátis, uso comercial, sem crédito. Ótimo para `impacto`, `whoosh_grave`, `riser`.
- **Freesound.org**: baixe à mão só os marcados como **CC0**.
- **Trilhas**: Incompetech (Kevin MacLeod, CC-BY: precisa de crédito), YouTube Audio Library
  (só para vídeos do YouTube), Free Music Archive (filtre CC0/CC-BY).
- Também dá para gerar uma vez com a ElevenLabs (`POST /sfx/biblioteca`, fluxo 06): fica no volume do worker.

## Crédito na descrição do vídeo

Se a licença pede crédito, crie ao lado do arquivo um `<arquivo>.credito.json`, por exemplo
`trilha/reflexivo/minha_musica.mp3.credito.json`:

```json
{"fonte": "Incompetech", "titulo": "Nome da música", "autor": "Kevin MacLeod", "licenca": "CC-BY 4.0", "url": "https://incompetech.com"}
```

O worker junta os créditos dos sons usados na `descricao_youtube.txt`.

Mantenha os arquivos pequenos (efeitos em .wav curtos ou .mp3; trilhas em .mp3 192 kbps):
tudo aqui entra na imagem do worker.
