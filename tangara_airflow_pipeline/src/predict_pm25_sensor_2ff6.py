"""
Script: predict_pm25_sensor_2ff6.py

Descripcion:
    Capa Gold del pipeline. Genera las predicciones de PM2.5 para
    el sensor 2FF6, usando el modelo XGBoost ya entrenado
    (modelo_xgboost_sensor_2FF6.joblib), a partir de los datos en
    vivo de Silver (silver.stg_tangara_sensor_2ff6).

    El modelo espera 8 variables de entrada, buscadas por nombre
    (no importa el orden):

        Temperatura_(°C)_2FF6
        Humedad_(%)_2FF6
        PM2.5_lag_1
        PM2.5_lag_2
        PM2.5_lag_3
        PM2.5_lag_6
        PM2.5_lag_12
        PM2.5_lag_24

    Los "lag" de PM2.5 se calculan a partir del propio historico de
    silver.stg_tangara_sensor_2ff6 (que ya trae una lectura real
    por hora, generada por transform_tangara_data.py). Las primeras
    filas del historico no tienen suficientes horas previas para
    calcular todos los lags (en particular el lag_24 necesita 24
    horas de historico) y se descartan, exactamente igual que se
    hizo al entrenar el modelo originalmente.

    Solo aplica al sensor 2FF6: es el unico sensor para el que
    existe un modelo entrenado por ahora.

    Tabla resultante en Gold:

        gold.sensor_2ff6_predicciones
            - Fecha & Hora
            - Temperatura (°C)
            - Humedad (%)
            - PM2.5_Real (µg/m³)
            - PM2.5_lag_1 (µg/m³)
            - PM2.5_lag_2 (µg/m³)
            - PM2.5_lag_3 (µg/m³)
            - PM2.5_lag_6 (µg/m³)
            - PM2.5_lag_12 (µg/m³)
            - PM2.5_lag_24 (µg/m³)
            - Latitud
            - Longitud
            - PM2.5_Predicho (µg/m³)

    Los lags y las coordenadas se dejan en la tabla Gold (ademas de
    usarse como input del modelo) para que el dashboard pueda, por
    ejemplo, ubicar el sensor en el mapa o inspeccionar el historico
    de PM2.5 que uso el modelo para cada prediccion, sin tener que
    volver a consultar Silver.

Variables de entorno:
    DATABASE_URL (opcional; Postgres origen/destino. Si no se
    define, usa el Postgres local del docker-compose)

Ejecucion:
    python predict_pm25_sensor_2ff6.py
"""

import os

import joblib
import pandas as pd

from sqlalchemy import create_engine, text


# Postgres origen/destino: por defecto el del docker-compose local
# (servicio "postgres"). Se puede sobreescribir con DATABASE_URL
# en el .env para apuntar, por ejemplo, a un Postgres administrado
# en Render.
DATABASE_URL = os.environ.get("DATABASE_URL") or (
    "postgresql+psycopg2://ai_admin:ai_admin@postgres:5432/ai_project"
)

MODEL_PATH = "/opt/airflow/models/modelo_xgboost_sensor_2FF6.joblib"

SILVER_SCHEMA = "silver"
SILVER_TABLE = "stg_tangara_sensor_2ff6"

GOLD_SCHEMA = "gold"
GOLD_TABLE = "sensor_2ff6_predicciones"

# Mismos lags usados al entrenar el modelo original.
LAGS = [1, 2, 3, 6, 12, 24]

# Nombres EXACTOS que espera el modelo (verificados directamente
# contra el archivo .joblib). El orden no importa para el modelo
# (busca por nombre), pero se mantiene consistente aqui.
FEATURE_COLUMNS = [
    "Temperatura_(°C)_2FF6",
    "Humedad_(%)_2FF6",
] + [f"PM2.5_lag_{lag}" for lag in LAGS]


def load_model():

    print("=== CARGANDO MODELO XGBOOST (sensor 2FF6) ===")

    model = joblib.load(MODEL_PATH)

    print(f"Modelo cargado desde: {MODEL_PATH}")

    return model


def load_silver_data(engine):

    print(
        f"=== LEYENDO SILVER: {SILVER_SCHEMA}.{SILVER_TABLE} ==="
    )

    df = pd.read_sql(
        f'''
        SELECT *
        FROM {SILVER_SCHEMA}."{SILVER_TABLE}"
        ORDER BY "Fecha & Hora" ASC
        ''',
        con=engine,
    )

    print(f"Registros leidos: {len(df)}")

    return df


def build_features(df):
    """
    Genera las columnas de lag de PM2.5 y renombra Temperatura /
    Humedad al nombre exacto que espera el modelo. Descarta las
    filas que no alcanzan a tener historico suficiente para todos
    los lags (igual que se hizo en el entrenamiento original).
    """

    df = df.copy()

    for lag in LAGS:

        df[f"PM2.5_lag_{lag}"] = df["PM2.5 (µg/m³)"].shift(lag)

    df["Temperatura_(°C)_2FF6"] = df["Temperatura (°C)"]
    df["Humedad_(%)_2FF6"] = df["Humedad (%)"]

    records_before = len(df)

    df = df.dropna(subset=FEATURE_COLUMNS).reset_index(drop=True)

    records_after = len(df)

    print("=== ELIMINANDO FILAS SIN HISTORICO SUFICIENTE (lags) ===")
    print(f"Registros descartados: {records_before - records_after}")
    print(f"Registros disponibles para predecir: {records_after}")

    return df


def predict_pm25(model, df):

    X = df[FEATURE_COLUMNS]

    predictions = model.predict(X)

    df["PM2.5_Predicho (µg/m³)"] = predictions.round(2)

    return df


def load_to_gold(engine, df):

    with engine.begin() as conn:

        conn.execute(
            text(
                f"CREATE SCHEMA IF NOT EXISTS {GOLD_SCHEMA}"
            )
        )

    lag_columns = [f"PM2.5_lag_{lag}" for lag in LAGS]

    result_columns = (
        ["Fecha & Hora", "Temperatura (°C)", "Humedad (%)", "PM2.5 (µg/m³)"]
        + lag_columns
        + ["Latitud", "Longitud", "PM2.5_Predicho (µg/m³)"]
    )

    result_df = df[result_columns].rename(
        columns={"PM2.5 (µg/m³)": "PM2.5_Real (µg/m³)"}
    )

    result_df.to_sql(
        name=GOLD_TABLE,
        schema=GOLD_SCHEMA,
        con=engine,
        if_exists="replace",
        index=False,
    )

    print(
        f"Tabla {GOLD_SCHEMA}.{GOLD_TABLE}: "
        f"{len(result_df)} registros"
    )


def run_prediction_pipeline():

    print("=== INICIANDO PREDICCION DE PM2.5 (SENSOR 2FF6) ===")

    engine = create_engine(DATABASE_URL)

    df = load_silver_data(engine)

    if len(df) == 0:

        print(
            f"[AVISO] {SILVER_SCHEMA}.{SILVER_TABLE} esta vacia. "
            "Todavia no hay datos para predecir."
        )

        return

    df = build_features(df)

    if len(df) == 0:

        print(
            "[AVISO] No hay suficiente historico todavia (se "
            "necesitan al menos 24 horas de datos consecutivos) "
            "para generar ninguna prediccion."
        )

        return

    model = load_model()

    df = predict_pm25(model, df)

    load_to_gold(engine, df)

    print("=== PREDICCION COMPLETADA ===")
    print("=== PROCESO FINALIZADO EXITOSAMENTE ===")


if __name__ == "__main__":

    run_prediction_pipeline()