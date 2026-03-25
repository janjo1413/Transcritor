const form = document.getElementById("transcription-form");
const submitButton = document.getElementById("submit-button");
const statusBox = document.getElementById("status-box");
const output = document.getElementById("transcription-output");
const summaryOutput = document.getElementById("summary-output");
const outputFiles = document.getElementById("output-files");
const mediaFileInput = document.getElementById("media-file");
const youtubeUrlInput = document.getElementById("youtube-url");
const sourceInputs = document.querySelectorAll('input[name="source_type"]');
const sourcePanels = document.querySelectorAll("[data-source-panel]");
const dropZone = document.getElementById("drop-zone");
const selectedFile = document.getElementById("selected-file");
const progressBar = document.getElementById("progress-bar");
const progressLabel = document.getElementById("progress-label");
const summaryFilesInput = document.getElementById("summary-files");

function formatSeconds(value) {
  const totalSeconds = Math.max(0, Math.round(value || 0));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

function describeJobActivity(payload) {
  const nowSeconds = Date.now() / 1000;
  const createdAt = payload.created_at || null;
  const updatedAt = payload.updated_at || null;
  const messageAt = payload.last_message_at || null;
  const totalElapsed = createdAt ? formatSeconds(nowSeconds - createdAt) : "n/d";
  const quietFor = updatedAt ? formatSeconds(nowSeconds - updatedAt) : "n/d";
  const messageAge = messageAt ? formatSeconds(nowSeconds - messageAt) : quietFor;
  const updates = payload.update_count ?? 0;

  return (
    `${payload.message || "Processando transcricao..."}\n` +
    `Tempo total nesta etapa: ${totalElapsed}\n` +
    `Ultima atualizacao: ha ${quietFor}\n` +
    `Ultima mudanca de mensagem: ha ${messageAge}\n` +
    `Eventos emitidos: ${updates}`
  );
}

function setStatus(message, muted = false) {
  statusBox.textContent = message;
  statusBox.classList.toggle("muted", muted);
}

function setProgress(value) {
  const boundedValue = Math.max(0, Math.min(100, Math.round(value)));
  progressBar.style.width = `${boundedValue}%`;
  progressLabel.textContent = `${boundedValue}%`;
}

function renderFiles(files) {
  outputFiles.innerHTML = "";
  Object.entries(files).forEach(([label, path]) => {
    const tag = document.createElement("code");
    tag.textContent = `${label}: ${path}`;
    outputFiles.appendChild(tag);
  });
}

function formatSummaryStatus(payload, transcriptionSeconds) {
  const warnings = payload.summary_warning;
  const warningsText = Array.isArray(warnings) && warnings.length
    ? `\nAvisos: ${warnings.join(" | ")}`
    : "";
  const contextStrategy = payload.summary?.context_strategy || "desconhecida";
  const modelStrategy = payload.summary?.model_strategy || "desconhecida";
  const ollamaMetrics = payload.timings?.ollama_metrics || {};
  const promptEvalCount = ollamaMetrics.prompt_eval_count ?? "?";

  return (
    `Resposta do Ollama concluida.\n` +
    `Provider: ${payload.summary?.provider || "ollama"}\n` +
    `Modelo: ${payload.summary?.model || "padrao"}\n` +
    `Selecao de modelo: ${modelStrategy}\n` +
    `Contexto: ${contextStrategy}\n` +
    `Tokens de prompt: ${promptEvalCount}\n` +
    `Transcricao: ${transcriptionSeconds || 0}s\n` +
    `Prompt: ${payload.timings?.summary_seconds || 0}s\n` +
    `Saida: ${payload.output_dir}` +
    warningsText
  );
}

function updateSelectedFileLabel() {
  const file = mediaFileInput.files?.[0];
  selectedFile.textContent = file
    ? `${file.name} (${Math.max(1, Math.round(file.size / 1024 / 1024))} MB)`
    : "Nenhum arquivo selecionado.";
}

function getSelectedSourceType() {
  return document.querySelector('input[name="source_type"]:checked')?.value || "file";
}

function syncSourceMode() {
  const sourceType = getSelectedSourceType();

  sourcePanels.forEach((panel) => {
    panel.classList.toggle("hidden", panel.dataset.sourcePanel !== sourceType);
  });

  const isFileMode = sourceType === "file";
  mediaFileInput.required = isFileMode;
  youtubeUrlInput.required = !isFileMode;

  if (isFileMode) {
    youtubeUrlInput.value = "";
  } else {
    mediaFileInput.value = "";
    updateSelectedFileLabel();
  }
}

function uploadWithProgress(formData) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", "/transcribe");
    request.responseType = "json";
    const sourceType = getSelectedSourceType();

    request.upload.addEventListener("progress", (event) => {
      if (sourceType !== "file") {
        return;
      }
      if (!event.lengthComputable) {
        return;
      }
      const uploadProgress = Math.min((event.loaded / event.total) * 15, 15);
      setProgress(uploadProgress);
      setStatus("Enviando arquivo para processamento local...");
    });

    request.addEventListener("load", () => {
      const payload = request.response || {};
      if (request.status >= 200 && request.status < 300) {
        resolve(payload);
        return;
      }
      reject(new Error(payload.detail || "Falha ao transcrever o arquivo."));
    });

    request.addEventListener("error", () => {
      reject(new Error("Falha de conexao com o servidor local."));
    });

    request.addEventListener("loadstart", () => {
      setProgress(0);
      setStatus(
        sourceType === "file"
          ? "Enviando arquivo para processamento local..."
          : "Enviando URL do YouTube para o backend local..."
      );
    });

    request.send(formData);
  });
}

function startSummaryJob({ sourceName, outputDir, transcriptText, summaryPrompt, summaryModel, summaryFiles }) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", "/summarize");
    request.responseType = "json";
    const formData = new FormData();

    formData.append("source_name", sourceName);
    formData.append("output_dir", outputDir);
    formData.append("transcript_text", transcriptText);
    formData.append("summary_prompt", summaryPrompt);
    formData.append("summary_model", summaryModel || "");

    Array.from(summaryFiles || []).forEach((file) => {
      formData.append("summary_files", file);
    });

    request.addEventListener("load", () => {
      const payload = request.response || {};
      if (request.status >= 200 && request.status < 300) {
        resolve(payload);
        return;
      }
      reject(new Error(payload.detail || "Falha ao iniciar o resumo."));
    });

    request.addEventListener("error", () => {
      reject(new Error("Falha de conexao com o servidor local durante o resumo."));
    });

    request.send(formData);
  });
}

async function pollJob(jobId) {
  while (true) {
    const response = await fetch(`/jobs/${jobId}`);
    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.detail || "Falha ao consultar o andamento da transcricao.");
    }

    setProgress(payload.progress || 0);
    setStatus(describeJobActivity(payload));

    if (payload.status === "completed") {
      return payload.result;
    }

    if (payload.status === "failed") {
      throw new Error(payload.error || "Falha durante a transcricao.");
    }

    await new Promise((resolve) => window.setTimeout(resolve, 900));
  }
}

["dragenter", "dragover"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("is-dragover");
  });
});

["dragleave", "dragend", "drop"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("is-dragover");
  });
});

dropZone.addEventListener("drop", (event) => {
  if (getSelectedSourceType() !== "file") {
    return;
  }
  const files = event.dataTransfer?.files;
  if (!files?.length) {
    return;
  }
  mediaFileInput.files = files;
  updateSelectedFileLabel();
});

mediaFileInput.addEventListener("change", updateSelectedFileLabel);
sourceInputs.forEach((input) => input.addEventListener("change", syncSourceMode));
syncSourceMode();

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  submitButton.disabled = true;
  output.value = "";
  summaryOutput.value = "";
  outputFiles.innerHTML = "";
  setStatus(
    getSelectedSourceType() === "file"
      ? "Preparando transcricao de arquivo local."
      : "Preparando transcricao a partir de link do YouTube."
  );

  try {
    const formData = new FormData(form);
    if (getSelectedSourceType() !== "file") {
      formData.delete("media_file");
    }

    const submission = await uploadWithProgress(formData);
    setStatus(
      getSelectedSourceType() === "file"
        ? "Upload concluido. Aguardando inicio do processamento."
        : "URL recebida. Aguardando inicio do download do YouTube."
    );
    const payload = await pollJob(submission.job_id);

    output.value = payload.text || "";
    renderFiles(payload.files || {});
    setProgress(100);
    setStatus(
      `Transcricao concluida.\nArquivo: ${payload.filename}\nModelo: ${payload.model}\nModo detectado: ${payload.transcription_mode || "automatico"}\nProcessamento: ${payload.device.toUpperCase()}\nFonte: ${payload.source_type}\nCache: ${payload.timings?.cache_hit ? "transcricao" : payload.timings?.download_cache_hit ? "audio" : "nao"}\nTempo total: ${payload.timings?.total_seconds || 0}s\nSaida: ${payload.output_dir}`
    );

      const summaryPrompt = document.getElementById("summary-prompt").value.trim();
      const summaryModel = document.getElementById("summary-model").value.trim();
      const summaryFiles = Array.from(summaryFilesInput.files || []);

      if (summaryPrompt) {
        setProgress(0);
      setStatus("Transcricao pronta. Enviando prompt para o Ollama em segunda etapa.");
      const summarySubmission = await startSummaryJob({
        sourceName: payload.filename,
        outputDir: payload.output_dir,
        transcriptText: payload.text || "",
        summaryPrompt,
        summaryModel,
        summaryFiles,
      });
      const summaryPayload = await pollJob(summarySubmission.job_id);
      summaryOutput.value = summaryPayload.summary?.text || "";
      renderFiles({ ...(payload.files || {}), ...(summaryPayload.files || {}) });
      setProgress(100);
      setStatus(formatSummaryStatus(summaryPayload, payload.timings?.total_seconds || 0));
    }
  } catch (error) {
    setStatus(error.message || "Ocorreu um erro durante a transcricao.");
  } finally {
    submitButton.disabled = false;
  }
});
