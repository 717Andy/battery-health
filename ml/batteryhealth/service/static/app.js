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
  copy: {},
};

const $ = (id) => document.getElementById(id);

function discharges() {
  return (state.battery?.cycles || []).filter((c) => String(c.type || "").toLowerCase() === "discharge");
}

function cycleByIndex(index) {
  const list = discharges();
  return list.find((c) => Number(c.cycleIndex) === Number(index)) || list[0] || null;
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
  $("footer-status").textContent = text;
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

function fadePoints() {
  return discharges()
    .filter((c) => c.capacityAh != null)
    .map((c) => ({ x: c.cycleIndex, y: c.capacityAh }));
}

function renderFade(stressed) {
  const datasets = [{ label: "Measured capacity", data: fadePoints(), borderColor: TEAL }];
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
  const list = $("cycle-list");
  return Number(list.value || state.summary?.defaultCycle || 1);
}

function refreshCycleUi() {
  const cycle = cycleByIndex(selectedCycleIndex());
  if (!cycle) {
    $("cycle-caption").textContent = "Select a discharge cycle with a sensor trace.";
    renderSensors(null);
    return;
  }
  const cap = cycle.capacityAh != null ? `${Number(cycle.capacityAh).toFixed(3)} Ah` : "no capacity";
  $("cycle-caption").textContent = hasTrace(cycle)
    ? `Cycle ${cycle.cycleIndex} · ${cycle.type} · ${cap}`
    : `Cycle ${cycle.cycleIndex} has fade data only.`;
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
  $("forecast-empty").textContent = "";
  $("sim-empty").textContent = "";
  $("intake-text").textContent = (summary.intakeLines || []).join("\n");
  $("intake-card").classList.remove("hidden");
  setStatus(status);
  showError("");

  const list = $("cycle-list");
  list.innerHTML = "";
  (summary.dischargeRows || []).forEach((row) => {
    const opt = document.createElement("option");
    opt.value = String(row.cycleIndex);
    opt.textContent = row.label;
    list.appendChild(opt);
  });
  list.value = String(summary.defaultCycle);
  list.disabled = false;
  $("rated-ah").value = Number(summary.ratedCapacityAh).toFixed(2);
  $("rated-ah").disabled = false;
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
  $("soh-text").textContent = `${forecast.predictedSohPercent.toFixed(1)}%`;
  $("rul70-text").textContent = `${Math.round(forecast.predictedRulCycles)} cycles`;
  $("rul70-fade").textContent = `${Math.round(forecast.fadeRulTo70Cycles)} cycles on the fade curve`;
  $("rul80-text").textContent = `${Math.round(forecast.fadeRulTo80Cycles)} cycles`;
  $("forecast-headline").textContent = `${forecast.batteryId} cycle ${forecast.cycleIndex}`;
  if (forecast.observedSoh != null) {
    const err = Math.abs(forecast.predictedSoh - forecast.observedSoh) * 100;
    $("observed-text").textContent =
      `Measured SoH ${(forecast.observedSoh * 100).toFixed(1)}% of the nameplate  ·  |error| vs model ${err.toFixed(2)} points`;
  } else {
    $("observed-text").textContent =
      "No coulomb-counted capacity on this cycle — SoH is inferred from the V/I/T curve.";
  }
  $("feature-shift").textContent = forecast.featureShift || "";
  $("warning-text").textContent = forecast.warnings || "";
  $("applicability").textContent = forecast.applicability || state.copy.applicability || "";
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
  $("ea-band").textContent = sim.eaBand || "";
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

function dischargesOf(record) {
  return (record.cycles || []).filter((c) => String(c.type || "").toLowerCase() === "discharge");
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
    applyBattery(record, await summarizeLocal(record), `Loaded ${file.name}`);
    await afterLoad();
    return payload;
  }
  const form = new FormData();
  form.append("file", file, file.name);
  const record = await api("/parse/calce", { method: "POST", body: form });
  applyBattery(record, await summarizeLocal(record), `Loaded ${file.name}`);
  await afterLoad();
  return record;
}

async function summarizeLocal(record) {
  const demo = await api("/demo/tiny").catch(() => null);
  const discharges = dischargesOf(record);
  const caps = discharges.map((c) => c.capacityAh).filter((c) => c != null);
  const traced = discharges.filter(hasTrace);
  return {
    batteryId: record.batteryId,
    source: record.source || "file",
    nCycles: discharges.length,
    ratedCapacityAh: record.ratedCapacityAh,
    eolCapacityFraction: record.eolCapacityFraction,
    eolCapacityAh: record.ratedCapacityAh * record.eolCapacityFraction,
    firstCapacityAh: caps[0],
    lastCapacityAh: caps.at(-1),
    defaultCycle: traced.at(-1)?.cycleIndex ?? discharges.at(-1)?.cycleIndex ?? 1,
    intakeLines: demo?.summary?.intakeLines,
    dischargeRows: discharges.map((c) => ({
      cycleIndex: c.cycleIndex,
      label: `Cycle ${c.cycleIndex} · ${c.capacityAh != null ? Number(c.capacityAh).toFixed(3) + " Ah" : "no capacity"} · ${hasTrace(c) ? "trace" : "fade only"}`,
      hasTrace: hasTrace(c),
    })),
  };
}

function downloadText(name, text, mime) {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function exportReport() {
  if (!state.battery) {
    showError("Load a cell before exporting.");
    return;
  }
  setStatus("Building CSV and JSON…");
  const report = await api("/workspace/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      battery: state.battery,
      cycle_index: selectedCycleIndex(),
      ambient_temperature_c: Number($("temp-slider").value),
      discharge_c_rate: Number($("crate-slider").value),
    }),
  });
  $("export-preview").classList.remove("hidden");
  $("export-status").textContent = `Wrote ${report.csvName} and ${report.jsonName}.`;
  $("export-csv").textContent = report.previewCsv;
  $("export-json").textContent = report.previewJson;
  downloadText(report.csvName, report.csv, "text/csv");
  downloadText(report.jsonName, JSON.stringify(report.json, null, 2), "application/json");
  setStatus(`Wrote ${report.csvName} and ${report.jsonName}.`);
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
  const loadB0005 = async () => {
    try {
      await loadDemo("B0005");
    } catch (err) {
      showError(err.message);
    }
  };
  $("btn-demo").addEventListener("click", loadB0005);
  $("btn-demo-forecast").addEventListener("click", loadB0005);
  $("btn-demo-sim").addEventListener("click", loadB0005);
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
  $("cycle-list").addEventListener("change", async () => {
    refreshCycleUi();
    try {
      await Promise.all([refreshForecast(), refreshSim()]);
    } catch (err) {
      showError(err.message);
    }
  });
  $("rated-ah").addEventListener("change", async () => {
    if (!state.battery) return;
    state.battery.ratedCapacityAh = Number($("rated-ah").value);
    state.battery.ratedCapacityAssumed = false;
    try {
      const demo = await api("/demo/B0005");
      // Rebuild intake from current battery via a local forecast refresh.
      await afterLoad();
      $("intake-text").textContent =
        `Nameplate ${Number($("rated-ah").value).toFixed(2)} Ah.\n` +
        `Lab stop is 70% (${(Number($("rated-ah").value) * 0.7).toFixed(2)} Ah). ` +
        `Warranty line is 80% (${(Number($("rated-ah").value) * 0.8).toFixed(2)} Ah).`;
      void demo;
    } catch (err) {
      showError(err.message);
    }
  });
  $("btn-refresh").addEventListener("click", async () => {
    try {
      await Promise.all([refreshForecast(), refreshTrajectory()]);
    } catch (err) {
      showError(err.message);
    }
  });
  $("btn-export").addEventListener("click", async () => {
    try {
      await exportReport();
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
    const copy = await api("/workspace/copy");
    state.copy = copy;
    $("metrics-text").textContent = copy.metricsText || "";
    $("typical-error").textContent = copy.typicalError || "";
    $("ea-band").textContent = copy.eaBand24C1C || "";
  } catch (err) {
    $("sidecar-status").textContent = "Sidecar down";
    $("sidecar-status").classList.add("bad");
    showError(err.message);
  }
}

boot();
