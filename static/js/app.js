const state = {
  split: "train",
  sensors: [],
  activeSensor: null,
  markers: {},
  charts: {},
};

const severityColor = (pm25) => {
  if (pm25 < 25) return "#3FC1C9";
  if (pm25 < 50) return "#6FCB9F";
  if (pm25 < 75) return "#F5C24C";
  if (pm25 < 100) return "#F5A524";
  return "#EF5B5B";
};

// ---------- Map ----------
const map = L.map("map", { zoomControl: true, attributionControl: false })
  .setView([3.4516, -76.5273], 14);

L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
  maxZoom: 19,
}).addTo(map);

function renderMarkers() {
  state.sensors.forEach((s) => {
    const color = severityColor(s.last_pm25);
    const icon = L.divIcon({
      className: "",
      html: `<div style="
        width:16px;height:16px;border-radius:50%;
        background:${color};
        box-shadow:0 0 0 4px ${color}33, 0 0 14px ${color}aa;
        border:2px solid #0B1220;"></div>`,
      iconSize: [16, 16],
      iconAnchor: [8, 8],
    });

    const marker = L.marker([s.lat, s.long], { icon }).addTo(map);
    marker.bindPopup(
      `<strong>${s.label}</strong><br/>PM2.5: ${s.last_pm25.toFixed(1)} μg/m³<br/>${s.last_fecha}`
    );
    marker.on("click", () => selectSensor(s.id));
    state.markers[s.id] = marker;
  });
}

// ---------- Sensor tabs ----------
function renderSensorTabs() {
  const container = document.getElementById("sensorTabs");
  container.innerHTML = "";
  state.sensors.forEach((s) => {
    const btn = document.createElement("button");
    btn.className = "sensor-tab" + (s.id === state.activeSensor ? " active" : "");
    btn.textContent = s.label;
    btn.addEventListener("click", () => selectSensor(s.id));
    container.appendChild(btn);
  });
}

function selectSensor(id) {
  state.activeSensor = id;
  renderSensorTabs();
  Object.entries(state.markers).forEach(([sid, m]) => {
    m.getElement()?.classList.toggle("marker-active", sid === id);
  });
  loadSensorData();
}

// ---------- Data loading ----------
async function loadSensors() {
  const res = await fetch("/api/sensors");
  state.sensors = await res.json();
  document.getElementById("sensorCount").textContent = `${state.sensors.length} activos`;
  renderMarkers();
  renderSensorTabs();
  if (state.sensors.length) selectSensor(state.sensors[0].id);
}

async function loadSensorData() {
  if (!state.activeSensor) return;
  const res = await fetch(`/api/data/${state.activeSensor}/${state.split}`);
  const payload = await res.json();
  updateStats(payload);
  updateCharts(payload);
}

function updateStats(payload) {
  const last = payload.records[payload.records.length - 1];
  if (!last) return;
  document.getElementById("statPm25").textContent = `${last.pm25.toFixed(1)} μg/m³`;
  document.getElementById("statTemp").textContent = `${last.temperatura.toFixed(1)} °C`;
  document.getElementById("statHum").textContent = `${last.humedad.toFixed(1)} %`;
  document.getElementById("statCount").textContent = payload.count;
  document.getElementById("pm25Hint").textContent = payload.has_prediction
    ? "· real vs. predicho"
    : "· datos reales (train)";
}

// ---------- Charts ----------
const chartDefaults = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: "index", intersect: false },
  plugins: {
    legend: { labels: { color: "#8C9BB5", font: { family: "IBM Plex Mono", size: 11 } } },
  },
  scales: {
    x: { ticks: { color: "#8C9BB5", maxTicksLimit: 8 }, grid: { color: "#22304A" } },
    y: { ticks: { color: "#8C9BB5" }, grid: { color: "#22304A" } },
  },
};

function makeLineChart(ctx, labels, datasets) {
  return new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      ...chartDefaults,
      elements: { point: { radius: 0 }, line: { tension: 0.3, borderWidth: 2 } },
    },
  });
}

function updateCharts(payload) {
  const labels = payload.records.map((r) => r.fecha.slice(5, 16));
  const pm25 = payload.records.map((r) => r.pm25);
  const temp = payload.records.map((r) => r.temperatura);
  const hum = payload.records.map((r) => r.humedad);

  // PM2.5 chart (real + predicho si aplica)
  const pm25Datasets = [
    { label: "PM2.5 real", data: pm25, borderColor: "#3FC1C9", backgroundColor: "#3FC1C933" },
  ];
  if (payload.has_prediction) {
    const pred = payload.records.map((r) => r.pm25_pred);
    pm25Datasets.push({
      label: "PM2.5 predicho",
      data: pred,
      borderColor: "#EF5B5B",
      backgroundColor: "#EF5B5B33",
      borderDash: [5, 4],
    });
  }

  destroyChart("chartPm25");
  state.charts.chartPm25 = makeLineChart(document.getElementById("chartPm25"), labels, pm25Datasets);

  destroyChart("chartTemp");
  state.charts.chartTemp = makeLineChart(document.getElementById("chartTemp"), labels, [
    { label: "Temperatura", data: temp, borderColor: "#F5C24C", backgroundColor: "#F5C24C33" },
  ]);

  destroyChart("chartHum");
  state.charts.chartHum = makeLineChart(document.getElementById("chartHum"), labels, [
    { label: "Humedad", data: hum, borderColor: "#6FCB9F", backgroundColor: "#6FCB9F33" },
  ]);

  destroyChart("chartScatter");
  state.charts.chartScatter = new Chart(document.getElementById("chartScatter"), {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "PM2.5 vs Humedad",
          data: payload.records.map((r) => ({ x: r.humedad, y: r.pm25 })),
          backgroundColor: "#3FC1C9aa",
        },
      ],
    },
    options: {
      ...chartDefaults,
      scales: {
        x: { title: { display: true, text: "Humedad (%)", color: "#8C9BB5" }, ticks: { color: "#8C9BB5" }, grid: { color: "#22304A" } },
        y: { title: { display: true, text: "PM2.5 (μg/m³)", color: "#8C9BB5" }, ticks: { color: "#8C9BB5" }, grid: { color: "#22304A" } },
      },
    },
  });
}

function destroyChart(key) {
  if (state.charts[key]) {
    state.charts[key].destroy();
    delete state.charts[key];
  }
}

// ---------- Toggle Train/Test ----------
const toggleEl = document.querySelector(".split-toggle");
document.querySelectorAll(".split-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".split-btn").forEach((b) => {
      b.classList.remove("active");
      b.setAttribute("aria-selected", "false");
    });
    btn.classList.add("active");
    btn.setAttribute("aria-selected", "true");
    state.split = btn.dataset.split;
    toggleEl.dataset.state = state.split;
    loadSensorData();
  });
});

// ---------- Init ----------
loadSensors();
