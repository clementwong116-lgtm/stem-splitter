(() => {
  const $ = (sel) => document.querySelector(sel);
  const fileInput = $("#file");
  const dropzone = $("#dropzone");
  const fileNameEl = $("#file-name");
  const startBtn = $("#start-btn");
  const statusEl = $("#status");
  const statusMsg = $("#status-msg");
  const statusWarn = $("#status-warn");
  const statusErr = $("#status-err");
  const progressBar = $("#progress-bar");
  const resultsEl = $("#results");
  const installBanner = $("#install-banner");
  const installBtn = $("#install-btn");
  const dismissInstall = $("#dismiss-install");
  const hintEl = document.querySelector("p.hint");
  const pageTitle = $("#page-title");
  const pageSubtitle = $("#page-subtitle");
  const resultsHeading = $("#results-heading");
  const resultsDesc = $("#results-desc");
  const stemVocals = $("#stem-vocals");
  const stemInstr = $("#stem-instrumental");
  const instrTitle = $("#instr-title");
  const vocalsTitle = $("#vocals-title");
  const dlInstr = $("#dl-instrumental");
  const dlVocals = $("#dl-vocals");

  let selectedFile = null;
  let pollTimer = null;
  let deferredPrompt = null;
  /** @type {"split"|"vocal_remover"} */
  let currentMode = "split";

  const MODE_COPY = {
    split: {
      title: "人聲／伴奏 分離",
      subtitle:
        "上傳一首歌，AI 分離出<strong>人聲</strong>與<strong>伴奏</strong>，可即時預覽並下載。",
      start: "開始分離",
      resultsHeading: "分離結果",
      resultsDesc: "可直接播放預覽，或下載音訊檔。",
      done: "完成！可預覽並下載人聲／伴奏。",
      instrLabel: '伴奏 <span class="tag">Instrumental</span>',
      vocalsLabel: '人聲 <span class="tag">Vocals</span>',
      dlInstr: "下載伴奏",
      dlVocals: "下載人聲",
    },
    vocal_remover: {
      title: "人聲消除 · Vocal Remover",
      subtitle:
        "上傳一首歌，消除<strong>人聲</strong>後取得<strong>伴奏／卡拉OK</strong>軌，可預覽並下載。",
      start: "開始消除人聲",
      resultsHeading: "人聲消除結果",
      resultsDesc: "主要輸出為伴奏／卡拉OK；若有人聲軌亦可下載。",
      done: "完成！主要下載伴奏／卡拉OK。",
      instrLabel:
        '伴奏／卡拉OK <span class="tag">Instrumental</span>',
      vocalsLabel: '人聲（可選） <span class="tag">Vocals</span>',
      dlInstr: "下載伴奏／卡拉OK",
      dlVocals: "下載人聲",
    },
  };

  function applyMode(mode) {
    currentMode = mode === "vocal_remover" ? "vocal_remover" : "split";
    const copy = MODE_COPY[currentMode];
    pageTitle.textContent = copy.title;
    pageSubtitle.innerHTML = copy.subtitle;
    startBtn.textContent = copy.start;
    resultsHeading.textContent = copy.resultsHeading;
    resultsDesc.textContent = copy.resultsDesc;
    instrTitle.innerHTML = copy.instrLabel;
    vocalsTitle.innerHTML = copy.vocalsLabel;
    dlInstr.textContent = copy.dlInstr;
    dlVocals.textContent = copy.dlVocals;

    document.querySelectorAll(".mode-chip[data-mode]").forEach((chip) => {
      const on = chip.getAttribute("data-mode") === currentMode;
      chip.classList.toggle("active", on);
      chip.setAttribute("aria-selected", on ? "true" : "false");
    });

    resultsEl.classList.toggle("mode-split", currentMode === "split");
    resultsEl.classList.toggle(
      "mode-vocal-remover",
      currentMode === "vocal_remover"
    );
    stemInstr.classList.toggle("stem-primary", currentMode === "vocal_remover");
    stemVocals.classList.toggle(
      "stem-optional",
      currentMode === "vocal_remover"
    );
    stemVocals.classList.toggle("stem-primary", currentMode === "split");
  }

  document.querySelectorAll(".mode-chip[data-mode]").forEach((chip) => {
    chip.addEventListener("click", () => {
      applyMode(chip.getAttribute("data-mode"));
      resetResults();
      setStatus(false, "");
    });
  });
  applyMode("split");

  function providerLabel(h) {
    const p = h.provider || h.engine || "";
    if (p === "stemsplit" || h.engine === "stemsplit") {
      return "StemSplit API";
    }
    if (p === "demucs" || h.demucs_available) {
      return `Demucs · ${h.model || "htdemucs"}`;
    }
    return "ffmpeg 後備";
  }

  fetch("/api/health")
    .then((r) => r.json())
    .then((h) => {
      const el = document.querySelector("header .badge");
      if (!el || !h) return;
      const eng = providerLabel(h);
      el.textContent = `本機 Demo · ${eng} · PWA`;
      if (hintEl) {
        if (h.provider === "stemsplit" || h.engine === "stemsplit") {
          hintEl.innerHTML =
            "使用 <strong>StemSplit</strong> 雲端分離（API 金鑰僅存伺服器）。<br />支援「人聲／伴奏」與「人聲消除」；可安裝為 PWA。";
        } else if (h.provider === "demucs") {
          hintEl.innerHTML =
            "CPU 本機 Demucs 分離較慢；長音檔可能耗用大量記憶體。<br />亦可設定 <code>STEMSPLIT_API_KEY</code> 改走雲端。";
        } else {
          hintEl.innerHTML =
            "目前為 ffmpeg 中置／側邊後備。<br />設定 <code>STEMSPLIT_API_KEY</code> 或安裝 Demucs 後重啟可升級品質。";
        }
      }
    })
    .catch(() => {});

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/static/sw.js").catch(() => {});
    });
  }

  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredPrompt = e;
    if (!localStorage.getItem("hideInstallBanner")) {
      installBanner.classList.add("visible");
    }
  });

  installBtn?.addEventListener("click", async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    await deferredPrompt.userChoice;
    deferredPrompt = null;
    installBanner.classList.remove("visible");
  });

  dismissInstall?.addEventListener("click", () => {
    localStorage.setItem("hideInstallBanner", "1");
    installBanner.classList.remove("visible");
  });

  function setStatus(visible, msg, { progress = 0, warn = "", err = "" } = {}) {
    statusEl.classList.toggle("visible", visible);
    statusMsg.textContent = msg || "";
    statusWarn.textContent = warn || "";
    statusErr.textContent = err || "";
    progressBar.style.width = `${Math.max(0, Math.min(100, progress))}%`;
  }

  function resetResults() {
    resultsEl.classList.remove("visible");
    $("#audio-vocals").removeAttribute("src");
    $("#audio-instrumental").removeAttribute("src");
    $("#dl-vocals").removeAttribute("href");
    $("#dl-instrumental").removeAttribute("href");
    stemVocals.classList.remove("hidden");
  }

  function pickFile(file) {
    if (!file) return;
    selectedFile = file;
    fileNameEl.textContent = file.name;
    startBtn.disabled = false;
    resetResults();
    setStatus(false, "");
  }

  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });
  fileInput.addEventListener("change", () => pickFile(fileInput.files?.[0]));

  ["dragenter", "dragover"].forEach((ev) => {
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach((ev) => {
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
    });
  });
  dropzone.addEventListener("drop", (e) => {
    const f = e.dataTransfer?.files?.[0];
    pickFile(f);
  });

  async function pollJob(jobId) {
    try {
      const res = await fetch(`/api/jobs/${jobId}`);
      if (!res.ok) throw new Error("無法取得任務狀態");
      const job = await res.json();
      const mode = job.mode || currentMode;
      const providerHint =
        job.provider === "stemsplit"
          ? "（StemSplit）"
          : job.provider === "demucs"
            ? "（Demucs）"
            : job.provider === "ffmpeg"
              ? "（ffmpeg）"
              : "";
      setStatus(true, `${job.message || job.status}${providerHint}`, {
        progress: job.progress || 0,
        warn: job.warning || "",
        err: job.status === "error" ? job.error || "處理失敗" : "",
      });

      if (job.status === "done") {
        clearInterval(pollTimer);
        pollTimer = null;
        startBtn.disabled = false;

        if (job.instrumental_stream) {
          $("#audio-instrumental").src = job.instrumental_stream;
          $("#dl-instrumental").href = job.instrumental_url;
          stemInstr.classList.remove("hidden");
        }
        if (job.vocals_stream) {
          $("#audio-vocals").src = job.vocals_stream;
          $("#dl-vocals").href = job.vocals_url;
          stemVocals.classList.remove("hidden");
        } else {
          stemVocals.classList.add("hidden");
        }

        resultsEl.classList.toggle("mode-split", mode === "split");
        resultsEl.classList.toggle(
          "mode-vocal-remover",
          mode === "vocal_remover"
        );
        resultsEl.classList.add("visible");
        const doneMsg =
          MODE_COPY[mode === "vocal_remover" ? "vocal_remover" : "split"].done;
        setStatus(true, doneMsg, { progress: 100 });
        return;
      }
      if (job.status === "error") {
        clearInterval(pollTimer);
        pollTimer = null;
        startBtn.disabled = false;
      }
    } catch (err) {
      clearInterval(pollTimer);
      pollTimer = null;
      startBtn.disabled = false;
      setStatus(true, "輪詢失敗", { err: String(err.message || err) });
    }
  }

  startBtn.addEventListener("click", async () => {
    if (!selectedFile) return;
    startBtn.disabled = true;
    resetResults();
    setStatus(true, "上傳中…", { progress: 2 });

    const fd = new FormData();
    fd.append("file", selectedFile, selectedFile.name);
    fd.append("mode", currentMode);

    try {
      const res = await fetch("/api/upload", { method: "POST", body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || data.message || `上傳失敗 (${res.status})`);
      }
      const startMsg =
        (data.mode || currentMode) === "vocal_remover"
          ? "已上傳，開始消除人聲…"
          : "已上傳，開始分離…";
      setStatus(true, startMsg, {
        progress: 8,
        warn: data.warning || "",
      });
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = setInterval(() => pollJob(data.job_id), 1500);
      pollJob(data.job_id);
    } catch (err) {
      startBtn.disabled = false;
      setStatus(true, "上傳失敗", { err: String(err.message || err) });
    }
  });
})();
