const ProgramRunner = (() => {
  function setOutput(outputEl, text) {
    outputEl.textContent = text || "";
    outputEl.scrollTop = outputEl.scrollHeight;
  }

  function estimateScreenRegion(target) {
    const rect = target.getBoundingClientRect();
    const scale = window.devicePixelRatio || 1;
    const viewport = window.visualViewport;
    const viewportLeft = viewport ? viewport.offsetLeft : 0;
    const viewportTop = viewport ? viewport.offsetTop : 0;

    const hasFirefoxViewportOrigin =
      Number.isFinite(window.mozInnerScreenX) && Number.isFinite(window.mozInnerScreenY);
    const viewportScreenLeft = hasFirefoxViewportOrigin
      ? window.mozInnerScreenX
      : (Number.isFinite(window.screenLeft) ? window.screenLeft : window.screenX) +
        Math.max(0, (window.outerWidth - window.innerWidth) / 2);
    const viewportScreenTop = hasFirefoxViewportOrigin
      ? window.mozInnerScreenY
      : (Number.isFinite(window.screenTop) ? window.screenTop : window.screenY) +
        Math.max(0, window.outerHeight - window.innerHeight);

    const x1 = Math.round((viewportScreenLeft + viewportLeft + rect.left) * scale);
    const y1 = Math.round((viewportScreenTop + viewportTop + rect.top) * scale);
    const x2 = Math.round((viewportScreenLeft + viewportLeft + rect.right) * scale);
    const y2 = Math.round((viewportScreenTop + viewportTop + rect.bottom) * scale);
    return `${x1},${y1},${x2},${y2}`;
  }

  function describeWindow() {
    const screenLeft = Number.isFinite(window.screenLeft) ? window.screenLeft : window.screenX;
    const screenTop = Number.isFinite(window.screenTop) ? window.screenTop : window.screenY;
    const firefoxOrigin =
      Number.isFinite(window.mozInnerScreenX) && Number.isFinite(window.mozInnerScreenY)
        ? ` mozViewport=(${Math.round(window.mozInnerScreenX)},${Math.round(window.mozInnerScreenY)})`
        : "";
    return `fenetre=(${Math.round(screenLeft)},${Math.round(screenTop)}) viewport=${window.innerWidth}x${window.innerHeight} scale=${window.devicePixelRatio || 1}${firefoxOrigin}`;
  }

  function isValidRegion(value) {
    if (!/^-?\d+,-?\d+,-?\d+,-?\d+$/.test(value)) return false;
    const [x1, y1, x2, y2] = value.split(",").map((part) => Number.parseInt(part, 10));
    return Number.isFinite(x1) && Number.isFinite(y1) && Number.isFinite(x2) && Number.isFinite(y2) && x2 > x1 && y2 > y1;
  }

  async function getJSON(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async function postJSON(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      let detail = "";
      try {
        const errorBody = await response.json();
        detail = errorBody.detail ? ` ${JSON.stringify(errorBody.detail)}` : "";
      } catch {
        detail = "";
      }
      throw new Error(`HTTP ${response.status}${detail}`);
    }
    return response.json();
  }

  function renderPrograms(selectEl, programs) {
    selectEl.innerHTML = "";
    if (!programs.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "Aucun fichier dans mouse_programs/";
      selectEl.appendChild(option);
      return;
    }

    const ordered = [...programs].sort((a, b) => {
      if (a.filename === "adaptive_spiral_human_plus.py") return -1;
      if (b.filename === "adaptive_spiral_human_plus.py") return 1;
      return a.filename.localeCompare(b.filename);
    });

    ordered.forEach((program) => {
      const option = document.createElement("option");
      option.value = program.filename;
      option.textContent = program.filename;
      selectEl.appendChild(option);
    });
  }

  function formatPct(score) {
    return `${Math.round(Number(score || 0) * 100)}%`;
  }

  function summarizeEvents(events, startedAt) {
    const runEvents = events.filter((event) => Number(event.ts || 0) >= startedAt);
    let maxScore = null;
    let latest = null;

    runEvents.forEach((event) => {
      const score = Number(event.bot_probability);
      if (!Number.isFinite(score)) return;
      if (maxScore === null || score > maxScore) maxScore = score;
      latest = event;
    });

    return { runEvents, latest, maxScore };
  }

  function start(opts) {
    const {
      programsEndpoint,
      runEndpoint,
      selectEl,
      regionEl,
      countEl,
      focusWaitEl,
      innerBoxPercentEl,
      clickBoxPercentEl,
      delayChanceEl,
      mouseButtonEl,
      innerBoxFieldEl,
      clickBoxFieldEl,
      delayChanceFieldEl,
      mouseButtonFieldEl,
      outputEl,
      refreshButton,
      runButton,
      estimateRegionButton,
      runModeEls = [],
      telemetryEndpoint = null,
      target,
    } = opts;

    let outputLines = [];
    let historyLines = [];

    function renderOutput() {
      setOutput(outputEl, [...outputLines, ...historyLines].join("\n"));
    }

    function selectedRunMode() {
      return runModeEls.find((input) => input.checked)?.value || "short";
    }

    async function refreshPrograms() {
      setOutput(outputEl, "Chargement des programmes...");
      try {
        const programs = await getJSON(programsEndpoint);
        renderPrograms(selectEl, programs);
        syncPlusOptions();
        setOutput(outputEl, `${programs.length} programme(s) disponible(s).`);
      } catch (err) {
        setOutput(outputEl, `Erreur chargement programmes: ${err.message}`);
      }
    }

    function selectedProgramUsesPlusOptions() {
      return selectEl.value === "adaptive_spiral_human_plus.py";
    }

    function syncPlusOptions() {
      const visible = selectedProgramUsesPlusOptions();
      if (innerBoxFieldEl) innerBoxFieldEl.hidden = !visible;
      if (clickBoxFieldEl) clickBoxFieldEl.hidden = !visible;
      if (delayChanceFieldEl) delayChanceFieldEl.hidden = !visible;
      if (mouseButtonFieldEl) mouseButtonFieldEl.hidden = !visible;
    }

    async function runProgram() {
      const filename = selectEl.value;
      if (!filename) {
        setOutput(outputEl, "Aucun programme selectionne.");
        return;
      }

      const count = Number.parseInt(countEl.value, 10);
      const focusWait = Number.parseFloat(focusWaitEl.value);
      const runMode = selectedRunMode();
      const timeoutSeconds = runMode === "continuous" ? 60 : 15;
      const runCount = runMode === "continuous"
        ? Math.max(1, Math.ceil((timeoutSeconds - (Number.isFinite(focusWait) ? focusWait : 3) - 0.5) * 2.4))
        : (Number.isFinite(count) ? count : 20);
      regionEl.value = estimateScreenRegion(target);
      if (!isValidRegion(regionEl.value.trim())) {
        setOutput(outputEl, `Region ecran invalide: ${regionEl.value || "(vide)"}`);
        return;
      }

      runButton.disabled = true;
      const startedAt = Date.now() / 1000;
      let pollTimer = null;
      historyLines = [];
      outputLines = [
        `Lancement de ${filename}...`,
        `Mode=${runMode === "continuous" ? "60s continu" : "15s"}`,
        `Region visible rafraichie: ${regionEl.value.trim()}`,
        describeWindow(),
        "F12 pour arreter.",
        "",
        "HISTORIQUE 5S",
        "en attente des scores...",
      ];
      renderOutput();

      async function appendTelemetrySnapshot(final = false) {
        if (!telemetryEndpoint) return { latest: null, maxScore: null, runEvents: [] };
        try {
          const events = await getJSON(`${telemetryEndpoint}?limit=200`);
          const summary = summarizeEvents(events, startedAt);
          const elapsed = Math.max(0, Math.round((Date.now() / 1000) - startedAt));
          const latestText = summary.latest
            ? `dernier=${formatPct(summary.latest.bot_probability)} reason=${summary.latest.reason || "?"}`
            : "aucun score";
          const maxText = summary.maxScore === null ? "max=--" : `max=${formatPct(summary.maxScore)}`;
          const prefix = final ? "final" : `t+${elapsed}s`;
          const line = `${prefix} ${latestText} ${maxText} mesures=${summary.runEvents.length}`;
          if (historyLines[historyLines.length - 1] !== line) {
            historyLines.push(line);
            renderOutput();
          }
          return summary;
        } catch (err) {
          const line = `telemetrie indisponible: ${err.message}`;
          if (historyLines[historyLines.length - 1] !== line) {
            historyLines.push(line);
            renderOutput();
          }
          return { latest: null, maxScore: null, runEvents: [] };
        }
      }

      try {
        pollTimer = window.setInterval(() => {
          appendTelemetrySnapshot();
        }, 5000);

        const payload = {
          filename,
          region: regionEl.value.trim(),
          count: runCount,
          focus_wait: Number.isFinite(focusWait) ? focusWait : 3,
          timeout: timeoutSeconds,
          base_url: window.location.origin,
        };

        if (selectedProgramUsesPlusOptions()) {
          payload.inner_box_percent = Number(innerBoxPercentEl.value);
          payload.click_box_percent = Number(clickBoxPercentEl.value);
          payload.delay_chance = Number(delayChanceEl.value);
          payload.mouse_button = mouseButtonEl.value;
        }

        const result = await postJSON(runEndpoint, payload);
        if (pollTimer) {
          window.clearInterval(pollTimer);
          pollTimer = null;
        }
        const telemetrySummary = await appendTelemetrySnapshot(true);

        outputLines = [
          `ok=${result.ok}`,
          `returncode=${result.returncode ?? ""}`,
          `duration=${result.duration ? result.duration.toFixed(2) : "0.00"}s`,
          result.run_count ? `clicks=${result.run_count}/${result.requested_count ?? result.run_count}` : "",
          telemetrySummary.maxScore === null ? "score_max=--" : `score_max=${formatPct(telemetrySummary.maxScore)}`,
          result.log_path ? `log=${result.log_path}` : "",
          "",
          "STDOUT",
          result.stdout || "(vide)",
          "",
          "STDERR",
          result.stderr || "(vide)",
          result.error ? `\nERROR\n${result.error}` : "",
          "",
          "HISTORIQUE 5S",
        ];
        renderOutput();
      } catch (err) {
        outputLines = [`Erreur execution: ${err.message}`, "", "HISTORIQUE 5S"];
        renderOutput();
      } finally {
        if (pollTimer) window.clearInterval(pollTimer);
        runButton.disabled = false;
      }
    }

    refreshButton.addEventListener("click", refreshPrograms);
    runButton.addEventListener("click", runProgram);
    selectEl.addEventListener("change", syncPlusOptions);
    estimateRegionButton.addEventListener("click", () => {
      regionEl.value = estimateScreenRegion(target);
      setOutput(outputEl, `Region estimee: ${regionEl.value}\n${describeWindow()}`);
    });

    regionEl.value = estimateScreenRegion(target);
    refreshPrograms();
    syncPlusOptions();
  }

  return { start };
})();
