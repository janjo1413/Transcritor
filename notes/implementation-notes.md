## Estado atual

- App FastAPI com um unico fluxo: upload local -> FFmpeg -> faster-whisper -> export `.txt/.srt/.json`.
- Jobs ficam em memoria, sem persistencia em disco ou banco.
- Frontend atual envia somente `media_file` para `POST /transcribe`.
- Saidas sao organizadas por `job_id` em `output/`.

## Feature 1: links diretos do YouTube

- Adicionar um segundo modo de entrada no formulario: `arquivo` ou `youtube_url`.
- Baixar somente o melhor audio para a pasta de entrada do job usando `yt-dlp`.
- Reaproveitar o pipeline existente a partir do arquivo baixado.
- Validar dominio e formato da URL antes de iniciar o job.

## Feature 2: agente GPT para resumos customizados

- Tornar o resumo opcional, disparado no mesmo job apos a transcricao.
- Aceitar:
  - `summary_prompt`
  - anexos genericos
  - imagens
- Enviar tudo para a Responses API da OpenAI com:
  - `input_text` para instrucoes e transcricao
  - `input_image` com data URL para imagens
  - `input_file` com base64 para arquivos nao-imagem
- Manter isso isolado em um servico proprio para facilitar troca de modelo, timeout e tratamento de erros.

## Riscos tecnicos

- `yt-dlp` precisa estar instalado no ambiente Python.
- Alguns links do YouTube podem falhar por restricao regional, idade ou rate limit.
- Anexos grandes aumentam custo e latencia da chamada ao modelo.
- Jobs em memoria nao sobrevivem a restart do servidor.
