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

    programs.forEach((program) => {
      const option = document.createElement("option");
      option.value = program.filename;
      option.textContent = program.filename;
      selectEl.appendChild(option);
    });
  }

  function start(opts) {
    const {
      programsEndpoint,
      runEndpoint,
      selectEl,
      regionEl,
      countEl,
      focusWaitEl,
      outputEl,
      refreshButton,
      runButton,
      estimateRegionButton,
      target,
    } = opts;

    async function refreshPrograms() {
      setOutput(outputEl, "Chargement des programmes...");
      try {
        const programs = await getJSON(programsEndpoint);
        renderPrograms(selectEl, programs);
        setOutput(outputEl, `${programs.length} programme(s) disponible(s).`);
      } catch (err) {
        setOutput(outputEl, `Erreur chargement programmes: ${err.message}`);
      }
    }

    async function runProgram() {
      const filename = selectEl.value;
      if (!filename) {
        setOutput(outputEl, "Aucun programme selectionne.");
        return;
      }

      const count = Number.parseInt(countEl.value, 10);
      const focusWait = Number.parseFloat(focusWaitEl.value);
      if (!isValidRegion(regionEl.value.trim())) {
        regionEl.value = estimateScreenRegion(target);
      }
      if (!isValidRegion(regionEl.value.trim())) {
        setOutput(outputEl, `Region ecran invalide: ${regionEl.value || "(vide)"}`);
        return;
      }

      runButton.disabled = true;
      setOutput(
        outputEl,
        `Lancement de ${filename}...\nRegion utilisee: ${regionEl.value.trim()}\n${describeWindow()}\nF12 pour arreter.`
      );

      try {
        const result = await postJSON(runEndpoint, {
          filename,
          region: regionEl.value.trim(),
          count: Number.isFinite(count) ? count : 8,
          focus_wait: Number.isFinite(focusWait) ? focusWait : 3,
          timeout: 15,
          base_url: window.location.origin,
        });

        const output = [
          `ok=${result.ok}`,
          `returncode=${result.returncode ?? ""}`,
          `duration=${result.duration ? result.duration.toFixed(2) : "0.00"}s`,
          result.run_count ? `clicks=${result.run_count}/${result.requested_count ?? result.run_count}` : "",
          "",
          "STDOUT",
          result.stdout || "(vide)",
          "",
          "STDERR",
          result.stderr || "(vide)",
          result.error ? `\nERROR\n${result.error}` : "",
        ].join("\n");
        setOutput(outputEl, output);
      } catch (err) {
        setOutput(outputEl, `Erreur execution: ${err.message}`);
      } finally {
        runButton.disabled = false;
      }
    }

    refreshButton.addEventListener("click", refreshPrograms);
    runButton.addEventListener("click", runProgram);
    estimateRegionButton.addEventListener("click", () => {
      regionEl.value = estimateScreenRegion(target);
      setOutput(outputEl, `Region estimee: ${regionEl.value}\n${describeWindow()}`);
    });

    regionEl.value = estimateScreenRegion(target);
    refreshPrograms();
  }

  return { start };
})();
