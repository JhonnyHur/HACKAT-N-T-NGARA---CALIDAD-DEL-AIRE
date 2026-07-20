# Dashboard Calidad del Aire

Dashboard Flask que muestra los datos de 2 sensores (train/test), un mapa con
su ubicación y gráficas de PM2.5, temperatura y humedad.

## Estructura

```
app.py                  Backend Flask (lee los CSV y expone /api/sensors y /api/data/<sensor>/<split>)
data/                   Los 4 CSV (SENSOR_1_TRAIN, SENSOR_1_TEST, SENSOR_2_TRAIN, SENSOR_2_TEST)
templates/index.html    Vista principal
static/css/style.css    Estilos
static/js/app.js        Lógica: fetch de API, mapa Leaflet, gráficas Chart.js
requirements.txt
Procfile                Comando de arranque para Render (gunicorn)
```

## Correr en local

```bash
pip install -r requirements.txt
python app.py
```

Abre http://localhost:5000

## Desplegar en Render

1. Sube esta carpeta a un repo de GitHub.
2. En Render: **New > Web Service**, conecta el repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app` (ya está en el Procfile, Render lo detecta solo)
5. Deploy. Render te da una URL tipo `tu-app.onrender.com`.

Si quieres que no se duerma (plan free), puedes apuntar UptimeRobot a esa URL
cada 5 minutos, igual que en el proyecto del sensor anterior.

## Agregar más sensores

En `app.py`, agrega una entrada al diccionario `SENSORS` con su `train` y
`test` (nombres de archivo en `data/`). El mapa y las gráficas se generan
dinámicamente a partir de eso, no hay que tocar el frontend.

## Notas sobre los datos

- `TRAIN`: PM2.5, Temperatura, Humedad, Lat, Long (valores reales medidos).
- `TEST`: lo mismo + `Pred_PM2.5_14D6 (μg/m³)`, la predicción del modelo —
  el dashboard la grafica junto al valor real cuando estás en la pestaña Test.
