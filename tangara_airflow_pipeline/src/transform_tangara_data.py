"""
Script: transform_tangara_data.py

Descripcion:
    Limpia, valida y transforma los datos crudos de Temperatura y
    Humedad de la capa Bronze (bronze.tangara_sensores_api_data),
    y los deja listos para consumo analitico en la capa Silver,
    generando UNA TABLA POR SENSOR, con UNA LECTURA ORIGINAL POR
    HORA (no se promedia: se toma la primera lectura real que cae
    dentro de cada hora, con su valor tal cual llego del sensor):

        silver.stg_tangara_sensor_2ff6
        silver.stg_tangara_sensor_f1ae
        silver.stg_tangara_sensor_1712
        silver.stg_tangara_sensor_307a

    Cada tabla queda con unicamente 3 columnas:
        - Fecha & Hora
        - Temperatura (°C)
        - Humedad (%)

    Incluye:
        - Validacion de rangos fisicamente posibles.
        - Deduplicacion por sensor + timestamp.
        - Mapeo del nombre completo del sensor en ClickHouse
          (ej. D29ESP32DED2FF6) a su codigo corto (ej. 2FF6), usado
          para nombrar cada tabla.

Ejecucion:
    python transform_tangara_data.py
"""

import pandas as pd

from sqlalchemy import create_engine, text


# =====================================
# MAPEO: nombre completo (sufijo) -> codigo corto del sensor
# =====================================

SENSOR_CODES = [
    "2FF6",
    "F1AE",
    "1712",
    "307A",
]


def map_sensor_code(full_name):

    for code in SENSOR_CODES:

        if full_name.endswith(code):

            return code

    return full_name


def transform_api_data():

    print("=== INICIANDO TRANSFORMACION DE DATOS TANGARA ===")

    engine = create_engine(
        "postgresql+psycopg2://ai_admin:ai_admin@postgres:5432/ai_project"
    )

    df = pd.read_sql(
        """
        SELECT *
        FROM bronze.tangara_sensores_api_data
        """,
        con=engine
    )

    original_records = len(df)

    print(f"Registros leidos de bronze: {original_records}")

    # =====================================
    # DEDUPLICACION (sensor + timestamp)
    # =====================================

    df = df.drop_duplicates(
        subset=["name", "time"]
    )

    print("=== DEDUPLICACION ===")
    print(f"Registros tras deduplicar: {len(df)}")

    # =====================================
    # VALIDACIONES DE RANGO
    # =====================================

    records_before_validation = len(df)

    df = df[
        (df["hum"] >= 0) &
        (df["hum"] <= 100) &
        (df["tmp"] >= -10) &
        (df["tmp"] <= 60)
    ]

    records_after_validation = len(df)

    print("=== VALIDACION DE RANGOS ===")
    print("Regla: Humedad (%) entre 0 y 100")
    print("Regla: Temperatura (C) entre -10 y 60")
    print(
        f"Registros descartados: "
        f"{records_before_validation - records_after_validation}"
    )

    # =====================================
    # RENOMBRAR / ESTANDARIZAR COLUMNAS
    # =====================================

    transformed_df = pd.DataFrame()

    transformed_df["Fecha & Hora"] = pd.to_datetime(df["time"])
    transformed_df["Sensor"] = df["name"].apply(map_sensor_code)
    transformed_df["Temperatura (°C)"] = df["tmp"].round(1)
    transformed_df["Humedad (%)"] = df["hum"].round(1)

    transformed_df = transformed_df.sort_values(
        by=["Sensor", "Fecha & Hora"]
    )

    print("=== MAPEO DE SENSORES ===")
    print(
        "Codigos detectados: "
        f"{sorted(transformed_df['Sensor'].unique().tolist())}"
    )

    numeric_columns = [
        "Temperatura (°C)",
        "Humedad (%)",
    ]

    transformed_df[numeric_columns] = (
        transformed_df[numeric_columns].round(1)
    )

    print(f"Registros antes de muestrear por hora: {len(transformed_df)}")

    # =====================================
    # UNA LECTURA ORIGINAL POR HORA
    # (no se promedia: se toma la primera lectura real
    # que cae dentro de cada hora, con su valor tal cual)
    # =====================================

    transformed_df["Hora_Referencia"] = (
        transformed_df["Fecha & Hora"].dt.floor("h")
    )

    transformed_df = (
        transformed_df
        .groupby(["Sensor", "Hora_Referencia"], as_index=False)
        .first()
    )

    transformed_df = transformed_df.drop(columns=["Hora_Referencia"])

    print(f"Registros tras muestrear por hora: {len(transformed_df)}")

    # =====================================
    # CARGA A SILVER - UNA TABLA POR SENSOR
    # =====================================

    with engine.begin() as conn:

        conn.execute(
            text(
                """
                CREATE SCHEMA IF NOT EXISTS silver
                """
            )
        )

    print("=== CARGA A SILVER (UNA TABLA POR SENSOR) ===")

    for sensor_code in SENSOR_CODES:

        sensor_df = (
            transformed_df[
                transformed_df["Sensor"] == sensor_code
            ]
            .drop(columns=["Sensor"])
            .reset_index(drop=True)
        )

        table_name = (
            f"stg_tangara_sensor_{sensor_code.lower()}"
        )

        sensor_df.to_sql(
            name=table_name,
            schema="silver",
            con=engine,
            if_exists="replace",
            index=False
        )

        print(
            f"Tabla silver.{table_name}: "
            f"{len(sensor_df)} registros"
        )

    print("=== TRANSFORMACION COMPLETADA ===")
    print("=== PROCESO FINALIZADO EXITOSAMENTE ===")


if __name__ == "__main__":

    transform_api_data()
