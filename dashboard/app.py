
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


GOLD_SCHEMA = "gold"
GOLD_SENSOR_ID = "2ff6"
GOLD_TABLE = "sensor_2ff6_predicciones"

SENSORS = {
    "2ff6": "Sensor 2FF6",
    "f1ae": "Sensor F1AE",
    "1712": "Sensor 1712",
    "307a": "Sensor 307A",
}


def table_name(sensor_id, split):

    return f"sensor_{sensor_id}_{split}"


def get_table_columns(conn, table, schema=SCHEMA):

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
        {"schema": schema, "table": table}
    )

    return [row[0] for row in result]


def find_column(columns, *keywords, exclude=None):

    for column in columns:

        column_lower = column.lower()

        if exclude and column_lower.startswith(exclude.lower()):

            continue

        if all(keyword.lower() in column_lower for keyword in keywords):

            return column

    return None


def build_date_filter(date_col, start_date, end_date):

    clauses = []
    params = {}

    if date_col and start_date:

        clauses.append(f'"{date_col}" >= :start_date')
        params["start_date"] = start_date

    if date_col and end_date:

        clauses.append(f'"{date_col}" <= :end_date')
        params["end_date"] = end_date

    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    return where_sql, params


def sensor_snapshot(conn, schema, table, start_date, end_date,
                     pm25_keyword="pm2", exclude_pred="pred"):

    columns = get_table_columns(conn, table, schema=schema)

    if not columns:

        return None

    date_col = find_column(columns, "fecha")
    pm25_col = find_column(columns, pm25_keyword, exclude=exclude_pred)
    lat_col = find_column(columns, "lat")
    long_col = find_column(columns, "long")

    if not date_col or not pm25_col:

        return None

    lat, long_ = None, None

    if lat_col and long_col:

        loc_row = conn.execute(
            text(
                f'SELECT "{lat_col}", "{long_col}" '
                f'FROM {schema}."{table}" '
                f'WHERE "{lat_col}" IS NOT NULL '
                f'AND "{long_col}" IS NOT NULL '
                f'ORDER BY "{date_col}" DESC LIMIT 1'
            )
        ).fetchone()

        if loc_row:

            lat, long_ = loc_row[0], loc_row[1]

    if start_date or end_date:

        where_sql, params = build_date_filter(
            date_col, start_date, end_date
        )

        pm25_filter = f'"{pm25_col}" IS NOT NULL'
        where_sql = (
            f"{where_sql} AND {pm25_filter}" if where_sql
            else f"WHERE {pm25_filter}"
        )

        agg_row = conn.execute(
            text(
                f'SELECT AVG("{pm25_col}"), MIN("{date_col}"), '
                f'MAX("{date_col}"), COUNT(*) '
                f'FROM {schema}."{table}" {where_sql}'
            ),
            params,
        ).fetchone()

        avg_pm25, range_start, range_end, count = agg_row

        return {
            "lat": lat,
            "long": long_,
            "pm25": round(float(avg_pm25), 1) if count else None,
            "fecha": range_end,
            "mode": "average",
            "range_start": range_start,
            "range_end": range_end,
        }

    row = conn.execute(
        text(
            f'SELECT * FROM {schema}."{table}" '
            f'WHERE "{pm25_col}" IS NOT NULL '
            f'ORDER BY "{date_col}" DESC LIMIT 1'
        )
    ).fetchone()

    if not row:

        return None

    row_dict = dict(zip(columns, row))

    return {
        "lat": lat if lat is not None else row_dict.get(lat_col),
        "long": long_ if long_ is not None else row_dict.get(long_col),
        "pm25": row_dict.get(pm25_col),
        "fecha": row_dict.get(date_col),
        "mode": "latest",
        "range_start": None,
        "range_end": None,
    }


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


def normalize_prediction_rows(rows, columns):

    date_col = find_column(columns, "fecha")
    temp_col = find_column(columns, "temperatura")
    hum_col = find_column(columns, "humedad")
    real_col = find_column(columns, "real")
    pred_col = find_column(columns, "predicho")

    normalized = []

    for row in rows:

        row_dict = dict(zip(columns, row))

        normalized.append({
            "fecha": row_dict.get(date_col) if date_col else None,
            "temperatura": row_dict.get(temp_col) if temp_col else None,
            "humedad": row_dict.get(hum_col) if hum_col else None,
            "pm25_real": row_dict.get(real_col) if real_col else None,
            "pm25_predicho": row_dict.get(pred_col) if pred_col else None,
        })

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

    start_date = request.args.get("start")
    end_date = request.args.get("end")

    result = []

    with engine.connect() as conn:

        for sensor_id, label in SENSORS.items():

            snapshot = None

            if sensor_id == GOLD_SENSOR_ID:

                try:

                    snapshot = sensor_snapshot(
                        conn, GOLD_SCHEMA, GOLD_TABLE,
                        start_date, end_date,
                        pm25_keyword="real", exclude_pred="pred",
                    )

                except Exception as error:

                    print(
                        f"[AVISO] No se pudo leer ubicacion desde "
                        f"Gold para '{sensor_id}': {error}"
                    )

                    snapshot = None

            if snapshot is None:

                table = table_name(sensor_id, "test")

                try:

                    snapshot = sensor_snapshot(
                        conn, SCHEMA, table, start_date, end_date
                    )

                except Exception as error:

                    print(f"[AVISO] No se pudo leer '{table}': {error}")

                    continue

            if snapshot is None:

                continue

            result.append({
                "id": sensor_id,
                "label": label,
                "lat": snapshot["lat"],
                "long": snapshot["long"],
                "last_pm25": snapshot["pm25"],
                "last_fecha": snapshot["fecha"],
                "mode": snapshot["mode"],
                "range_start": snapshot["range_start"],
                "range_end": snapshot["range_end"],
            })

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


    start_date = request.args.get("start")
    end_date = request.args.get("end")

    with engine.connect() as conn:

        try:

            columns = get_table_columns(
                conn, GOLD_TABLE, schema=GOLD_SCHEMA
            )

        except Exception as error:

            print(
                f"[AVISO] No se pudo leer '{GOLD_SCHEMA}.{GOLD_TABLE}': "
                f"{error}"
            )

            columns = []

        if not columns:

            return jsonify({
                "status": "empty",
                "message": (
                    "Todavía no hay predicciones disponibles para "
                    "el sensor 2FF6. El modelo necesita al menos "
                    "24 horas de histórico antes de generar la "
                    "primera predicción."
                ),
                "records": [],
            })

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

        try:

            rows = conn.execute(
                text(
                    f'SELECT * FROM {GOLD_SCHEMA}."{GOLD_TABLE}" '
                    f'{where_sql} {order_sql}'
                ),
                params
            ).fetchall()

        except Exception as error:

            print(
                f"[AVISO] Error consultando "
                f"'{GOLD_SCHEMA}.{GOLD_TABLE}': {error}"
            )

            return jsonify({
                "status": "empty",
                "message": "Error consultando las predicciones.",
                "records": [],
            })

    records = normalize_prediction_rows(rows, columns)

    if not records:

        return jsonify({
            "status": "empty",
            "message": (
                "No hay predicciones para el rango de fechas "
                "seleccionado."
            ),
            "records": [],
        })

    return jsonify({
        "status": "ok",
        "sensor_id": GOLD_SENSOR_ID,
        "sensor_label": SENSORS[GOLD_SENSOR_ID],
        "count": len(records),
        "records": records,
    })


if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(host="0.0.0.0", port=port, debug=True)