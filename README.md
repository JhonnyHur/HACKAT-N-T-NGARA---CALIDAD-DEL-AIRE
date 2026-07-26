# Predicción de PM2.5 mediante Modelo de Machine Learning

Proyecto desarrollado para la Hackatón Tángara 2026, que integra un pipeline ETL End-to-End de Ingeniería de Datos e Inteligencia Artificial para la estimación y el pronóstico de concentraciones de PM2.5 en diferentes ubicaciones de la ciudad de Santiago de Cali.

La solución emplea un dataset histórico, obtenido a través de la Red de Sensores Tángara y correspondiente al período comprendido entre enero de 2023 y junio de 2026, para el entrenamiento y la evaluación de un modelo de Machine Learning (XGBoost). Posteriormente, utiliza datos ambientales en tiempo real, provenientes de la misma Red de Sensores Tángara, para generar predicciones de PM2.5 y pronosticar su comportamiento durante las siguientes seis horas.

Todo el proceso es gestionado mediante un pipeline ETL End-to-End, orquestado con Apache Airflow y contenedorizado con Docker, que extrae, transforma y almacena la información en PostgreSQL siguiendo una arquitectura Medallón (Bronze, Silver y Gold). Finalmente, las predicciones se presentan a través de un dashboard interactivo, desplegado en Render, permitiendo visualizar las variables ambientales (temperatura y humedad), consultar información histórica y monitorear la calidad del aire.


---


# Equipo de Desarrollo

| Integrante | Universidad | Correo electrónico |
|------------|-------------|--------------------|
| Bryan Fernando Burbano Carvajal | Universidad Autónoma de Occidente | bryanburbanocarvajal24@gmail.com |
| Jhonny Silvano Hurtado Sinisterra | Universidad Autónoma de Occidente | jhonny.hurtado@uao.edu.co |
| Germán Andrés Calberto Sánchez | Universidad Autónoma de Occidente | gacalberto@uao.edu.co |
| Graciela Sánchez Ibarra | Universidad Autónoma de Baja California | sanchez.graciela@uabc.edu.mx |


---

## Repository Structure

```text
## Repository Structure
.
├── dashboard/
├── tangara_airflow_pipeline/
├── HACKATÓN_TÁNGARA_CALIDAD_DEL_AIRE_...
├── README.md
├── Sensores.xlsx
└── Ubicación de sensores 2.0.pdf
```

### dashboard/

Dashboard interactivo para visualizar variables ambientales, consultar información histórica y monitorear las predicciones de PM2.5.
https://dashboardtangana.onrender.com

### tangara_airflow_pipeline/

Pipeline ETL End-to-End, orquestado con Apache Airflow y contenedorizado con Docker, encargado del procesamiento de los datos en tiempo real de la Red de Sensores Tángara.

### HACKATÓN_TÁNGARA_CALIDAD_DEL_AIRE_SENSOR_2FF6.ipynb

Notebook con la creación, entrenamiento, validación y evaluación del modelo XGBoost utilizando los registros históricos del sensor **2FF6**.

### Sensores.xlsx

Análisis exploratorio de los registros históricos (enero de 2023 a junio de 2026) para la selección de los sensores utilizados en el desarrollo del modelo.

DATA HISTORICA: https://drive.google.com/drive/folders/1nFosDZsS_br2JzNnk9DQLsYXC1DUO2lN?usp=sharing

### Ubicación de sensores 2.0.pdf

Documento con la ubicación geográfica de los cuatro sensores seleccionados para el desarrollo del modelo de Machine Learning.


---

## Origen de los datos

Los datos son obtenidos desde la infraestructura de la Red de Sensores Tángara, almacenados en una base de datos ClickHouse. El pipeline consulta la capa Silver para extraer información de temperatura, humedad, PM2.5 y la ubicación de los sensores.

**Repositorio de referencia**

**Autor:** Sebastian Rios Sabogal

**Repositorio:** https://github.com/sebaxtian/clickhouse-tangara

Para el desarrollo del proyecto se utilizaron los siguientes sensores:

| Código | Nombre del sensor |
|--------:|-------------------|
| 2FF6 | D29ESP32DED2FF6 |
| F1AE | D29TTGOTD8F1AE  |
| 1712 | D29ESP32DEE1712 |
| 307A | D29ESP32DED307A |



## Arquitectura

```text




```



---

# Ejecución del Proyecto

Levantar los contenedores:

```bash
docker compose up -d --build
```

Detener los contenedores:

```bash
docker compose down
```

Una vez iniciado el proyecto:

1. Ejecuta el DAG desde **Apache Airflow**.
2. El pipeline extrae los datos más recientes de la **Red de Sensores Tángara**.
3. Los datos son procesados y almacenados en **PostgreSQL**.
4. El dashboard desplegado en **Render** consulta automáticamente la base de datos y muestra la información más reciente junto con el pronóstico de **PM2.5 para las próximas 6 horas**.

---

# Acceso a Apache Airflow

URL

```text
http://localhost:8080
```

Usuario

```text
admin
```

Contraseña

```text
admin
```

---

# Acceso a pgAdmin

URL

```text
http://localhost:5050
```

Usuario

```text
admin@admin.com
```

Contraseña

```text
admin
```

---

# Conexión a PostgreSQL Local

### GENERAL

Name

```text
ai-project-postgres
```

### CONNECTION

Host name/address

```text
postgres
```

Port

```text
5432
```

Maintenance database

```text
ai_project
```

Username

```text
ai_admin
```

Password

```text
ai_admin
```

---

# Conexión a PostgreSQL (Render)

### GENERAL

Name

```text
render-postgres
```

### CONNECTION

Host name/address

```text
dpg-d9is09vavr4c73bcokm0-a.ohio-postgres.render.com
```

Port

```text
5432
```

Maintenance database

```text
ai_project_4i6q
```

Username

```text
admin
```

Password

```text
bluS2CCW9ux17mwR6f7x92mjacn8JKER
```

- Host: `postgres`
- Puerto: `5432`
- Base de datos: `ai_project`
- Usuario: `ai_admin`
- Contraseña: `ai_admin`
