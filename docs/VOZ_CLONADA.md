# Sua voz clonada, grátis

A narração pode sair na **sua voz**, sem ElevenLabs e sem pagar nada por minuto. Dois modelos abertos, liberados para uso comercial, rodam no próprio worker:

| Motor | Licença | Semelhança com a voz de referência* | Velocidade em CPU (4 núcleos)* | Quando usar |
|---|---|---|---|---|
| **Chatterbox Multilingual** (Resemble AI) | MIT | **0,939** | ~6,4 s para cada 1 s de fala | Melhor timbre e mais expressivo. Ideal com GPU. |
| **Qwen3-TTS Base 0.6B** (Alibaba) | Apache 2.0 | 0,925 | ~4 s para cada 1 s de fala | Mais rápido em CPU (Railway). Padrão. |
| Kokoro (voz pronta, não clona) | Apache 2.0 | 0,654 | ~1,5 s | Reserva, quando não há voz cadastrada |

\* Medido neste projeto com uma gravação em português: as vozes clonadas e a Kokoro foram comparadas com a referência por um medidor de semelhança de voz (o encoder de locutor do Chatterbox; 1,0 = mesma voz). A gravação original comparada com o próprio trecho usado deu 0,936, ou seja, as duas clonagens ficaram no nível da própria voz. Vozes de outras pessoas ficam entre 0,55 e 0,65. Nas três, o texto falado foi conferido pelo Whisper e saiu palavra por palavra correto.

Nenhum modelo aberto é garantia de soar idêntico à ElevenLabs em todo trecho; por isso o sistema confere cada frase (veja abaixo) e você ouve as prévias antes de usar.

## 1. Grave a sua voz

- **20 a 30 segundos**, falando do jeito que você quer narrar os vídeos (tom, ritmo, energia).
- Lugar **silencioso**, sem eco (um quarto com cortinas e cama é melhor que uma sala vazia).
- Celular serve. Fique a um palmo do microfone, sem encostar.
- Fale frases completas. Pode ler isto:

> Sabe aquela sensação de que você já sabia como a história ia terminar? Pois é. O nosso cérebro adora ter razão, mesmo quando está errado. Hoje a gente vai entender por quê, e o que dá para fazer com isso. Pega um café, senta aí, que a conversa vai ser boa.

Formatos aceitos: wav, mp3, m4a, ogg, opus, flac.

## 2. Cadastre no worker

**Pelo n8n:** crie a pasta **04 · Minha voz** no Drive, ponha a gravação lá e rode o fluxo `04_cadastrar_minha_voz.json` (preencha o Config). Ele:
1. limpa a gravação: tira ruído grave e chiado e nivela o volume;
2. escolhe o melhor trecho de ~12 s, com mais fala contínua e sem estouro;
3. transcreve o trecho (o Qwen3 usa a transcrição para clonar melhor);
4. gera a mesma frase com cada motor e salva as prévias na pasta da voz (`prévia · clone_qwen3.wav`, `prévia · clone_chatterbox.wav`, `prévia · kokoro_onnx.wav`).

O resultado mostra se a gravação tem ruído ou estouro e o que melhorar.

**Direto na API:** `POST /voz/referencia` com `{"audio_base64": "...", "nome_arquivo": "minha_voz.m4a"}`, depois `POST /voz/teste`.

A partir do cadastro, **todo vídeo sai na sua voz** (a voz clonada passa à frente da Kokoro). Para trocar de motor, mude `VOZ_CLONE_MOTOR` no worker (`qwen3` ou `chatterbox`).

## 3. Como o sistema garante a qualidade

Para cada cena:
1. **Texto preparado para fala:** números por extenso (2023 → "dois mil e vinte e três", 90 MI → "noventa milhões", R$ 2,50 → "dois reais e cinquenta centavos", 12,5% → "doze vírgula cinco por cento", 1º → "primeiro"). A legenda continua com o texto original.
2. **Pronúncia sob controle:** crie `biblioteca/voz/pronuncia.txt` com uma regra por linha, por exemplo `GTA = gê tê á` ou `Nietzsche = nítche`.
3. **Frases curtas:** o texto é gerado em pedaços de até ~220 caracteres, sempre com a mesma semente, para a voz não mudar ao longo do vídeo.
4. **Conferência:** o Whisper ouve cada pedaço. Se a fala não bater com o texto (palavra trocada, repetição, frase inventada) ou durar tempo demais ou de menos, o pedaço é gerado de novo com outra semente (até 3 tentativas) e fica o melhor.
5. **Pausas naturais:** 0,32 s depois de ponto final, 0,16 s depois de vírgula entre pedaços.
6. **Tempo de cada palavra:** sai da própria conferência e alimenta a legenda, o punch-in e os efeitos.
7. **Masterização de estúdio** na faixa inteira de voz: corte de graves de ruído, controle do "s" chiado (de-esser), menos embolado nos médios-graves, mais presença, compressão suave. Depois, o volume final do vídeo fica em −14 LUFS.

## 4. Velocidade e onde rodar

- **Railway (CPU):** funciona sem configurar nada. Um vídeo de 15 minutos tem ~15 minutos de fala, o que dá mais ou menos 1 hora de narração com o Qwen3 em 4 núcleos (menos com mais núcleos, com `VOZ_THREADS`). Para um vídeo por dia, cabe.
- **Com GPU** (sua máquina com placa NVIDIA, `docker compose --profile gpu up -d`): a narração de 15 minutos sai em poucos minutos, e vale usar `VOZ_CLONE_MOTOR=chatterbox` ou o Qwen3 1.7B (`QWEN3_PASTA=qwen3_tts_base_1.7b`).
- **Pesos dos modelos:** ~6 GB, baixados uma vez para o volume `/dados/modelos` na primeira vez que forem usados. Para baixar antes: `POST /voz/baixar-modelos?motores=qwen3_tts_base,whisper_small,chatterbox_mtl`.

## 5. Uso responsável

Clone **só a sua voz** ou a de quem autorizou por escrito. O Chatterbox põe no áudio uma marca d'água inaudível (Perth), que identifica o conteúdo como gerado. No YouTube, marque o vídeo como conteúdo alterado ou sintético quando a plataforma pedir.
