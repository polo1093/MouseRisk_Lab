/* BotRisk v2: click-driven scoring + 10s rolling window + idle auto-update + history */

const BotRisk = (() => {
  const botdAgentPromise = import("https://openfpcdn.io/botd/v2").then((Botd) => Botd.load());
  let botdResultPromise = null;

  function nowMs() { return performance.now(); }

  function createSessionId() {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function quantile(arr, q) {
    if (!arr.length) return 0;
    const a = [...arr].sort((x, y) => x - y);
    const pos = (a.length - 1) * q;
    const base = Math.floor(pos);
    const rest = pos - base;
    return a[base + 1] !== undefined
      ? a[base] + rest * (a[base + 1] - a[base])
      : a[base];
  }

  function mean(arr) {
    if (!arr.length) return 0;
    return arr.reduce((s, x) => s + x, 0) / arr.length;
  }

  function std(arr) {
    if (arr.length < 2) return 0;
    const m = mean(arr);
    const v = arr.reduce((s, x) => s + (x - m) * (x - m), 0) / (arr.length - 1);
    return Math.sqrt(v);
  }

  function angleBetween(v1x, v1y, v2x, v2y) {
    const dot = v1x * v2x + v1y * v2y;
    const n1 = Math.hypot(v1x, v1y);
    const n2 = Math.hypot(v2x, v2y);
    if (n1 === 0 || n2 === 0) return 0;
    const c = Math.min(1, Math.max(-1, dot / (n1 * n2)));
    return Math.acos(c);
  }

  function envSignals() {
    const nav = navigator || {};
    return {
      webdriver: !!nav.webdriver,
      plugins_len: (nav.plugins && nav.plugins.length) ? nav.plugins.length : 0,
      languages_len: (nav.languages && nav.languages.length) ? nav.languages.length : 0,
      hardware_concurrency: nav.hardwareConcurrency || null,
      max_touch_points: nav.maxTouchPoints || 0,
      ua_len: (nav.userAgent && nav.userAgent.length) ? nav.userAgent.length : 0,
    };
  }

  function computeFeatures(points) {
    // points: [{t,x,y,type,isTrusted,pointerType}]
    const n = points.length;
    if (n < 5) return null;

    const dt = [];
    const speed = [];
    let pathLen = 0;
    const turnAngles = [];
    let mousemoveTeleportCount = 0;

    for (let i = 1; i < n; i++) {
      const a = points[i - 1], b = points[i];
      const dti = Math.max(0.5, b.t - a.t);
      dt.push(dti);

      const dx = b.x - a.x, dy = b.y - a.y;
      const dist = Math.hypot(dx, dy);
      pathLen += dist;

      const speedPxPerSecond = (dist / dti) * 1000.0;
      speed.push(speedPxPerSecond); // px/s
      if (a.type === "m" && b.type === "m" && speedPxPerSecond > 8000.0) {
        mousemoveTeleportCount += 1;
      }
    }

    for (let i = 2; i < n; i++) {
      const p0 = points[i - 2], p1 = points[i - 1], p2 = points[i];
      const v1x = p1.x - p0.x, v1y = p1.y - p0.y;
      const v2x = p2.x - p1.x, v2y = p2.y - p1.y;
      turnAngles.push(Math.abs(angleBetween(v1x, v1y, v2x, v2y)));
    }

    const start = points[0], end = points[n - 1];
    const displacement = Math.hypot(end.x - start.x, end.y - start.y);
    const straightness = pathLen > 0 ? Math.min(1, displacement / pathLen) : 0;

    const trustedRatio = points.filter(p => p.isTrusted).length / n;
    const durationMs = Math.max(0, end.t - start.t);
    const mousemoveCount = points.filter(p => p.type === "m").length;

    return {
      n,
      duration_ms: durationMs,
      mousemove_count: mousemoveCount,
      mousemove_teleport_count: mousemoveTeleportCount,
      mean_dt: mean(dt),
      std_dt: std(dt),
      p90_dt: quantile(dt, 0.90),

      mean_speed: mean(speed),
      std_speed: std(speed),
      max_speed: speed.length ? Math.max(...speed) : 0,

      straightness,
      mean_abs_turn: mean(turnAngles),

      trusted_ratio: trustedRatio,
      pointer_type: points[0].pointerType || null,

      ...envSignals(),
    };
  }

  async function postJSON(url, body) {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  }

  function fmtTime(d = new Date()) {
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    const ss = String(d.getSeconds()).padStart(2, "0");
    return `${hh}:${mm}:${ss}`;
  }

  function start(opts) {
    const {
      scoreEndpoint,
      telemetryEndpoint = null,
      overlayProbEl,
      overlayMetaEl,
      overlaySignalsEl,
      overlayStatusEl,
      overlayEl,
      riskBarEl = null,
      windowSelectEl = null,
      windowBadgeEl = null,

      // NEW behavior knobs
      target = window,
      horizonMs: initialHorizonMs = 10_000,        // fenetre glissante
      minPoints: initialMinPoints = 25,            // nb min d'events pour scorer
      idleUpdateMs = 10_000,     // si aucun clic depuis last update => auto-update après 10s
      housekeepingEveryMs = 500, // purge buffer
      historyEl = null,          // <ul> ou <div> qui reçoit l'historique
      historyMax = 6,            // nb max de lignes visibles

    } = opts;

    let points = [];
    let horizonMs = initialHorizonMs;
    let minPoints = initialMinPoints;
    let lastScoreAt = 0;
    let lastClickAt = 0;
    let scoring = false;
    let lastTelemetryTs = 0;
    let lastRenderedKey = "";
    const sessionId = createSessionId();

    function prune() {
      const t = nowMs();
      const cutoff = t - horizonMs - 250; // petite marge
      if (points.length && points[0].t < cutoff) {
        // remove oldest until within window
        let k = 0;
        while (k < points.length && points[k].t < cutoff) k++;
        if (k > 0) points.splice(0, k);
      }
    }

    function minPointsForWindow(windowMs) {
      if (windowMs <= 1000) return 5;
      if (windowMs <= 2000) return 8;
      if (windowMs <= 5000) return 12;
      return initialMinPoints;
    }

    function renderWindowLabel() {
      const seconds = Math.round(horizonMs / 1000);
      if (windowBadgeEl) windowBadgeEl.textContent = `Fenetre ${seconds}s`;
      if (overlayMetaEl && lastScoreAt === 0) {
        overlayMetaEl.textContent = `waiting for activity... window=${seconds}s`;
      }
    }

    function setDetectionWindow(windowMs) {
      horizonMs = Number(windowMs) || 10_000;
      minPoints = minPointsForWindow(horizonMs);
      prune();
      renderWindowLabel();
    }

    function pushPoint(e, type) {
      const t = nowMs();
      points.push({
        t,
        x: e.clientX,
        y: e.clientY,
        type,
        isTrusted: !!e.isTrusted,
        pointerType: e.pointerType || "mouse",
      });
    }

    function windowPoints() {
      prune();
      const t = nowMs();
      const cutoff = t - horizonMs;
      // points already pruned, but keep strict window
      const w = [];
      for (let i = 0; i < points.length; i++) {
        if (points[i].t >= cutoff) w.push(points[i]);
      }
      return w;
    }

    function pushHistory(pct, model, raw, reason) {
      if (!historyEl) return;

      const line = document.createElement("div");
      line.className = "botrisk-history-line";
      const compactReason = reason
        .replace("BotD: ", "B:")
        .replace("Mouse: ", "M:")
        .replace("mouse_heuristic_v1", "mouse")
        .replace("combo_v1", "combo");
      line.textContent = `${fmtTime()}  ${pct}%  ${compactReason}`;
      line.title = `${fmtTime()} | ${pct}% | ${reason} | ${model} | raw=${raw.toFixed(3)}`;

      historyEl.prepend(line);

      // trim
      while (historyEl.children.length > historyMax) {
        historyEl.removeChild(historyEl.lastChild);
      }

      historyEl.scrollTop = 0;
    }

    function updateRiskClass(prob) {
      if (!overlayEl) return;
      overlayEl.classList.remove("risk-low", "risk-mid", "risk-high");
      if (prob >= 0.7) {
        overlayEl.classList.add("risk-high");
      } else if (prob >= 0.5) {
        overlayEl.classList.add("risk-mid");
      } else {
        overlayEl.classList.add("risk-low");
      }

      if (riskBarEl) {
        riskBarEl.style.width = `${Math.round(prob * 100)}%`;
      }
    }

    function renderSignals(signals) {
      if (!overlaySignalsEl) return "";
      overlaySignalsEl.innerHTML = "";

      const lines = [];

      if (signals.botd_v2) {
        const botdPct = Math.round(signals.botd_v2.score * 100);
        const kind = signals.botd_v2.raw?.kind;
        lines.push(`BotD: ${botdPct}%${kind ? ` (kind=${kind})` : ""}`);
      }
      if (signals.mouse_heuristic_v1) {
        const mousePct = Math.round(signals.mouse_heuristic_v1.score * 100);
        lines.push(`Mouse: ${mousePct}%`);
      }
      if (signals.external_fe_bot_v1) {
        const externalPct = Math.round(signals.external_fe_bot_v1.score * 100);
        const status = signals.external_fe_bot_v1.raw?.status;
        lines.push(`External ML: ${externalPct}%${status && status !== "ok" ? ` (${status})` : ""}`);
      }

      lines.forEach((text) => {
        const row = document.createElement("div");
        row.textContent = text;
        overlaySignalsEl.appendChild(row);
      });

      return lines.join(", ");
    }

    function updateStatus(prob, signals) {
      if (!overlayStatusEl) return "";
      let message = "Low risk";

      if (prob >= 0.7) {
        message = "High risk";
      } else if (prob >= 0.5) {
        message = "Elevated";
      }

      const botdBot = signals.botd_v2?.raw?.bot === true;
      if (botdBot) {
        const kind = signals.botd_v2.raw?.kind || "unknown";
        message = `${message}: ${kind}`;
      }

      overlayStatusEl.textContent = message;
      return message;
    }

    function renderScoreEvent(event) {
      const prob = Number(event.bot_probability || 0);
      const pct = Math.round(prob * 100);
      const raw = Number(event.raw_score || prob);
      const model = event.model || "unknown";
      const signals = event.signals || {};
      const renderKey = `${event.reason || ""}|${model}|${raw.toFixed(3)}|${pct}`;
      if (renderKey === lastRenderedKey) return;
      lastRenderedKey = renderKey;

      if (overlayProbEl) overlayProbEl.textContent = `${pct}%`;
      if (overlayMetaEl) overlayMetaEl.textContent = `${model} | raw=${raw.toFixed(3)} | w=${event.n || "external"}`;

      const signalSummary = renderSignals(signals);
      updateRiskClass(prob);
      updateStatus(prob, signals);

      const reason = event.reason || "external";
      const historyReason = signalSummary ? `${reason} | ${signalSummary}` : reason;
      pushHistory(pct, model, raw, historyReason);
    }

    function ensureBotdResult() {
      if (!botdResultPromise) {
        botdResultPromise = botdAgentPromise
          .then((agent) => agent.detect())
          .catch((err) => {
            console.warn("BotD detect failed", err);
            return null;
          });
      }
      return botdResultPromise;
    }

    async function scoreNow(reason) {
      if (scoring) return;
      scoring = true;

      try {
        const w = windowPoints();
        if (w.length < minPoints) {
          if (overlayMetaEl) overlayMetaEl.textContent = `not enough events (${w.length}/${minPoints})`;
          return;
        }

        const features = computeFeatures(w);
        if (!features) return;

        const botd = await ensureBotdResult();
        const payload = {
          ...features,
          botd_bot: botd?.bot ?? null,
          botd_kind: botd?.bot ? (botd.botKind ?? "unknown") : null,
          session_id: sessionId,
          reason,
        };

        const out = await postJSON(scoreEndpoint, payload);
        renderScoreEvent({ ...out, reason, n: w.length, ts: Date.now() / 1000 });

        lastScoreAt = nowMs();
      } finally {
        scoring = false;
      }
    }

    async function pullLatestTelemetry() {
      if (!telemetryEndpoint) return;
      try {
        const response = await fetch(`${telemetryEndpoint}?limit=1`);
        if (!response.ok) return;
        const events = await response.json();
        const event = events[events.length - 1];
        if (!event || !event.ts || event.ts <= lastTelemetryTs) return;
        lastTelemetryTs = event.ts;
        renderScoreEvent(event);
      } catch (err) {
        console.warn("telemetry poll failed", err);
      }
    }

    // Capture
    target.addEventListener("pointermove", (e) => pushPoint(e, "m"), { passive: true });
    target.addEventListener("pointerdown", (e) => pushPoint(e, "d"));
    target.addEventListener("pointerup",   (e) => pushPoint(e, "u"));

    // Click => score immediately
    target.addEventListener("click", async (e) => {
      pushPoint(e, "c");
      lastClickAt = nowMs();
      await scoreNow("click");
    });

    // Housekeeping + idle auto-update
    setInterval(() => {
      prune();
      const t = nowMs();

      // auto-update only if no click since last update for idleUpdateMs
      if (lastScoreAt > 0) {
        const noClickSinceLastUpdate = (t - lastClickAt) >= idleUpdateMs;
        const staleScore = (t - lastScoreAt) >= idleUpdateMs;

        if (noClickSinceLastUpdate && staleScore) {
          // score on latest 10s window
          scoreNow("auto");
        }
      } else {
        // first auto score once there is enough activity (optional)
        // comment/uncomment depending on what you prefer:
        // if (windowPoints().length >= minPoints) scoreNow("auto");
      }
    }, housekeepingEveryMs);

    setInterval(pullLatestTelemetry, 1500);

    if (windowSelectEl) {
      windowSelectEl.value = String(horizonMs);
      windowSelectEl.addEventListener("change", () => {
        setDetectionWindow(windowSelectEl.value);
        scoreNow("window");
      });
    }

    // First feedback: show waiting state.
    setDetectionWindow(horizonMs);
    if (overlayStatusEl) overlayStatusEl.textContent = "Low risk";
    updateRiskClass(0);
  }

  return { start };
})();
