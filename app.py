import os
from flask import Flask, jsonify, render_template
from pymongo import MongoClient

app = Flask(__name__)

MONGODB_URI = os.environ.get("MONGODB_URI")
DB_NAME = os.environ.get("MONGODB_DB", "lol")

client = MongoClient(MONGODB_URI)
db = client[DB_NAME]

SENSOR_LABELS = {
    "sensor_1": "Sensor 1",
    "sensor_2": "Sensor 2",
}

# sensor_id + split -> nombre real de la colección en Atlas.
# Renombra tus colecciones en Atlas exactamente así para que esto funcione.
COLLECTIONS = {
    ("sensor_1", "train"): "Sensor1Train",
    ("sensor_1", "test"): "Sensor1Test",
    ("sensor_2", "train"): "Sensor2Train",
    ("sensor_2", "test"): "Sensor2Test",
}

PM25_SUBFIELD = "5_14D6 (μg/m³)"


def normalize(doc, has_prediction):
    pm25_obj = doc.get("PM2") or {}
    flat = {
        "fecha": doc.get("Fecha y Hora"),
        "pm25": pm25_obj.get(PM25_SUBFIELD),
        "temperatura": doc.get("Temperatura (°C)"),
        "humedad": doc.get("Humedad (%)"),
        "lat": doc.get("Lat"),
        "long": doc.get("Long"),
    }
    if has_prediction:
        pred_obj = doc.get("Pred_PM2") or {}
        flat["pm25_pred"] = pred_obj.get(PM25_SUBFIELD)
    return flat


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/_debug/collections")
def debug_collections():
    """Util para verificar que encontramos las colecciones correctas."""
    return jsonify({
        "existing_in_db": db.list_collection_names(),
        "resolved_mapping": {f"{k[0]}/{k[1]}": v for k, v in COLLECTIONS.items()},
    })


@app.route("/api/sensors")
def api_sensors():
    result = []
    for sensor_id, label in SENSOR_LABELS.items():
        coll_name = COLLECTIONS.get((sensor_id, "test"))
        if not coll_name:
            continue
        coll = db[coll_name]
        last_raw = coll.find_one(sort=[("Fecha y Hora", -1)])
        if not last_raw:
            continue
        last = normalize(last_raw, has_prediction=True)
        result.append({
            "id": sensor_id,
            "label": label,
            "lat": last["lat"],
            "long": last["long"],
            "last_pm25": last["pm25"],
            "last_fecha": last["fecha"],
        })
    return jsonify(result)


@app.route("/api/data/<sensor_id>/<split>")
def api_data(sensor_id, split):
    if split not in ("train", "test"):
        return jsonify({"error": "not found"}), 404

    coll_name = COLLECTIONS.get((sensor_id, split))
    if not coll_name:
        return jsonify({"error": "not found"}), 404

    coll = db[coll_name]
    has_prediction = split == "test"
    raw_records = list(coll.find().sort("Fecha y Hora", 1))
    records = [normalize(r, has_prediction) for r in raw_records]

    if not records:
        return jsonify({"error": "not found"}), 404

    return jsonify({
        "sensor_id": sensor_id,
        "split": split,
        "has_prediction": has_prediction,
        "count": len(records),
        "records": records,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
