const form = document.getElementById("transcription-form");
const submitButton = document.getElementById("submit-button");
const statusBox = document.getElementById("status-box");
const output = document.getElementById("transcription-output");
const outputFiles = document.getElementById("output-files");
const mediaFileInput = document.getElementById("media-file");
const dropZone = document.getElementById("drop-zone");
const selectedFile = document.getElementById("selected-file");
const progressBar = document.getElementById("progress-bar");
const progressLabel = document.getElementById("progress-label");

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

function updateSelectedFileLabel() {
  const file = mediaFileInput.files?.[0];
  selectedFile.textContent = file
    ? `${file.name} (${Math.max(1, Math.round(file.size / 1024 / 1024))} MB)`
    : "Nenhum arquivo selecionado.";
}

function uploadWithProgress(formData) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", "/transcribe");
    request.responseType = "json";

    request.upload.addEventListener("progress", (event) => {
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
    setStatus(payload.message || "Processando transcricao...");

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
  const files = event.dataTransfer?.files;
  if (!files?.length) {
    return;
  }
  mediaFileInput.files = files;
  updateSelectedFileLabel();
});

mediaFileInput.addEventListener("change", updateSelectedFileLabel);

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  submitButton.disabled = true;
  output.value = "";
  outputFiles.innerHTML = "";
  setStatus("Preparando transcricao local.");

  try {
    const formData = new FormData(form);
    const submission = await uploadWithProgress(formData);
    setStatus("Upload concluido. Aguardando inicio do processamento.");
    const payload = await pollJob(submission.job_id);

    output.value = payload.text || "";
    renderFiles(payload.files || {});
    setProgress(100);
    setStatus(
      `Transcricao concluida.\nArquivo: ${payload.filename}\nModelo: ${payload.model}\nProcessamento: ${payload.device.toUpperCase()}\nSaida: ${payload.output_dir}`
    );
  } catch (error) {
    setStatus(error.message || "Ocorreu um erro durante a transcricao.");
  } finally {
    submitButton.disabled = false;
  }
});
