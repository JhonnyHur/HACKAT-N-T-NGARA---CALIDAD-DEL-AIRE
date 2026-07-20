import os
import pandas as pd
from flask import Flask, jsonify, render_template

app = Flask(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# Config de sensores: id -> nombre visible + archivos
SENSORS = {
    "sensor_1": {
        "label": "Sensor 1",
        "train": "SENSOR_1_TRAIN.csv",
        "test": "SENSOR_1_TEST.csv",
    },
    "sensor_2": {
        "label": "Sensor 2",
        "train": "SENSOR_2_TRAIN.csv",
        "test": "SENSOR_2_TEST.csv",
    },
}

COL_MAP = {
    "Fecha y Hora": "fecha",
    "PM2.5_14D6 (μg/m³)": "pm25",
    "Temperatura (°C)": "temperatura",
    "Humedad (%)": "humedad",
    "Lat": "lat",
    "Long": "long",
    "Pred_PM2.5_14D6 (μg/m³)": "pm25_pred",
}


def load_csv(path):
    df = pd.read_csv(path, encoding="utf-8-sig")
    df = df.rename(columns=COL_MAP)
    return df


# Cache en memoria al arrancar (los CSV son estáticos / no cambian en runtime)
_CACHE = {}
for sensor_id, cfg in SENSORS.items():
    for split in ("train", "test"):
        fpath = os.path.join(DATA_DIR, cfg[split])
        _CACHE[(sensor_id, split)] = load_csv(fpath)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/sensors")
def api_sensors():
    """Metadata de cada sensor: ubicación (lat/long) y última lectura conocida."""
    result = []
    for sensor_id, cfg in SENSORS.items():
        df = _CACHE[(sensor_id, "test")]
        last = df.iloc[-1]
        result.append({
            "id": sensor_id,
            "label": cfg["label"],
            "lat": float(df["lat"].iloc[0]),
            "long": float(df["long"].iloc[0]),
            "last_pm25": float(last["pm25"]),
            "last_fecha": str(last["fecha"]),
        })
    return jsonify(result)


@app.route("/api/data/<sensor_id>/<split>")
def api_data(sensor_id, split):
    if sensor_id not in SENSORS or split not in ("train", "test"):
        return jsonify({"error": "not found"}), 404

    df = _CACHE[(sensor_id, split)]
    records = df.to_dict(orient="records")
    return jsonify({
        "sensor_id": sensor_id,
        "split": split,
        "has_prediction": split == "test",
        "count": len(records),
        "records": records,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
