# Como testar no n8n (10 minutos)

O teste usa o fluxo **00 · Teste rápido**. Você clica em "Executar", ele pega o seu artifact na pasta do Drive, manda para o worker editar, espera terminar e salva os vídeos na pasta de prontos.

## O que precisa estar no ar

1. **O worker** (o programa que edita). O n8n sozinho não edita vídeo: ele só chama o worker. Escolha um jeito:
   - **Railway** (recomendado se o seu n8n está na nuvem): siga a seção "Ou no Railway" do README. No fim você tem uma URL tipo `https://fabrica-worker.up.railway.app`.
   - **Seu computador** com Docker: `docker compose --profile cpu up -d --build`. A URL fica `http://localhost:8000`, mas só funciona se o n8n também estiver rodando no seu computador.
   - Teste se está no ar abrindo `<URL do worker>/saude` no navegador: tem que aparecer `"ok": true` e a voz ativa (`kokoro_onnx`).
2. **Pastas no Google Drive**
   ```
   Fábrica Cult/
   ├── 02 · Artifacts        ← ponha aqui o .html do artifact
   └── 03 · Vídeos prontos   ← os vídeos chegam aqui
   ```
   O ID de cada pasta é o final do link: `drive.google.com/drive/folders/`**`1AbC...xyz`**.

## Passo a passo

1. Salve o artifact como `.html` dentro de **02 · Artifacts**. Para o primeiro teste, use `exemplos/artifact_motor_de_cenas.html` deste projeto.
2. No n8n: **Workflows → Import from File** → `n8n/workflows/00_teste_rapido.json`.
3. Abra o nó **Config** e preencha:
   | Campo | O que pôr |
   |---|---|
   | `worker_url` | a URL do worker, sem barra no fim |
   | `nome_do_artifact` | o nome exato do arquivo, ex.: `artifact_motor_de_cenas.html` |
   | `drive_pasta_artifacts` | ID da pasta 02 · Artifacts |
   | `drive_pasta_prontos` | ID da pasta 03 · Vídeos prontos |
   | `gerar_shorts` | `sim` ou `nao` (`sim` usa o Claude para escolher os trechos, a não ser que o artifact já traga `window.META.shorts`; precisa de `ANTHROPIC_API_KEY` no worker) |
   | `clima_trilha` | `reflexivo`, `misterio` ou `tensao` |
   | `trilha_arquivo` | opcional: link direto de uma música sua |
4. Nos 3 nós do Google Drive (**Procurar artifact**, **Baixar artifact**, **Salvar no Drive**), escolha a credencial do Google Drive (ou crie: Google Drive OAuth2).
5. Clique em **Execute workflow**.

O fluxo checa o worker, acha o arquivo, envia, e fica no laço **Esperar 30 s → Ver andamento** até a edição terminar. Um vídeo de 1 minuto leva alguns minutos; um de 15 minutos leva bem mais (veja "Tempo" no README). No nó **Ver andamento** dá para acompanhar a etapa atual (`narracao`, `render_longo`, `shorts`...).

No fim, o nó **Pronto!** mostra os links dos arquivos no Drive:
- `longo_16x9.mp4` e `longo_16x9.srt`
- `descricao_youtube.txt` (capítulos e créditos)
- `short_1_9x16.mp4`, `short_2_9x16.mp4`...

## Se der erro

| Onde parou | Causa provável |
|---|---|
| **Worker está no ar?** | URL errada, ou o worker está desligado. Abra `<URL>/saude` no navegador. |
| **Achou?** | O nome do arquivo no Config não bate com o do Drive, ou o ID da pasta está errado. A mensagem lista o que ele achou. |
| **Parar com o erro** | A edição falhou no worker. A mensagem diz a etapa; os detalhes ficam em `<URL>/jobs/<job_id>`. |
| **Baixar do worker** demora | Normal para vídeos grandes; o tempo limite é de 10 minutos por arquivo. |

Depois que o teste funcionar, use os fluxos **01** (pauta diária) e **02** (vigia a pasta do Drive e edita sozinho tudo o que chegar).
