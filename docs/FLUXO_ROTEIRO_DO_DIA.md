# Fluxo 03 · Roteiro do dia

Você escreve o roteiro numa planilha e gera o artifact na conversa do Claude. Todo dia às **6h13** o n8n olha a planilha. Se tiver uma linha com a **data de hoje**, ele pega o artifact correspondente no Drive e manda editar: narração, sincronia, sons, trilha, transições, legendas, vídeo longo 16:9, shorts 9:16 e descrição do YouTube. Tudo cai pronto em **03 · Vídeos prontos**, com aviso no Telegram (opcional).

## 1. A planilha

Pode ser **Excel (.xlsx) salvo no Drive** ou **Planilha Google**. A primeira aba é a que vale e a primeira linha é o cabeçalho.

| roteiro | data | artifact *(opcional)* |
|---|---|---|
| # Viés de confirmação<br>Erro de pensamento número um... | 20/11/2026 | |
| Seu cérebro não quer a verdade. Ele quer conforto... | 21/11/2026 | gta6 parte final |

- **roteiro**: o texto do vídeo. Se a primeira linha começar com `# `, ela vira o título do vídeo. Pode usar o formato com `[CENA]` (um bloco por cena, na ordem).
- **data**: o dia em que o vídeo deve ser feito. Aceita data do Excel, `20/11/2026`, `2026-11-20` ou `20-11-2026`.
- **artifact** (opcional): o nome do arquivo `.html` na pasta 02 · Artifacts. Também aceita o ID ou o link do arquivo no Drive.

Linhas com outra data são ignoradas. Se não tiver nenhuma linha para hoje, o fluxo termina sem fazer nada.

## 2. Como o roteiro se liga ao artifact

O artifact baixado da conversa do Claude vai para **02 · Artifacts**. O fluxo acha o arquivo de cada linha nesta ordem:

1. pela coluna **artifact**, se você preencheu;
2. pela **data no nome do arquivo**: `2026-11-20 viés de confirmação.html` (também vale `20-11-2026` ou `20.11.2026`);
3. se só existe um `.html` na pasta e uma linha para hoje, usa esse.

Se não achar, o fluxo para com uma mensagem dizendo o que procurou e o que tem na pasta.

## 3. De onde vem a narração (`narracao_vem_de` no Config)

| Valor | O que acontece |
|---|---|
| `auto` (padrão) | Se as cenas do artifact já têm narração, ela vale, porque está sincronizada com o desenho. O roteiro da planilha preenche só as cenas que vieram sem texto e dá o título. Se o artifact veio quase sem narração, o roteiro inteiro é dividido entre as cenas. |
| `roteiro` | A narração de todas as cenas sai da planilha. Com `[CENA]`, um bloco por cena; sem marcadores, as frases são distribuídas pela duração de cada cena, sem cortar frase no meio. |
| `artifact` | Usa só o texto do artifact; a planilha dá apenas o título. |

## 4. Configurar

1. Importe `n8n/workflows/03_roteiro_do_dia.json`.
2. No nó **Config**, preencha:

   | Campo | O que pôr |
   |---|---|
   | `worker_url` | URL do worker, sem barra no fim |
   | `planilha_id` | ID da planilha no Drive (o trecho do link entre `/d/` e `/edit`, ou o final do link do arquivo) |
   | `drive_pasta_artifacts` | ID da pasta 02 · Artifacts |
   | `drive_pasta_prontos` | ID da pasta 03 · Vídeos prontos |
   | `narracao_vem_de` | `auto`, `roteiro` ou `artifact` |
   | `gerar_shorts` | `sim` ou `nao` (`sim` precisa da chave da Anthropic no worker, a não ser que o artifact traga `window.META.shorts`) |
   | `clima_trilha` | `reflexivo`, `misterio` ou `tensao` |
   | `trilha_arquivo` | opcional: link de uma música sua, ou o nome de um arquivo da pasta `sons/trilha/` |
   | `voz` | vazio = a voz configurada no worker. Ou `google`, `elevenlabs`, `kokoro_onnx` só para este fluxo |
   | `limite_minutos` | depois de quanto tempo esperando o worker o fluxo desiste com erro (padrão 120) |
   | `testar_com_a_data` | vazio = hoje. Para testar agora uma linha de outro dia, ponha a data dela: `2026-11-20` |
   | `telegram_chat_id` | opcional: aviso com os links quando ficar pronto |

3. Escolha a credencial do Google Drive nos nós **Baixar planilha**, **Arquivos da pasta**, **Baixar artifact** e **Salvar no Drive**. Se for usar o aviso, escolha a credencial **Telegram API** (o token do @BotFather) no nó **Avisar no Telegram**.
4. Clique em **Execute workflow** (botão do nó **▶ Testar agora**) para ver na hora. Quando estiver bom, ative o fluxo: ele roda sozinho todo dia às 6h13.

Vários vídeos no mesmo dia entram numa fila no worker e saem um depois do outro. O fluxo confere o andamento a cada minuto e só entrega quando todos terminam. Se um falhar, os outros são entregues e o erro aparece no resumo.

## 5. O que chega no Drive

Para cada linha do dia, com o nome começando pela data:
- `… · longo_16x9.mp4` e `… · longo_16x9.srt`
- `… · descricao_youtube.txt` (capítulos clicáveis e créditos)
- `… · short_1_9x16.mp4`, `short_2_…` (se `gerar_shorts = sim`)
