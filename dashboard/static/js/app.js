// =====================================================
// TABS
// =====================================================

const tabButtons = document.querySelectorAll(".tab-btn");
const tabPanels = document.querySelectorAll(".tab-panel");

tabButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    const target = btn.dataset.tab;

    tabButtons.forEach((b) => b.classList.remove("active"));
    tabPanels.forEach((p) => p.classList.remove("active"));

    btn.classList.add("active");
    document.getElementById(`tab-${target}`).classList.add("active");
  });
});

// =====================================================
// ESTADO POR CADA VISTA (TRAIN / TEST)
// =====================================================

const datasetViews = document.querySelectorAll(".dataset-view");

datasetViews.forEach((panel) => initDatasetView(panel));

function initDatasetView(panel) {
  const split = panel.dataset.split; // "train" | "test"

  const state = {
    sensorId: Object.keys(SENSORS)[0] || null,
    map: null,
    marker: null,
    charts: {},
  };

  const sensorSelector = panel.querySelector(".sensor-selector");
  const statusLine = panel.querySelector(".status-line");
  const applyBtn = panel.querySelector(".apply-filters");
  const clearBtn = panel.querySelector(".clear-filters");
  const startInput = panel.querySelector(".filter-start");
  const endInput = panel.querySelector(".filter-end");

  // --- Botones de sensor con nombre real ---
  Object.entries(SENSORS).forEach(([sensorId, label]) => {
    const btn = document.createElement("button");
    btn.className = "sensor-btn" + (sensorId === state.sensorId ? " active" : "");
    btn.textContent = label;
    btn.dataset.sensorId = sensorId;

    btn.addEventListener("click", () => {
      state.sensorId = sensorId;
      sensorSelector
        .querySelectorAll(".sensor-btn")
        .forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      loadData(panel, state, split);
    });

    sensorSelector.appendChild(btn);
  });

  applyBtn.addEventListener("click", () => loadData(panel, state, split));

  clearBtn.addEventListener("click", () => {
    startInput.value = "";
    endInput.value = "";
    loadData(panel, state, split);
  });

  // --- Mapa base ---
  const mapEl = panel.querySelector(".leaflet-map");
  state.map = L.map(mapEl).setView([3.4516, -76.532], 12);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap",
  }).addTo(state.map);

  // Carga inicial
  if (state.sensorId) {
    loadData(panel, state, split);
  } else {
    statusLine.textContent = "No hay sensores configurados.";
  }
}

// =====================================================
// CARGA DE DATOS DESDE LA API
// =====================================================

async function loadData(panel, state, split) {
  const statusLine = panel.querySelector(".status-line");
  const startInput = panel.querySelector(".filter-start");
  const endInput = panel.querySelector(".filter-end");

  statusLine.classList.remove("error");
  statusLine.textContent = "Cargando datos...";

  const params = new URLSearchParams();
  if (startInput.value) params.set("start", startInput.value.replace("T", " "));
  if (endInput.value) params.set("end", endInput.value.replace("T", " "));

  const url = `/api/data/${state.sensorId}/${split}?${params.toString()}`;

  try {
    const res = await fetch(url);

    if (!res.ok) {
      statusLine.classList.add("error");
      statusLine.textContent =
        "No se encontraron datos para este sensor / rango de fechas.";
      clearCharts(state);
      return;
    }

    const data = await res.json();

    statusLine.textContent = `${data.count} registros — ${data.sensor_label} (${data.split})`;

    renderCharts(panel, state, data);
    renderMap(state, data);
  } catch (err) {
    statusLine.classList.add("error");
    statusLine.textContent = "Error consultando la API.";
    console.error(err);
  }
}

// =====================================================
// MAPA
// =====================================================

function renderMap(state, data) {
  const withCoords = data.records.filter(
    (r) => r.lat !== null && r.long !== null && r.lat !== undefined
  );

  if (withCoords.length === 0) return;

  const last = withCoords[withCoords.length - 1];

  if (state.marker) {
    state.map.removeLayer(state.marker);
  }

  state.marker = L.marker([last.lat, last.long]).addTo(state.map);
  state.marker.bindPopup(
    `${data.sensor_label}<br>PM2.5: ${last.pm25 ?? "N/D"}<br>${last.fecha ?? ""}`
  );

  state.map.setView([last.lat, last.long], 14);
}

// =====================================================
// GRAFICAS
// =====================================================

function clearCharts(state) {
  Object.values(state.charts).forEach((chart) => chart && chart.destroy());
  state.charts = {};
}

function renderCharts(panel, state, data) {
  clearCharts(state);

  const labels = data.records.map((r) => r.fecha);
  const pm25 = data.records.map((r) => r.pm25);
  const pm25Pred = data.records.map((r) => r.pm25_pred ?? null);
  const temperatura = data.records.map((r) => r.temperatura);
  const humedad = data.records.map((r) => r.humedad);

  const pm25Canvas = panel.querySelector(".chart-pm25");
  const tempCanvas = panel.querySelector(".chart-temperatura");
  const humCanvas = panel.querySelector(".chart-humedad");

  const pm25Datasets = [
    {
      label: "PM2.5 real",
      data: pm25,
      borderColor: "#3fb37f",
      backgroundColor: "rgba(63,179,127,0.15)",
      tension: 0.25,
      pointRadius: 0,
    },
  ];

  if (data.has_prediction) {
    pm25Datasets.push({
      label: "PM2.5 predicho",
      data: pm25Pred,
      borderColor: "#e0716a",
      backgroundColor: "rgba(224,113,106,0.15)",
      tension: 0.25,
      pointRadius: 0,
      borderDash: [5, 4],
    });
  }

  state.charts.pm25 = new Chart(pm25Canvas, {
    type: "line",
    data: { labels, datasets: pm25Datasets },
    options: chartOptions(),
  });

  state.charts.temperatura = new Chart(tempCanvas, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Temperatura (°C)",
          data: temperatura,
          borderColor: "#e8b04b",
          backgroundColor: "rgba(232,176,75,0.15)",
          tension: 0.25,
          pointRadius: 0,
        },
      ],
    },
    options: chartOptions(),
  });

  state.charts.humedad = new Chart(humCanvas, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Humedad (%)",
          data: humedad,
          borderColor: "#4b9be8",
          backgroundColor: "rgba(75,155,232,0.15)",
          tension: 0.25,
          pointRadius: 0,
        },
      ],
    },
    options: chartOptions(),
  });
}

function chartOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    scales: {
      x: {
        ticks: { color: "#9aa1ad", maxTicksLimit: 8 },
        grid: { color: "#2a2f3a" },
      },
      y: {
        ticks: { color: "#9aa1ad" },
        grid: { color: "#2a2f3a" },
      },
    },
    plugins: {
      legend: { labels: { color: "#e7e9ee" } },
    },
  };
}
