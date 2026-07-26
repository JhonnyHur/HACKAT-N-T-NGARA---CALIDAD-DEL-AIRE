# Predicción de PM2.5 mediante Modelo de Machine Learning

Proyecto desarrollado para la **Hackatón Tángara 2026**, que integra un pipeline de Ingeniería de Datos y un modelo de Inteligencia Artificial para la estimación de concentraciones de **PM2.5** en el oriente de Santiago de Cali.

La solución combina registros históricos de calidad del aire recopilados entre **2014 y 2019** en la Estación de Monitoreo Compartir con datos ambientales obtenidos en tiempo real a través de la **Red de Sensores Tángara**. Estos datos son procesados automáticamente mediante un pipeline implementado con **Apache Airflow**, almacenados en **PostgreSQL** bajo una arquitectura Medallón (Bronze y Silver) y utilizados por un modelo de **Machine Learning (XGBoost)** para generar predicciones de PM2.5.

Finalmente, los resultados son presentados mediante un **dashboard interactivo**, permitiendo visualizar las variables ambientales, consultar información histórica y monitorear las predicciones generadas por el modelo.

---

# Equipo de Desarrollo

| Integrante | Universidad | Correo electrónico |
|------------|-------------|--------------------|
| Bryan Fernando Burbano Carvajal | Universidad Autónoma de Occidente | bryanburbanocarvajal24@gmail.com |
| Jhonny Silvano Hurtado Sinisterra | *Pendiente* | *Pendiente* |
| Germán Andrés Calberto Sánchez | *Pendiente* | *Pendiente* |
| Graciela Sánchez Ibarra | *Pendiente* | *Pendiente* |


---

## Repository Structure

```text
.
├── dashboard/
├── tangara/
└── README.md
```

---

## Origen de los datos

A diferencia de un API REST tradicional, la red **Tangara** expone sus
datos a través de una instancia **ClickHouse** administrada (repositorio
de referencia:
[sebaxtian/clickhouse-tangara](https://github.com/sebaxtian/clickhouse-tangara)),
protegida detrás de Cloudflare, con conexión TLS/SSL obligatoria.

Esa instancia ya implementa su propia arquitectura medallón interna:

- `tangara_bronce.bronce_tangara_sensores`: datos crudos (String) desde InfluxDB.
- `tangara_plata.plata_tangara_sensores`: datos tipados, deduplicados
  (`ReplacingMergeTree`) — columnas relevantes: `time`, `name` (sensor),
  `geo` (geohash), `tmp` (Temperatura °C), `hum` (Humedad %), `pm25`, `co2`.

Este proyecto se conecta a la capa **Plata** (`tangara_plata`) usando el
cliente nativo `clickhouse-connect`, y extrae las columnas `tmp`
(Temperatura), `hum` (Humedad), `geo` (ubicación/geohash) y `pm25`
(material particulado 2.5), filtrando además por los siguientes
sensores. El código corto es el **sufijo** del nombre completo del
sensor (`name`) en ClickHouse:

| Código corto | Nombre completo en ClickHouse |
|---|---|
| `2FF6` | `D29ESP32DED2FF6` |
| `F1AE` | `D29TTGOTD8F1AE` |
| `1712` | `D29ESP32DEE1712` |
| `307A` (cero, no letra O) | `D29ESP32DED307A` |

Esta lista se controla con la variable `TANGARA_SENSOR_NAMES` en `.env`
(separada por comas, solo el código corto). Si la dejas vacía, el
pipeline trae todos los sensores disponibles.

---

## Arquitectura

```text

                 Apache Airflow DAG
                            │
                            ▼

              ClickHouse Tangara
        (tangara_plata.plata_tangara_sensores)
        tmp + hum + geo + pm25 (Temperatura,
        Humedad, ubicacion, PM2.5)
              filtrado por: 2FF6, F1AE, 1712, 307A
                            │
                            ▼

┌─────────────────────────────────────────────────────┐
│ BRONZE LAYER                                        │
│ PostgreSQL - Schema: bronze                         │
│                                                     │
│ bronze.tangara_sensores_api_data                     │
│                                                     │
│ • Temperatura, Humedad, geo y PM2.5 crudos           │
│ • Ingesta incremental (ventana configurable)         │
└─────────────────────────────────────────────────────┘
                             │
                             ▼

┌─────────────────────────────────────────┐
│ SILVER LAYER                            │
│ Una tabla por sensor:                   │
│   silver.stg_tangara_sensor_2ff6        │
│   silver.stg_tangara_sensor_f1ae        │
│   silver.stg_tangara_sensor_1712        │
│   silver.stg_tangara_sensor_307a        │
│                                         │
│ - Deduplicacion sensor + timestamp      │
│ - Validacion de rangos fisicos          │
│ - Mapeo a codigo corto de sensor        │
│ - Una lectura ORIGINAL por hora         │
│   (no promediada; primera lectura       │
│   real de cada hora)                    │
│                                         │
│ Columnas por tabla:                     │
│   Fecha & Hora | Temperatura (°C) |     │
│   Humedad (%)                           │
└─────────────────────────────────────────┘

     (rama independiente, datos estaticos)

datos_train_test/*.csv (Sensor <codigo> Train/Test.csv)
                             │
                             ▼

┌─────────────────────────────────────────┐
│ SILVER LAYER (train/test)               │
│   silver.sensor_2ff6_train / _test      │
│   silver.sensor_f1ae_train / _test      │
│   silver.sensor_1712_train / _test      │
│   silver.sensor_307a_train / _test      │
│                                         │
│ Se cargan tal cual, sin transformar     │
└─────────────────────────────────────────┘
                             │
                             ▼

              (Próximamente: modelo de ML)

```

---

## Estructura del proyecto

```text
tangara-airflow-pipeline/
├── dags/
│   └── tangara_pipeline_dag.py
├── src/
│   ├── __init__.py
│   ├── extract_tangara_data.py       # ClickHouse -> Bronze
│   ├── transform_tangara_data.py     # Bronze -> Silver
│   └── load_train_test_csv_data.py   # CSV estaticos -> Silver
├── datos_train_test/
│   ├── Sensor 2FF6 Train.csv
│   ├── Sensor 2FF6 Test.csv
│   ├── Sensor F1AE Train.csv
│   ├── Sensor F1AE Test.csv
│   ├── Sensor 1712 Train.csv
│   ├── Sensor 1712 Test.csv
│   ├── Sensor 307A Train.csv
│   └── Sensor 307A Test.csv
├── .gitignore
├── .pre-commit-config.yaml
├── docker-compose.yml
├── Dockerfile
├── env.example
├── README.md
└── requirements.txt
```

---

## Cómo correr todo el proyecto (paso a paso)

### 0. Requisitos previos

- Tener **Docker Desktop** (o Docker + Docker Compose) instalado y
  corriendo.
- Tener las credenciales de ClickHouse del ecosistema Tangara
  (`CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`), provistas por el equipo
  de Tangara. Sin esto el pipeline no podrá conectarse.

### 1. Descomprimir y ubicarte en la carpeta del proyecto

```bash
cd tangara-airflow-pipeline
```

### 2. Crear el archivo de variables de entorno

```bash
cp env.example .env
```

Abre `.env` con tu editor y completa al menos:

```text
CLICKHOUSE_USER=tu_usuario
CLICKHOUSE_PASSWORD=tu_password
```

La lista de sensores (`TANGARA_SENSOR_NAMES=2FF6,F1AE,1712,307A`) y el
resto de valores ya vienen listos por defecto; solo cámbialos si lo
necesitas.

### 3. Verificar la carpeta de datasets train/test

Asegúrate de que la carpeta `datos_train_test/` esté en la raíz del
proyecto (al mismo nivel que `docker-compose.yml`) con los 8 CSV
nombrados exactamente así: `Sensor 2FF6 Train.csv`,
`Sensor 2FF6 Test.csv`, etc. (mayúsculas y espacios tal cual). Si el
nombre no coincide exacto, esa tarea del DAG mostrará un aviso de
"No encontrado" para ese archivo y seguirá con los demás.

### 4. Levantar los contenedores

Desde la misma carpeta (donde está `docker-compose.yml`):

```bash
docker compose up -d --build
```

Esto construye la imagen de Airflow y levanta 3 servicios:
`postgres`, `airflow` y `pgadmin`. La primera vez puede tardar varios
minutos (descarga imágenes, instala Airflow y las dependencias de
`_PIP_ADDITIONAL_REQUIREMENTS`).

> Si ya tenías los contenedores corriendo de una versión anterior y
> solo cambiaste código (no el `.env`), usa
> `docker compose up -d --build` de nuevo para reconstruir la imagen
> con los cambios.

### 5. Activar y correr el DAG

1. Entra a `http://localhost:8080` (usuario `admin`, contraseña `admin`).
2. Busca el DAG `tangara_pipeline` en el listado.
3. Actívalo con el switch de la izquierda (por defecto está pausado).
4. Dispáralo manualmente la primera vez con el botón ▶ (Trigger DAG),
   o espera a que corra según su schedule (`@hourly`).

El DAG tiene 3 tareas: 2 encadenadas y 1 independiente en paralelo:

`extract_and_load_bronze_tangara_data` → `transform_and_load_silver_tangara_data`

`load_train_test_csv_to_silver` (corre en paralelo, no depende de las anteriores — solo lee los CSV estáticos de `datos_train_test/`)

### 6. Revisar los datos cargados

Entra a pgAdmin (`http://localhost:5050`, `admin@admin.com` / `admin`),
conecta el servidor Postgres con los datos de la sección de abajo, y
consulta las tablas:

**Del flujo en vivo (ClickHouse):**
- `bronze.tangara_sensores_api_data`
- `silver.stg_tangara_sensor_2ff6`
- `silver.stg_tangara_sensor_f1ae`
- `silver.stg_tangara_sensor_1712`
- `silver.stg_tangara_sensor_307a`

**De los CSV train/test (estáticos):**
- `silver.sensor_2ff6_train` / `silver.sensor_2ff6_test`
- `silver.sensor_f1ae_train` / `silver.sensor_f1ae_test`
- `silver.sensor_1712_train` / `silver.sensor_1712_test`
- `silver.sensor_307a_train` / `silver.sensor_307a_test`

### 7. Detener el proyecto

```bash
docker compose down
```

Esto detiene los contenedores sin borrar los datos (quedan en el
volumen `postgres_data`). Si además quieres borrar los datos:

```bash
docker compose down -v
```

---

## Acceso a pgAdmin

URL: `http://localhost:5050`
Usuario: `admin@admin.com`
Contraseña: `admin`

### Conexión a PostgreSQL

- Host: `postgres`
- Puerto: `5432`
- Base de datos: `ai_project`
- Usuario: `ai_admin`
- Contraseña: `ai_admin`
