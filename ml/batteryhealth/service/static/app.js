const TEAL = "#0f766e";
const AMBER = "#d97706";
const ROSE = "#be123c";
const SLATE = "#64748b";

const state = {
  battery: null,
  summary: null,
  forecast: null,
  trajectory: [],
  charts: {},
};

const $ = (id) => document.getElementById(id);

function discharges() {
  return (state.battery?.cycles || []).filter((c) => String(c.type || "").toLowerCase() === "discharge");
}

function cycleByIndex(index) {
  const list = discharges();
  const matches = list.filter((c) => Number(c.cycleIndex) <= Number(index));
  return matches.at(-1) || list[0] || null;
}

function hasTrace(cycle) {
  return Boolean(cycle && cycle.timeS && cycle.timeS.length > 1 && cycle.voltageV && cycle.voltageV.length > 1);
}

function showError(message) {
  const el = $("error-line");
  if (!message) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  el.hidden = false;
  el.textContent = message;
}

function setStatus(text) {
  $("status-line").textContent = text;
}

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      detail = await res.text();
    }
    throw new Error(detail);
  }
  return res.json();
}

function lineChart(id, datasets, xTitle, yTitle) {
  const existing = state.charts[id];
  if (existing) existing.destroy();
  const ctx = $(id).getContext("2d");
  state.charts[id] = new Chart(ctx, {
    type: "line",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom" } },
      elements: { point: { radius: 0 }, line: { tension: 0.15, borderWidth: 2 } },
      scales: {
        x: { type: "linear", title: { display: true, text: xTitle } },
        y: { title: { display: true, text: yTitle } },
      },
    },
  });
}

function xy(xs, ys) {
  const n = Math.min(xs.length, ys.length);
  const points = [];
  for (let i = 0; i < n; i += 1) points.push({ x: xs[i], y: ys[i] });
  return points;
}

function renderSensors(cycle) {
  if (!hasTrace(cycle)) {
    lineChart("sensor-chart", [], "Time (s)", "V / A / °C");
    return;
  }
  lineChart(
    "sensor-chart",
    [
      { label: "Voltage (V)", data: xy(cycle.timeS, cycle.voltageV), borderColor: TEAL },
      { label: "Current (A)", data: xy(cycle.timeS, cycle.currentA || []), borderColor: AMBER },
      { label: "Temperature (°C)", data: xy(cycle.timeS, cycle.temperatureC || []), borderColor: ROSE },
    ],
    "Time (s)",
    "V / A / °C",
  );
}

function fadePoints(battery) {
  return discharges()
    .filter((c) => c.capacityAh != null)
    .map((c) => ({ x: c.cycleIndex, y: c.capacityAh }));
}

function renderFade(stressed) {
  const datasets = [{ label: "Measured capacity", data: fadePoints(state.battery), borderColor: TEAL }];
  if (stressed?.length) {
    datasets.push({
      label: "Stressed capacity",
      data: stressed.map((p) => ({ x: p.cycleIndex, y: p.capacityAh })),
      borderColor: ROSE,
    });
  }
  lineChart("fade-chart", datasets, "Cycle", "Capacity (Ah)");
}

function renderSoh(points) {
  lineChart(
    "soh-chart",
    [
      {
        label: "Predicted SoH %",
        data: points.map((p) => ({ x: p.cycleIndex, y: p.predictedSoh * 100 })),
        borderColor: TEAL,
      },
      {
        label: "Measured SoH %",
        data: points.filter((p) => p.observedSoh != null).map((p) => ({ x: p.cycleIndex, y: p.observedSoh * 100 })),
        borderColor: SLATE,
        borderDash: [4, 3],
      },
    ],
    "Cycle",
    "SoH (%)",
  );
}

function renderStress(sim) {
  const baseline = (sim?.baseline || []).map((p) => ({ x: p.cycleIndex, y: p.capacityAh }));
  const stressed = (sim?.stressed || []).map((p) => ({ x: p.cycleIndex, y: p.capacityAh }));
  lineChart(
    "stress-chart",
    [
      { label: "Measured capacity", data: baseline, borderColor: TEAL },
      { label: "Stressed capacity", data: stressed, borderColor: ROSE },
    ],
    "Cycle",
    "Capacity (Ah)",
  );
}

function selectedCycleIndex() {
  return Number($("cycle-slider").value);
}

function refreshCycleUi() {
  const cycle = cycleByIndex(selectedCycleIndex());
  $("cycle-value").textContent = cycle ? `Cycle ${cycle.cycleIndex}` : "—";
  if (!cycle) {
    $("cycle-caption").textContent = "Select a discharge cycle with a sensor trace.";
    renderSensors(null);
    return;
  }
  const cap = cycle.capacityAh != null ? `${Number(cycle.capacityAh).toFixed(3)} Ah` : "no capacity";
  $("cycle-caption").textContent = hasTrace(cycle)
    ? `Cycle ${cycle.cycleIndex} · ${cycle.type} · ${cap}`
    : `Cycle ${cycle.cycleIndex} has fade data only. Pick a traced cycle (demo: 1, 40, 80, 120, last).`;
  renderSensors(cycle);
}

function applyBattery(record, summary, status) {
  state.battery = record;
  state.summary = summary;
  const id = summary.batteryId || record.batteryId || "battery";
  const source = (summary.source || record.source || "").toUpperCase();
  $("battery-title").textContent = `${id} · ${source || "FILE"}`;
  const first = summary.firstCapacityAh != null ? Number(summary.firstCapacityAh).toFixed(3) : "—";
  const last = summary.lastCapacityAh != null ? Number(summary.lastCapacityAh).toFixed(3) : "—";
  $("summary-line").textContent =
    `${summary.nCycles} discharge cycles · rated ${Number(summary.ratedCapacityAh).toFixed(2)} Ah · ` +
    `EOL ${(summary.eolCapacityFraction * 100).toFixed(0)}% (${Number(summary.eolCapacityAh).toFixed(2)} Ah) · ` +
    `capacity ${first} → ${last} Ah`;
  $("empty-hint").textContent = "";
  setStatus(status);
  showError("");

  const slider = $("cycle-slider");
  slider.min = String(summary.cycleMin);
  slider.max = String(summary.cycleMax);
  slider.value = String(summary.defaultCycle);
  slider.disabled = false;
  refreshCycleUi();
  renderFade();
}

async function refreshForecast() {
  if (!state.battery) return;
  const forecast = await api("/workspace/forecast", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ battery: state.battery, cycle_index: selectedCycleIndex() }),
  });
  state.forecast = forecast;
  const oem = $("oem-toggle").checked;
  const rul = oem ? forecast.oemRulCycles : forecast.predictedRulCycles;
  $("soh-text").textContent = `${forecast.predictedSohPercent.toFixed(1)}%`;
  $("rul-text").textContent = `${Math.round(rul)} cycles`;
  $("forecast-headline").textContent = `${forecast.batteryId} cycle ${forecast.cycleIndex}`;
  if (forecast.observedSoh != null) {
    const err = Math.abs(forecast.predictedSoh - forecast.observedSoh) * 100;
    $("observed-text").textContent =
      `Measured SoH ${(forecast.observedSoh * 100).toFixed(1)}%  ·  |error| ${err.toFixed(2)} points`;
  } else {
    $("observed-text").textContent =
      "No coulomb-counted capacity on this cycle — SoH is inferred from the V/I/T curve.";
  }
  $("eol-text").textContent = oem
    ? "Showing fade-curve RUL to 80% of rated capacity (OEM warranty line). The ONNX model itself is trained to the NASA 70% stop."
    : "ONNX RUL to 70% of rated capacity (NASA PCoE official end-of-life). Toggle OEM to estimate 80% from the measured fade curve.";
}

async function refreshTrajectory() {
  if (!state.battery) return;
  const body = await api("/workspace/trajectory", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ battery: state.battery }),
  });
  state.trajectory = body.points || [];
  renderSoh(state.trajectory);
}

async function refreshSim() {
  if (!state.battery) return;
  const ambient = Number($("temp-slider").value);
  const crate = Number($("crate-slider").value);
  $("temp-value").textContent = String(ambient);
  $("crate-value").textContent = crate.toFixed(1);
  const sim = await api("/simulate/stress", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      battery: state.battery,
      ambient_temperature_c: ambient,
      discharge_c_rate: crate,
      current_cycle: selectedCycleIndex(),
    }),
  });
  $("af-text").textContent =
    `AF = ${sim.accelerationFactor.toFixed(2)}  (temperature ${sim.temperatureAcceleration.toFixed(2)} × C-rate ${sim.cRateAcceleration.toFixed(2)})`;
  const extra = sim.stressedExtrapolated ? " (extrapolated past the measured window)." : ".";
  $("rul-compare").textContent =
    `From cycle ${sim.currentCycle}: baseline RUL ${sim.baselineRulCycles} cycles → ` +
    `stressed RUL ${sim.stressedRulCycles} cycles ` +
    `(${sim.ambientTemperatureC.toFixed(0)} °C, ${sim.dischargeCRate.toFixed(2)} C). ` +
    `EOL cycle ${sim.baselineEolCycle} → ${sim.stressedEolCycle}${extra}`;
  renderStress(sim);
  renderFade(sim.stressed);
}

async function afterLoad() {
  await Promise.all([refreshForecast(), refreshTrajectory(), refreshSim()]);
}

async function loadDemo(id) {
  setStatus(`Loading ${id}…`);
  const payload = await api(`/demo/${id}`);
  applyBattery(payload.battery, payload.summary, `Loaded demo ${id}`);
  await afterLoad();
}

async function loadFile(file) {
  setStatus(`Opening ${file.name}…`);
  const lower = file.name.toLowerCase();
  if (lower.endsWith(".json")) {
    const record = JSON.parse(await file.text());
    const payload = await api("/workspace/forecast", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ battery: record }),
    });
    const summary = {
      batteryId: record.batteryId,
      source: record.source || "json",
      nCycles: dischargesOf(record).length,
      ratedCapacityAh: record.ratedCapacityAh,
      eolCapacityFraction: record.eolCapacityFraction,
      eolCapacityAh: record.ratedCapacityAh * record.eolCapacityFraction,
      firstCapacityAh: firstCap(record),
      lastCapacityAh: lastCap(record),
      cycleMin: minCycle(record),
      cycleMax: maxCycle(record),
      defaultCycle: defaultCycle(record),
    };
    applyBattery(record, summary, `Loaded ${file.name}`);
    await afterLoad();
    return payload;
  }
  const form = new FormData();
  form.append("file", file, file.name);
  const record = await api("/parse/calce", { method: "POST", body: form });
  const payload = await api(`/demo/calce`).catch(() => null);
  const summary = {
    batteryId: record.batteryId,
    source: record.source || "calce",
    nCycles: dischargesOf(record).length,
    ratedCapacityAh: record.ratedCapacityAh,
    eolCapacityFraction: record.eolCapacityFraction,
    eolCapacityAh: record.ratedCapacityAh * record.eolCapacityFraction,
    firstCapacityAh: firstCap(record),
    lastCapacityAh: lastCap(record),
    cycleMin: minCycle(record),
    cycleMax: maxCycle(record),
    defaultCycle: defaultCycle(record),
  };
  applyBattery(record, summary, `Loaded ${file.name}`);
  await afterLoad();
  return payload;
}

function dischargesOf(record) {
  return (record.cycles || []).filter((c) => String(c.type || "").toLowerCase() === "discharge");
}
function firstCap(record) {
  const caps = dischargesOf(record).map((c) => c.capacityAh).filter((c) => c != null);
  return caps[0];
}
function lastCap(record) {
  const caps = dischargesOf(record).map((c) => c.capacityAh).filter((c) => c != null);
  return caps.at(-1);
}
function minCycle(record) {
  return dischargesOf(record)[0]?.cycleIndex ?? 1;
}
function maxCycle(record) {
  return dischargesOf(record).at(-1)?.cycleIndex ?? 1;
}
function defaultCycle(record) {
  const traced = dischargesOf(record).filter(hasTrace);
  return traced.at(-1)?.cycleIndex ?? maxCycle(record);
}

function showPage(name) {
  document.querySelectorAll(".page").forEach((el) => el.classList.add("hidden"));
  document.querySelectorAll(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.page === name));
  $(`page-${name}`).classList.remove("hidden");
}

async function boot() {
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => showPage(btn.dataset.page));
  });
  $("btn-demo").addEventListener("click", async () => {
    try {
      await loadDemo("B0005");
    } catch (err) {
      showError(err.message);
    }
  });
  $("btn-calce").addEventListener("click", async () => {
    try {
      await loadDemo("calce");
    } catch (err) {
      showError(err.message);
    }
  });
  $("btn-open").addEventListener("click", () => $("file-input").click());
  $("file-input").addEventListener("change", async (ev) => {
    const file = ev.target.files?.[0];
    if (!file) return;
    try {
      await loadFile(file);
    } catch (err) {
      showError(err.message);
    }
  });
  $("cycle-slider").addEventListener("input", () => {
    refreshCycleUi();
  });
  $("cycle-slider").addEventListener("change", async () => {
    try {
      await Promise.all([refreshForecast(), refreshSim()]);
    } catch (err) {
      showError(err.message);
    }
  });
  $("oem-toggle").addEventListener("change", () => {
    if (state.forecast) refreshForecast().catch((err) => showError(err.message));
  });
  $("btn-refresh").addEventListener("click", async () => {
    try {
      await Promise.all([refreshForecast(), refreshTrajectory()]);
    } catch (err) {
      showError(err.message);
    }
  });
  const onStress = () => refreshSim().catch((err) => showError(err.message));
  $("temp-slider").addEventListener("input", () => {
    $("temp-value").textContent = $("temp-slider").value;
  });
  $("crate-slider").addEventListener("input", () => {
    $("crate-value").textContent = Number($("crate-slider").value).toFixed(1);
  });
  $("temp-slider").addEventListener("change", onStress);
  $("crate-slider").addEventListener("change", onStress);
  $("btn-reset").addEventListener("click", async () => {
    $("temp-slider").value = "24";
    $("crate-slider").value = "1.0";
    try {
      await refreshSim();
    } catch (err) {
      showError(err.message);
    }
  });

  try {
    const health = await api("/health");
    $("sidecar-status").textContent = health.models?.soh && health.models?.rul ? "ONNX ready" : "Models missing";
    if (!(health.models?.soh && health.models?.rul)) $("sidecar-status").classList.add("bad");
    const metrics = await api("/metrics");
    const hold = metrics?.rul?.gbr?.holdout;
    if (hold) {
      $("metrics-text").textContent =
        `Held-out B0018 (GBR ONNX): RUL RMSE ${Number(hold.rmse).toFixed(1)} cycles, ` +
        `MAE ${Number(hold.mae).toFixed(1)}, R² ${Number(hold.r2).toFixed(2)}. ` +
        "SoH GBR RMSE 0.0067 (fraction). See README for leave-one-battery-out and noise robustness.";
    }
  } catch (err) {
    $("sidecar-status").textContent = "Sidecar down";
    $("sidecar-status").classList.add("bad");
    showError(err.message);
  }
}

boot();
