"""
app.py

Dashboard "Predicción de PM2.5 Hackatón Tangara".

Antes usaba MongoDB Atlas; ahora se conecta directamente a la misma
base PostgreSQL que llena el pipeline de Airflow
(https://github.com/... proyecto tangara-airflow-pipeline), leyendo
las tablas de la capa Silver que ya trae los datasets de
entrenamiento/prueba por sensor:

    silver.sensor_<codigo>_train
    silver.sensor_<codigo>_test

Donde <codigo> es uno de: 2ff6, f1ae, 1712, 307a.

Secciones del dashboard:
    - Predicciones: por ahora vacia, a la espera de conectar el
      modelo de Machine Learning.
    - Train: datos reales medidos (sin prediccion).
    - Test: datos reales + la prediccion del modelo (si el CSV
      cargado la trae).

Como no se conoce de antemano el nombre exacto de cada columna en
los CSV originales (pueden variar ligeramente entre sensores), las
columnas relevantes (fecha, PM2.5, prediccion, temperatura, humedad,
lat, long) se detectan por coincidencia de palabras clave en el
nombre de columna, en vez de asumir un nombre fijo.
"""

import os

from flask import Flask, jsonify, render_template, request

from sqlalchemy import create_engine, text


app = Flask(__name__)


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://ai_admin:ai_admin@localhost:5432/ai_project"
)

engine = create_engine(DATABASE_URL)

SCHEMA = "silver"

# codigo de tabla -> nombre real del sensor mostrado en el dashboard
SENSORS = {
    "2ff6": "Sensor 2FF6",
    "f1ae": "Sensor F1AE",
    "1712": "Sensor 1712",
    "307a": "Sensor 307A",
}


def table_name(sensor_id, split):

    return f"sensor_{sensor_id}_{split}"


def get_table_columns(conn, table):

    result = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = :schema
              AND table_name = :table
            ORDER BY ordinal_position
            """
        ),
        {"schema": SCHEMA, "table": table}
    )

    return [row[0] for row in result]


def find_column(columns, *keywords, exclude=None):
    """
    Busca la primera columna cuyo nombre (en minusculas) contenga
    TODAS las palabras clave dadas, ignorando las columnas que
    empiecen con `exclude` (ej. para no confundir la columna de
    PM2.5 real con la de PM2.5 predicho).
    """

    for column in columns:

        column_lower = column.lower()

        if exclude and column_lower.startswith(exclude.lower()):

            continue

        if all(keyword.lower() in column_lower for keyword in keywords):

            return column

    return None


def normalize_rows(rows, columns, has_prediction):

    date_col = find_column(columns, "fecha")
    pm25_col = find_column(columns, "pm2", exclude="pred")
    pred_col = find_column(columns, "pred") if has_prediction else None
    temp_col = find_column(columns, "temperatura")
    hum_col = find_column(columns, "humedad")
    lat_col = find_column(columns, "lat")
    long_col = find_column(columns, "long")

    normalized = []

    for row in rows:

        row_dict = dict(zip(columns, row))

        item = {
            "fecha": row_dict.get(date_col) if date_col else None,
            "pm25": row_dict.get(pm25_col) if pm25_col else None,
            "temperatura": row_dict.get(temp_col) if temp_col else None,
            "humedad": row_dict.get(hum_col) if hum_col else None,
            "lat": row_dict.get(lat_col) if lat_col else None,
            "long": row_dict.get(long_col) if long_col else None,
        }

        if has_prediction:

            item["pm25_pred"] = (
                row_dict.get(pred_col) if pred_col else None
            )

        normalized.append(item)

    return normalized


@app.route("/")
def index():

    return render_template("index.html", sensors=SENSORS)


@app.route("/api/_debug/tables")
def debug_tables():
    """Util para verificar que tablas existen realmente en Silver."""

    with engine.connect() as conn:

        result = conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = :schema
                ORDER BY table_name
                """
            ),
            {"schema": SCHEMA}
        )

        existing_tables = [row[0] for row in result]

    expected_tables = [
        table_name(sensor_id, split)
        for sensor_id in SENSORS
        for split in ("train", "test")
    ]

    return jsonify({
        "existing_in_silver": existing_tables,
        "expected_tables": expected_tables,
    })


@app.route("/api/sensors")
def api_sensors():

    result = []

    with engine.connect() as conn:

        for sensor_id, label in SENSORS.items():

            table = table_name(sensor_id, "test")

            try:

                columns = get_table_columns(conn, table)

                if not columns:

                    continue

                date_col = find_column(columns, "fecha")

                order_sql = (
                    f'ORDER BY "{date_col}" DESC' if date_col else ""
                )

                row = conn.execute(
                    text(
                        f'SELECT * FROM {SCHEMA}."{table}" '
                        f'{order_sql} LIMIT 1'
                    )
                ).fetchone()

                if not row:

                    continue

                normalized = normalize_rows(
                    [row], columns, has_prediction=True
                )[0]

                result.append({
                    "id": sensor_id,
                    "label": label,
                    "lat": normalized["lat"],
                    "long": normalized["long"],
                    "last_pm25": normalized["pm25"],
                    "last_fecha": normalized["fecha"],
                })

            except Exception as error:

                print(f"[AVISO] No se pudo leer '{table}': {error}")

                continue

    return jsonify(result)


@app.route("/api/data/<sensor_id>/<split>")
def api_data(sensor_id, split):

    if split not in ("train", "test"):

        return jsonify({"error": "not found"}), 404

    if sensor_id not in SENSORS:

        return jsonify({"error": "not found"}), 404

    table = table_name(sensor_id, split)
    has_prediction = split == "test"

    start_date = request.args.get("start")
    end_date = request.args.get("end")

    with engine.connect() as conn:

        try:

            columns = get_table_columns(conn, table)

        except Exception:

            return jsonify({"error": "not found"}), 404

        if not columns:

            return jsonify({"error": "not found"}), 404

        date_col = find_column(columns, "fecha")

        where_clauses = []
        params = {}

        if date_col and start_date:

            where_clauses.append(f'"{date_col}" >= :start_date')
            params["start_date"] = start_date

        if date_col and end_date:

            where_clauses.append(f'"{date_col}" <= :end_date')
            params["end_date"] = end_date

        where_sql = ""

        if where_clauses:

            where_sql = "WHERE " + " AND ".join(where_clauses)

        order_sql = f'ORDER BY "{date_col}" ASC' if date_col else ""

        rows = conn.execute(
            text(
                f'SELECT * FROM {SCHEMA}."{table}" '
                f'{where_sql} {order_sql}'
            ),
            params
        ).fetchall()

    records = normalize_rows(rows, columns, has_prediction)

    if not records:

        return jsonify({"error": "not found"}), 404

    return jsonify({
        "sensor_id": sensor_id,
        "sensor_label": SENSORS[sensor_id],
        "split": split,
        "has_prediction": has_prediction,
        "count": len(records),
        "records": records,
    })


@app.route("/api/predicciones")
def api_predicciones():
    """
    Placeholder de la seccion Predicciones. Todavia no hay modelo
    de Machine Learning conectado; se deja la ruta lista para
    cuando se integre.
    """

    return jsonify({
        "status": "empty",
        "message": (
            "La sección de Predicciones aún no tiene un modelo "
            "conectado."
        ),
        "records": [],
    })


if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(host="0.0.0.0", port=port, debug=True)
