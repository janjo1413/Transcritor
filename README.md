# Transcritor Local

Aplicacao local para transcrever audio e video em texto usando `FastAPI`, `FFmpeg` e `faster-whisper`.

## O que o projeto faz

- Aceita arquivos de audio e video enviados pela interface web local
- Aceita tambem links diretos do YouTube para baixar o audio antes da transcricao
- Permite selecionar ou arrastar e soltar o arquivo na tela
- Converte a midia para `wav` mono em `16kHz`
- Transcreve localmente usando modelos Whisper
- Pode executar um prompt livre opcional via `Ollama` local a partir da transcricao e de anexos
- Divide automaticamente arquivos longos em blocos para processamento paralelo
- Mostra progresso visual de envio e processamento
- Detecta automaticamente CPU ou GPU disponivel para a execucao
- Salva os resultados como `.txt`, `.srt` e `.json` na sua maquina

## Requisitos

- Python 3.11 ou superior
- `ffmpeg` instalado e disponivel no `PATH`
- `yt-dlp` instalado no ambiente Python para links do YouTube
- `Ollama` instalado e em execucao local para processar prompts depois da transcricao

## Instalar dependencias

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Executar o app

```bash
uvicorn app.main:app --reload
```

Abra `http://127.0.0.1:8000`.

Se for usar o prompt livre local, inicie tambem o Ollama e tenha ao menos um modelo baixado, por exemplo:

```bash
ollama serve
ollama pull llama3.2:3b
ollama pull llama3.2:1b
```

## Estrutura

```text
app/
  main.py
  routes.py
  services/
  static/
  templates/
input/
temp/
output/
requirements.txt
```

## Observacoes

- O app pode escolher automaticamente entre um modelo rapido e um modelo mais capaz via `OLLAMA_FAST_MODEL` e `OLLAMA_MODEL`
- O `faster-whisper` escolhe automaticamente CPU ou GPU quando disponivel
- Arquivos com mais de 10 minutos sao divididos em blocos de 2 minutos para acelerar a transcricao
- O tempo de processamento depende do tamanho do arquivo e da sua maquina
- O app aceita os formatos mais comuns de audio e video, desde que o `ffmpeg` consiga abrir o arquivo
