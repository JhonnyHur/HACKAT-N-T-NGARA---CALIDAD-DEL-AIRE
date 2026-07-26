// =====================================================
// VISTA POR DEFECTO (CALI) Y VALIDACION DE COORDENADAS
// =====================================================

const CALI_CENTER = [3.4516, -76.532];
const CALI_DEFAULT_ZOOM = 12;

// Caja amplia alrededor de Cali / Valle del Cauca: solo coordenadas
// dentro de este rango se usan para centrar/ajustar el mapa
// automaticamente. Evita que una coordenada mal cargada (ej. desde
// un CSV de train/test) mande la vista a otra parte del mapa.
const CALI_BOUNDS = L.latLngBounds([3.10, -76.90], [3.75, -76.20]);

function hasValidCoords(sensor) {
  const lat = Number(sensor.lat);
  const long = Number(sensor.long);

  return (
    Number.isFinite(lat) &&
    Number.isFinite(long) &&
    !(lat === 0 && long === 0)
  );
}

// =====================================================
// ESCALA DE CALIDAD DEL AIRE (basada en PM2.5, µg/m³)
// =====================================================

const AQI_LEVELS = [
  { max: 12, label: "Bien", color: "#0e8f5f" },
  { max: 35.4, label: "Moderado", color: "#e8c33e" },
  { max: 55.4, label: "Nocivo para grupos sensibles", color: "#e08a3c" },
  { max: 150.4, label: "Poco saludable", color: "#c0392b" },
  { max: 250.4, label: "Muy poco saludable", color: "#7d3c98" },
  { max: Infinity, label: "Peligroso", color: "#5c0a1a" },
];

function getAQICategory(pm25) {
  const value = Number(pm25);

  if (pm25 === null || pm25 === undefined || Number.isNaN(value)) {
    return { label: "Sin dato", color: "#5a6070" };
  }

  return (
    AQI_LEVELS.find((level) => value <= level.max) ||
    AQI_LEVELS[AQI_LEVELS.length - 1]
  );
}

function addAQILegend(map) {
  const legend = L.control({ position: "bottomright" });

  legend.onAdd = function () {
    const div = L.DomUtil.create("div", "aqi-legend");

    div.innerHTML =
      "<h4>Calidad del aire (PM2.5)</h4>" +
      AQI_LEVELS.map(
        (level) => `
          <div class="aqi-legend-item">
            <span class="aqi-swatch" style="background:${level.color}"></span>
            ${level.label}
          </div>
        `
      ).join("");

    return div;
  };

  legend.addTo(map);
}

// =====================================================
// TABS
// =====================================================

const tabButtons = document.querySelectorAll(".tab-btn");
const tabPanels = document.querySelectorAll(".tab-panel");

// Registro de instancias de mapa de Leaflet por panel: los mapas de
// las pestañas Train/Test se crean mientras esa pestaña esta oculta
// (display: none), asi que Leaflet mide el contenedor en 0x0 y el
// mapa se ve mal (solo un pedazo de tiles arriba a la izquierda).
// Por eso, al activar una pestaña, forzamos invalidateSize() sobre
// su mapa para que recalcule su tamaño real.
const panelMaps = new Map();

tabButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    const target = btn.dataset.tab;

    tabButtons.forEach((b) => b.classList.remove("active"));
    tabPanels.forEach((p) => p.classList.remove("active"));

    btn.classList.add("active");

    const activePanel = document.getElementById(`tab-${target}`);
    activePanel.classList.add("active");

    const map = panelMaps.get(activePanel);

    if (map) {
      // El cambio de "display: none" a "block" tarda un tick en
      // reflejarse en el layout, por eso el invalidateSize se
      // dispara en el siguiente frame en vez de inmediatamente.
      requestAnimationFrame(() => map.invalidateSize());
    }
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
    sensorMarkers: {},
    charts: {},
  };

  const sensorSelector = panel.querySelector(".sensor-selector");
  const statusLine = panel.querySelector(".status-line");
  const applyBtn = panel.querySelector(".apply-filters");
  const clearBtn = panel.querySelector(".clear-filters");
  const startInput = panel.querySelector(".filter-start");
  const endInput = panel.querySelector(".filter-end");

  function selectSensor(sensorId) {
    state.sensorId = sensorId;

    sensorSelector.querySelectorAll(".sensor-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.sensorId === sensorId);
    });

    highlightSensorMarker(state);
    loadData(panel, state, split);
  }

  // --- Botones de sensor con nombre real ---
  Object.entries(SENSORS).forEach(([sensorId, label]) => {
    const btn = document.createElement("button");
    btn.className = "sensor-btn" + (sensorId === state.sensorId ? " active" : "");
    btn.textContent = label;
    btn.dataset.sensorId = sensorId;

    btn.addEventListener("click", () => selectSensor(sensorId));

    sensorSelector.appendChild(btn);
  });

  applyBtn.addEventListener("click", () => loadData(panel, state, split));

  clearBtn.addEventListener("click", () => {
    startInput.value = "";
    endInput.value = "";
    loadData(panel, state, split);
  });

  // --- Mapa base, con todos los sensores y escala de calidad del aire ---
  const mapEl = panel.querySelector(".leaflet-map");
  state.map = L.map(mapEl, {
    center: CALI_CENTER,
    zoom: CALI_DEFAULT_ZOOM,
    minZoom: 5,
  });

  L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    {
      attribution: "&copy; OpenStreetMap &copy; CARTO",
      subdomains: "abcd",
      maxZoom: 19,
    }
  ).addTo(state.map);

  panelMaps.set(panel, state.map);

  // Si el panel ya esta visible al cargar la pagina, igual conviene
  // forzar el recalculo de tamaño una vez que el layout se asiente.
  requestAnimationFrame(() => state.map.invalidateSize());

  addAQILegend(state.map);
  loadSensorMarkers(state, panel, selectSensor);

  // Carga inicial
  if (state.sensorId) {
    loadData(panel, state, split);
  } else {
    statusLine.textContent = "No hay sensores configurados.";
  }
}

// =====================================================
// MARCADORES DE TODOS LOS SENSORES EN EL MAPA
// =====================================================

async function loadSensorMarkers(state, panel, onSensorClick) {
  const statusLine = panel.querySelector(".status-line");

  try {
    const res = await fetch("/api/sensors");

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const sensors = await res.json();

    const coords = [];
    let skippedCount = 0;

    sensors.forEach((sensor) => {
      if (!hasValidCoords(sensor)) {
        console.warn(
          `Sensor ${sensor.id}: coordenadas invalidas, no se dibuja`,
          sensor
        );
        skippedCount += 1;
        return;
      }

      const lat = Number(sensor.lat);
      const long = Number(sensor.long);
      const category = getAQICategory(sensor.last_pm25);

      const marker = L.circleMarker([lat, long], {
        radius: 9,
        color: "#0f1115",
        weight: 1,
        fillColor: category.color,
        fillOpacity: 0.9,
      }).addTo(state.map);

      marker.bindPopup(
        `<strong>${sensor.label}</strong><br>` +
          `PM2.5: ${sensor.last_pm25 ?? "N/D"} µg/m³ (${category.label})<br>` +
          `${sensor.last_fecha ?? ""}`
      );

      marker.on("click", () => onSensorClick(sensor.id));

      state.sensorMarkers[sensor.id] = marker;

      // Solo las coordenadas dentro del area esperada (Cali /
      // Valle del Cauca) se usan para reencuadrar el mapa
      // automaticamente. Una coordenada fuera de rango no mueve
      // la vista, pero el marcador igual se dibuja.
      if (CALI_BOUNDS.contains([lat, long])) {
        coords.push([lat, long]);
      }
    });

    highlightSensorMarker(state);

    if (coords.length > 0) {
      state.map.fitBounds(coords, { padding: [30, 30], maxZoom: 14 });
    } else {
      state.map.setView(CALI_CENTER, CALI_DEFAULT_ZOOM);
    }

    if (skippedCount > 0 && statusLine) {
      console.warn(
        `${skippedCount} sensor(es) sin coordenadas validas para el mapa`
      );
    }
  } catch (err) {
    console.error("No se pudieron cargar los sensores en el mapa", err);

    state.map.setView(CALI_CENTER, CALI_DEFAULT_ZOOM);

    if (statusLine) {
      statusLine.classList.add("error");
      statusLine.textContent =
        "No se pudo cargar el mapa de sensores (revisa /api/sensors).";
    }
  }
}

function highlightSensorMarker(state) {
  Object.entries(state.sensorMarkers).forEach(([sensorId, marker]) => {
    const isActive = sensorId === state.sensorId;

    marker.setStyle({
      radius: isActive ? 13 : 9,
      weight: isActive ? 3 : 1,
      color: isActive ? "#e7e9ee" : "#0f1115",
    });

    if (isActive) {
      marker.bringToFront();
    }
  });
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
      resetAQISummary(panel);
      return;
    }

    const data = await res.json();

    statusLine.textContent = `${data.count} registros — ${data.sensor_label} (${data.split})`;

    renderCharts(panel, state, data);
  } catch (err) {
    statusLine.classList.add("error");
    statusLine.textContent = "Error consultando la API.";
    console.error(err);
  }
}

// =====================================================
// RANGO DE FECHAS PARA LOS TITULOS DE LAS GRAFICAS
// =====================================================

const MESES_ES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

/**
 * A partir de las fechas (strings) que llegan en `labels`, arma un
 * texto tipo "desde enero 2026 hasta julio 2026" (o "en julio 2026"
 * si el primer y el ultimo dato caen en el mismo mes/año) para usarlo
 * en los titulos de las graficas. Si no hay fechas validas, devuelve
 * una cadena vacia y el titulo simplemente no incluye el rango.
 */
function formatDateRangeES(labels) {
  const validDates = labels
    .map((label) => new Date(label))
    .filter((date) => !Number.isNaN(date.getTime()));

  if (validDates.length === 0) {
    return "";
  }

  const start = validDates[0];
  const end = validDates[validDates.length - 1];

  const startText = `${MESES_ES[start.getMonth()]} ${start.getFullYear()}`;
  const endText = `${MESES_ES[end.getMonth()]} ${end.getFullYear()}`;

  if (
    start.getFullYear() === end.getFullYear() &&
    start.getMonth() === end.getMonth()
  ) {
    return `en ${startText}`;
  }

  return `desde ${startText} hasta ${endText}`;
}

/**
 * Actualiza el texto del <h3> que precede a un canvas dentro de su
 * .chart-box, anteponiendo el titulo base al rango de fechas
 * calculado (si lo hay).
 */
function setChartTitle(canvas, baseTitle, rangeText) {
  const heading = canvas.closest(".chart-box")?.querySelector("h3");

  if (!heading) {
    return;
  }

  heading.textContent = rangeText ? `${baseTitle}, ${rangeText}` : baseTitle;
}

// =====================================================
// TARJETA DE RESUMEN DE CALIDAD DEL AIRE (AQI)
// =====================================================

/**
 * Cuenta cuantos registros caen en cada categoria de AQI_LEVELS, y de
 * paso calcula el promedio de PM2.5 y el pico mas alto (con su
 * fecha), a partir de la lista de registros ya cargados (los mismos
 * que se usan para dibujar las graficas), respetando el sensor y el
 * filtro de fechas activos.
 */
function buildAQISummary(records, pm25Field) {
  const counts = AQI_LEVELS.map(() => 0);

  let sum = 0;
  let validCount = 0;
  let maxValue = -Infinity;
  let maxRecord = null;

  records.forEach((record) => {
    const raw = record[pm25Field];
    const value = Number(raw);

    if (raw === null || raw === undefined || Number.isNaN(value)) {
      return;
    }

    const levelIndex = AQI_LEVELS.findIndex((level) => value <= level.max);

    counts[levelIndex === -1 ? AQI_LEVELS.length - 1 : levelIndex] += 1;

    sum += value;
    validCount += 1;

    if (value > maxValue) {
      maxValue = value;
      maxRecord = record;
    }
  });

  return {
    counts,
    total: validCount,
    average: validCount > 0 ? sum / validCount : null,
    maxValue: validCount > 0 ? maxValue : null,
    maxRecord,
  };
}

function resetAQISummary(panel) {
  const card = panel.querySelector(".aqi-summary-card");

  if (!card) {
    return;
  }

  card.querySelector(".aqi-summary-count").textContent = "";
  card.querySelector(".aqi-summary-bars").innerHTML =
    '<p class="aqi-summary-empty">Sin datos de PM2.5 en este rango.</p>';
  card.querySelector(".aqi-summary-extra").innerHTML = "";
}

function renderAQISummary(panel, records, pm25Field) {
  const card = panel.querySelector(".aqi-summary-card");

  if (!card) {
    return;
  }

  const summary = buildAQISummary(records, pm25Field);

  if (summary.total === 0) {
    resetAQISummary(panel);
    return;
  }

  const countEl = card.querySelector(".aqi-summary-count");
  const barsEl = card.querySelector(".aqi-summary-bars");
  const extraEl = card.querySelector(".aqi-summary-extra");

  countEl.textContent = `${summary.total} registro(s) con PM2.5`;

  barsEl.innerHTML = AQI_LEVELS.map((level, i) => {
    const count = summary.counts[i];

    if (count === 0) {
      return "";
    }

    const pct = ((count / summary.total) * 100).toFixed(1);

    return `
      <div class="aqi-summary-row">
        <span class="aqi-swatch" style="background:${level.color}"></span>
        <span class="aqi-summary-label">${level.label}</span>
        <div class="aqi-summary-track">
          <div class="aqi-summary-fill" style="width:${pct}%; background:${level.color}"></div>
        </div>
        <span class="aqi-summary-value">${count} (${pct}%)</span>
      </div>
    `;
  }).join("");

  let predominantIndex = 0;

  summary.counts.forEach((count, i) => {
    if (count > summary.counts[predominantIndex]) {
      predominantIndex = i;
    }
  });

  const predominantLevel = AQI_LEVELS[predominantIndex];

  const averageText =
    summary.average !== null ? `${summary.average.toFixed(1)} µg/m³` : "N/D";

  const maxText = summary.maxRecord
    ? `${summary.maxValue.toFixed(1)} µg/m³ — ${summary.maxRecord.fecha ?? "fecha desconocida"}`
    : "N/D";

  extraEl.innerHTML = `
    <div class="aqi-summary-stat">
      <span class="aqi-summary-stat-label">Promedio PM2.5</span>
      <span class="aqi-summary-stat-value">${averageText}</span>
    </div>
    <div class="aqi-summary-stat">
      <span class="aqi-summary-stat-label">Categoría predominante</span>
      <span class="aqi-summary-stat-value" style="color:${predominantLevel.color}">
        ${predominantLevel.label}
      </span>
    </div>
    <div class="aqi-summary-stat">
      <span class="aqi-summary-stat-label">Pico más alto</span>
      <span class="aqi-summary-stat-value">${maxText}</span>
    </div>
  `;
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

  renderAQISummary(panel, data.records, "pm25");

  const labels = data.records.map((r) => r.fecha);
  const pm25 = data.records.map((r) => r.pm25);
  const pm25Pred = data.records.map((r) => r.pm25_pred ?? null);
  const temperatura = data.records.map((r) => r.temperatura);
  const humedad = data.records.map((r) => r.humedad);

  const pm25Canvas = panel.querySelector(".chart-pm25");
  const tempCanvas = panel.querySelector(".chart-temperatura");
  const humCanvas = panel.querySelector(".chart-humedad");

  const rangeText = formatDateRangeES(labels);

  setChartTitle(
    pm25Canvas,
    data.has_prediction
      ? "PM2.5 real vs. predicción (μg/m³)"
      : "PM2.5 (μg/m³)",
    rangeText
  );
  setChartTitle(tempCanvas, "Temperatura (°C)", rangeText);
  setChartTitle(humCanvas, "Humedad (%)", rangeText);

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
      label: "PM2.5 predicción",
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

// =====================================================
// PESTAÑA PREDICCIONES (Gold — solo sensor 2FF6)
// =====================================================

const prediccionesPanel = document.querySelector(".prediction-view");

if (prediccionesPanel) {
  initPrediccionesView(prediccionesPanel);
}

function initPrediccionesView(panel) {
  const state = { charts: {} };

  const statusLine = panel.querySelector(".status-line");
  const applyBtn = panel.querySelector(".apply-filters");
  const clearBtn = panel.querySelector(".clear-filters");
  const startInput = panel.querySelector(".filter-start");
  const endInput = panel.querySelector(".filter-end");

  applyBtn.addEventListener("click", () => loadPredicciones(panel, state));

  clearBtn.addEventListener("click", () => {
    startInput.value = "";
    endInput.value = "";
    loadPredicciones(panel, state);
  });

  loadPredicciones(panel, state);
}

async function loadPredicciones(panel, state) {
  const statusLine = panel.querySelector(".status-line");
  const startInput = panel.querySelector(".filter-start");
  const endInput = panel.querySelector(".filter-end");

  statusLine.classList.remove("error");
  statusLine.textContent = "Cargando predicciones...";

  const params = new URLSearchParams();
  if (startInput.value) params.set("start", startInput.value.replace("T", " "));
  if (endInput.value) params.set("end", endInput.value.replace("T", " "));

  const url = `/api/predicciones?${params.toString()}`;

  try {
    const res = await fetch(url);
    const data = await res.json();

    if (data.status !== "ok" || !data.records || data.records.length === 0) {
      statusLine.classList.add("error");
      statusLine.textContent =
        data.message || "No hay predicciones disponibles.";
      clearPrediccionesCharts(state);
      resetAQISummary(panel);
      resetForecastCard(panel);
      return;
    }

    statusLine.textContent = `${data.count} registros — ${data.sensor_label} (predicción)`;

    renderPrediccionesCharts(panel, state, data);
  } catch (err) {
    statusLine.classList.add("error");
    statusLine.textContent = "Error consultando la API.";
    console.error(err);
  }
}

function clearPrediccionesCharts(state) {
  Object.values(state.charts).forEach((chart) => chart && chart.destroy());
  state.charts = {};
}

function renderPrediccionesCharts(panel, state, data) {
  clearPrediccionesCharts(state);

  renderAQISummary(panel, data.records, "pm25_real");
  renderForecastCard(panel, state, data.records);

  const labels = data.records.map((r) => r.fecha);
  const pm25Real = data.records.map((r) => r.pm25_real ?? null);
  const pm25Pred = data.records.map((r) => r.pm25_predicho);
  const temperatura = data.records.map((r) => r.temperatura);
  const humedad = data.records.map((r) => r.humedad);

  const pm25Canvas = panel.querySelector(".chart-pm25-pred");
  const tempCanvas = panel.querySelector(".chart-temperatura-pred");
  const humCanvas = panel.querySelector(".chart-humedad-pred");

  const rangeText = formatDateRangeES(labels);

  setChartTitle(pm25Canvas, "PM2.5 real vs. predicción (μg/m³)", rangeText);
  setChartTitle(tempCanvas, "Temperatura (°C)", rangeText);
  setChartTitle(humCanvas, "Humedad (%)", rangeText);

  state.charts.pm25 = new Chart(pm25Canvas, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "PM2.5 real",
          data: pm25Real,
          borderColor: "#3fb37f",
          backgroundColor: "rgba(63,179,127,0.15)",
          tension: 0.25,
          pointRadius: 0,
        },
        {
          label: "PM2.5 predicción",
          data: pm25Pred,
          borderColor: "#e0716a",
          backgroundColor: "rgba(224,113,106,0.15)",
          tension: 0.25,
          pointRadius: 0,
          borderDash: [5, 4],
        },
      ],
    },
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
// =====================================================
// TARJETA: PRONOSTICO PROXIMAS HORAS (registros de Gold con
// pm25_real nulo, ya que esas horas todavia no han pasado)
// =====================================================

/**
 * Del listado completo de gold.sensor_2ff6_predicciones, se queda
 * solo con las filas "futuras" (pm25_real nulo pero pm25_predicho
 * ya calculado), ordenadas de la hora mas cercana a la mas lejana.
 */
function getForecastRecords(records) {
  return records
    .filter((r) => {
      const isFuture = r.pm25_real === null || r.pm25_real === undefined;
      const hasPrediction =
        r.pm25_predicho !== null && r.pm25_predicho !== undefined;

      return isFuture && hasPrediction;
    })
    .sort((a, b) => String(a.fecha).localeCompare(String(b.fecha)));
}

function formatHourLabel(fecha) {
  if (!fecha) {
    return "";
  }

  // Se lee la hora:minuto directamente del string que ya viene de
  // Gold (columna "Fecha & Hora", en hora de Cali), sin pasar por
  // new Date(...): usar Date() aqui reinterpreta/convierte la hora
  // segun la zona horaria del navegador, y eso hace que se corra
  // (ej. si el navegador no esta en America/Bogota). Al leer los
  // digitos tal cual, se muestra exactamente la hora que guardo el
  // pipeline, sin conversion de por medio.
  const match = String(fecha).match(/(\d{2}):(\d{2})(?::\d{2})?/);

  if (match) {
    return `${match[1]}:${match[2]}`;
  }

  return String(fecha);
}

function resetForecastCard(panel) {
  const card = panel.querySelector(".forecast-card");

  if (!card) {
    return;
  }

  card.querySelector(".forecast-updated").textContent = "";
  card.querySelector(".forecast-chips").innerHTML = "";
  card.querySelector(".forecast-chart-box").style.display = "none";
  card.querySelector(".forecast-empty").hidden = false;
}

function renderForecastCard(panel, state, records) {
  const card = panel.querySelector(".forecast-card");

  if (!card) {
    return;
  }

  const chipsEl = card.querySelector(".forecast-chips");
  const updatedEl = card.querySelector(".forecast-updated");
  const emptyEl = card.querySelector(".forecast-empty");
  const chartBox = card.querySelector(".forecast-chart-box");
  const canvas = card.querySelector(".chart-forecast");

  const forecastRecords = getForecastRecords(records);

  if (forecastRecords.length === 0) {
    resetForecastCard(panel);
    return;
  }

  emptyEl.hidden = true;
  chartBox.style.display = "";

  updatedEl.textContent =
    `Próximas ${forecastRecords.length} horas, a partir del último dato real`;

  chipsEl.innerHTML = forecastRecords
    .map((record, i) => {
      const value = Number(record.pm25_predicho);
      const level = getAQICategory(value);
      const valueText = Number.isFinite(value) ? value.toFixed(1) : "N/D";

      return `
        <div class="forecast-chip" style="border-top-color:${level.color}">
          <span class="forecast-chip-hour">
            +${i + 1}h · ${formatHourLabel(record.fecha)}
          </span>
          <span class="forecast-chip-value">
            ${valueText}<span class="forecast-chip-unit"> µg/m³</span>
          </span>
          <span class="forecast-chip-label" style="color:${level.color}">
            ${level.label}
          </span>
        </div>
      `;
    })
    .join("");

  const labels = forecastRecords.map(
    (record, i) => `+${i + 1}h (${formatHourLabel(record.fecha)})`
  );
  const values = forecastRecords.map((record) => Number(record.pm25_predicho));
  const colors = forecastRecords.map(
    (record) => getAQICategory(Number(record.pm25_predicho)).color
  );

  state.charts.forecast = new Chart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "PM2.5 pronosticado (µg/m³)",
          data: values,
          backgroundColor: colors,
          borderRadius: 4,
          maxBarThickness: 40,
        },
      ],
    },
    options: {
      ...chartOptions(),
      plugins: {
        legend: { display: false },
      },
    },
  });
}