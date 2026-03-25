# Transcritor Local

Aplicativo local para transformar audio e video em texto no seu proprio computador.

## Para que serve

Voce pode usar o app para:

- transcrever arquivos de audio e video
- baixar o audio de um video do YouTube e transcrever
- salvar o resultado em `.txt`, `.srt` e `.json`

## Como usar a versao pronta

1. Baixe a pasta do programa.
2. Extraia o `.zip`, se ele vier compactado.
3. Abra a pasta `Transcritor`.
4. Clique em `Transcritor.exe`.
5. Aguarde o navegador abrir automaticamente.
6. Use o app em `http://127.0.0.1:8000`.

## O que o usuario precisa ter no PC

- Windows 64 bits
- um navegador instalado
- internet apenas se for usar link do YouTube

Voce nao precisa instalar:

- Python
- bibliotecas Python
- FFmpeg
- yt-dlp

## Como transcrever

### Arquivo do computador

1. Abra o app.
2. Escolha `Arquivo local`.
3. Selecione o arquivo ou arraste para a tela.
4. Clique em `Transcrever`.
5. Espere o processo terminar.

### Link do YouTube

1. Abra o app.
2. Escolha `Link do YouTube`.
3. Cole a URL do video.
4. Clique em `Transcrever`.
5. Espere o download e a transcricao terminarem.

## Onde ficam os resultados

Os arquivos gerados ficam na pasta de saida mostrada no app.

Os formatos gerados sao:

- `.txt`: texto simples
- `.srt`: legenda com tempo
- `.json`: dados completos da transcricao

## Dicas importantes

- Envie a pasta inteira do app para outra pessoa, nao apenas o `Transcritor.exe`.
- Se o navegador nao abrir sozinho, acesse manualmente `http://127.0.0.1:8000`.
- O tempo de transcricao depende do tamanho do arquivo e da potencia do computador.
- Para links do YouTube, o app precisa de internet.

## Para desenvolvimento

Se voce for rodar o projeto em modo desenvolvimento:

```bash
python run.py
```

No Windows, voce tambem pode executar `start.bat`.

## Gerar a versao distribuivel

Para gerar a pasta pronta para usuario comum:

1. Coloque `ffmpeg.exe`, `ffprobe.exe` e `yt-dlp.exe` na raiz do projeto.
2. Instale `PyInstaller` no ambiente.
3. Execute:

```powershell
.\build.ps1
```

A saida sera criada em `dist/Transcritor/`.
