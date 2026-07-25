# Predicción de PM2.5 Hackatón Tangara

Dashboard Flask que muestra los datos de los sensores de la red
Tangara (2FF6, F1AE, 1712, 307A), con mapa de ubicación, gráficas de
PM2.5/Temperatura/Humedad, filtros por rango de fechas y 3 secciones:
**Predicciones**, **Train** y **Test**.

> Cambio importante: este dashboard ya **no usa MongoDB Atlas**.
> Ahora se conecta directamente a **PostgreSQL** — la misma base que
> llena el pipeline `tangara-airflow-pipeline`, leyendo las tablas
> `silver.sensor_<codigo>_train` y `silver.sensor_<codigo>_test`
> que ese pipeline genera a partir de los CSV de `datos_train_test/`.

## Secciones

- **Predicciones**: por ahora vacía — queda lista para conectar el
  modelo de Machine Learning más adelante (`/api/predicciones`).
- **Train**: datos reales medidos por sensor (sin predicción).
- **Test**: datos reales + la predicción del modelo, cuando el CSV
  cargado la trae (columna que empiece con `Pred_`).

## Estructura

```
app.py                  Backend Flask (Postgres) — expone /api/sensors,
                         /api/data/<sensor>/<split> y /api/predicciones
templates/index.html    Vista principal (3 pestañas)
static/css/style.css    Estilos
static/js/app.js        Tabs, filtros de fecha, mapa Leaflet, gráficas Chart.js
requirements.txt
Procfile                Comando de arranque para Render (gunicorn)
env.example
```

## Requisito: que existan las tablas en Postgres

Este dashboard **no carga datos por sí mismo** — lee lo que ya dejó
el pipeline de Airflow en Silver. Antes de correr el dashboard,
asegúrate de que el DAG `tangara_pipeline` (proyecto
`tangara-airflow-pipeline`) ya corrió al menos una vez la tarea
`load_train_test_csv_to_silver`, y de que existan estas tablas:

```
silver.sensor_2ff6_train   silver.sensor_2ff6_test
silver.sensor_f1ae_train   silver.sensor_f1ae_test
silver.sensor_1712_train   silver.sensor_1712_test
silver.sensor_307a_train   silver.sensor_307a_test
```

Puedes verificarlo entrando a `http://localhost:5000/api/_debug/tables`
una vez el dashboard esté corriendo.

## Correr en local

1. Copia las variables de entorno:

```bash
cp env.example .env
```

2. Ajusta `DATABASE_URL` en `.env` según dónde esté corriendo tu
   Postgres:
   - Si corres el dashboard **fuera** de Docker y el Postgres del
     pipeline expone el puerto 5432 en tu máquina (como ya lo hace
     `docker-compose.yml` del pipeline con `"5432:5432"`), usa
     `localhost`:
     ```text
     DATABASE_URL=postgresql+psycopg2://ai_admin:ai_admin@localhost:5432/ai_project
     ```
   - Si en cambio corres este dashboard **dentro** de la misma red
     de Docker que el pipeline, usa el nombre del servicio:
     ```text
     DATABASE_URL=postgresql+psycopg2://ai_admin:ai_admin@postgres:5432/ai_project
     ```

3. Instala dependencias y corre:

```bash
pip install -r requirements.txt
python app.py
```

Abre http://localhost:5000

## Desplegar en Render

1. Sube esta carpeta a un repo de GitHub.
2. En Render: **New > Web Service**, conecta el repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app` (ya está en el Procfile).
5. En **Environment**, agrega la variable `DATABASE_URL` apuntando a
   tu Postgres (necesitas que ese Postgres sea accesible desde
   internet — si hoy solo corre en tu Docker local, tendrás que
   exponerlo con un servicio de Postgres administrado, o usar un
   túnel, antes de desplegar aquí).
6. Deploy. Render te da una URL tipo `tu-app.onrender.com`.

## Filtros de tiempo

Cada pestaña (Train / Test) tiene selectores de fecha "Desde" /
"Hasta". Al aplicar el filtro, la consulta a Postgres se limita a
ese rango (`WHERE "Fecha y Hora" >= ... AND <= ...`), sin traer todo
el histórico cada vez.

## Notas sobre las columnas

El backend no asume nombres de columna fijos: detecta automáticamente
cuál es la columna de fecha, PM2.5 real, PM2.5 predicho, temperatura,
humedad, latitud y longitud buscando palabras clave en el nombre de
cada columna (ej. cualquier columna que contenga "fecha", cualquiera
que contenga "pm2" y no empiece por "pred", etc.). Esto evita que el
dashboard se rompa si el nombre exacto de una columna varía
ligeramente entre los CSV de los distintos sensores.
