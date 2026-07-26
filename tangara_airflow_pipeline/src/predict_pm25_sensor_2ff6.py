
import os

import joblib
import pandas as pd

from sqlalchemy import create_engine, text


DATABASE_URL = os.environ.get("DATABASE_URL") or (
    "postgresql+psycopg2://ai_admin:ai_admin@postgres:5432/ai_project"
)

MODEL_PATH = "/opt/airflow/models/modelo_xgboost_sensor_2FF6.joblib"

SILVER_SCHEMA = "silver"
SILVER_TABLE = "stg_tangara_sensor_2ff6"

GOLD_SCHEMA = "gold"
GOLD_TABLE = "sensor_2ff6_predicciones"


LAGS = [1, 2, 3, 6, 12, 24]


FEATURE_COLUMNS = [
    "Temperatura_(°C)_2FF6",
    "Humedad_(%)_2FF6",
] + [f"PM2.5_lag_{lag}" for lag in LAGS]


GOLD_COLUMNS = (
    ["Fecha & Hora", "Temperatura (°C)", "Humedad (%)"]
    + ["PM2.5_Real (µg/m³)"]
    + [f"PM2.5_lag_{lag}" for lag in LAGS]
    + ["Latitud", "Longitud", "PM2.5_Predicho (µg/m³)"]
)


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


def ensure_gold_schema(engine):

    with engine.begin() as conn:

        conn.execute(
            text(
                f"CREATE SCHEMA IF NOT EXISTS {GOLD_SCHEMA}"
            )
        )


def gold_table_exists(engine):

    with engine.connect() as conn:

        return conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = :schema
                    AND table_name = :table
                )
                """
            ),
            {"schema": GOLD_SCHEMA, "table": GOLD_TABLE},
        ).scalar()


def load_to_gold(engine, df):
    ensure_gold_schema(engine)

    result_df = df[
        ["Fecha & Hora", "Temperatura (°C)", "Humedad (%)", "PM2.5 (µg/m³)"]
        + [f"PM2.5_lag_{lag}" for lag in LAGS]
        + ["Latitud", "Longitud", "PM2.5_Predicho (µg/m³)"]
    ].rename(columns={"PM2.5 (µg/m³)": "PM2.5_Real (µg/m³)"})[GOLD_COLUMNS]

    if gold_table_exists(engine):

        with engine.begin() as conn:

            conn.execute(
                text(
                    f'''
                    DELETE FROM {GOLD_SCHEMA}."{GOLD_TABLE}"
                    WHERE "PM2.5_Real (µg/m³)" IS NOT NULL
                    '''
                )
            )

    result_df.to_sql(
        name=GOLD_TABLE,
        schema=GOLD_SCHEMA,
        con=engine,
        if_exists="append",
        index=False,
    )

    print(
        f"Tabla {GOLD_SCHEMA}.{GOLD_TABLE}: "
        f"{len(result_df)} registros historicos insertados "
        "(filas de pronostico, si existen, no se tocan)"
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