# Predicción de PM2.5 Hackatón Tangara

Dashboard Flask que muestra los datos de los sensores de la red
Tangara (2FF6), con mapa de ubicación, gráficas de
PM2.5/Temperatura/Humedad, filtros por rango de fechas y 3 secciones:
**Predicciones**, **Train** y **Test**.


```
dashboard/
├── static/
│   ├── css/
│   │   └── style.css        Estilos
│   └── js/
│       └── app.js           Tabs, filtros de fecha, mapa Leaflet, gráficas Chart.js
├── templates/
│   └── index.html           Vista principal (3 pestañas)
├── .env
├── app.py                   Backend Flask (Postgres) — expone /api/sensors,
│                             /api/data/<sensor>/<split> y /api/predicciones
├── env.example
├── Procfile                 Comando de arranque para Render (gunicorn)
├── README.md
└── requirements.txt
```

## Variable de entorno: DATABASE_URL

Todo el comportamiento del dashboard depende de una sola variable:

```
DATABASE_URL=postgresql+psycopg2://usuario:password@host:puerto/nombre_bd
```

Si no defines `DATABASE_URL`, el dashboard usa por defecto
`postgresql+psycopg2://ai_admin:ai_admin@localhost:5432/ai_project`
(las credenciales por defecto del Postgres local del pipeline), así
que en local muchas veces no necesitas configurar nada si ya tienes
ese Postgres corriendo.

Tienes dos opciones para esta variable, según a qué Postgres quieras
apuntar:

### Opción A — Postgres LOCAL

Esta opción sirve si estás corriendo el pipeline de Airflow en tu
máquina.

1. Verifica en el `.env` del pipeline (o en su `docker-compose.yml`)
   cuáles son `POSTGRES_USER`, `POSTGRES_PASSWORD` y `POSTGRES_DB`.
   Por defecto son `ai_admin` / `ai_admin` / `ai_project`.
2. Como el Postgres del pipeline expone el puerto 5432 al host
   (`"5432:5432"` en su `docker-compose.yml`), desde tu máquina se ve
   como si corriera en `localhost`. Tu `DATABASE_URL` queda:

   ```
   DATABASE_URL=postgresql+psycopg2://ai_admin:ai_admin@localhost:5432/ai_project
   ```

   Nota: si de igual forma dejas `DATABASE_URL` vacía, el dashboard
   debería apuntar al Postgres local de igual manera (es el default). 
   Esto si estas corriendo y usando el flujo de airflow de tangara_airflow_pipeline

### Opción B — Postgres en RENDER

En este caso, usa la siguiente URL para conectarte al Postgres que ya
tenemos en Render:

```
DATABASE_URL=postgresql+psycopg2://admin:bluS2CCW9ux17mwR6f7x92mjacn8JKER@dpg-d9is09vavr4c73bcokm0-a.ohio-postgres.render.com/ai_project_4i6q
```

## Correr en local

1. Copia las variables de entorno:

   ```bash
   cp env.example .env
   ```

2. Abre `.env` y pega ahí tu `DATABASE_URL`, según la Opción A o B de
   arriba (o déjala vacía para usar el default del Postgres local).

3. Instala dependencias y corre:

   ```bash
   pip install -r requirements.txt
   python app.py
   ```

4. Abre <http://localhost:5000>.

## Desplegar en Render

1. Sube esta carpeta a un repo de GitHub.
2. En Render: **New > Web Service**, conecta el repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app` (ya está en el Procfile).
5. En **Environment**, agrega la variable `DATABASE_URL` apuntando al
   Postgres que ya está en Render (Opción B de arriba):

   ```
   postgresql+psycopg2://admin:bluS2CCW9ux17mwR6f7x92mjacn8JKER@dpg-d9is09vavr4c73bcokm0-a.ohio-postgres.render.com/ai_project_4i6q
   ```

6. Deploy. Render te da una URL tipo `tu-app.onrender.com`.