"""
Script: extract_tangara_data.py

Descripcion:
    Extrae desde la instancia ClickHouse del ecosistema Tangara
    (https://github.com/sebaxtian/clickhouse-tangara) las variables
    Temperatura ("tmp"), Humedad ("hum"), ubicacion ("geo") y PM2.5
    ("pm25") de la capa Plata (tangara_plata.plata_tangara_sensores),
    y las aterriza como datos crudos en la capa Bronze de este
    pipeline (PostgreSQL, esquema bronze).

    Tangara no expone un API REST propio: el acceso se hace por
    conexion directa a ClickHouse (cliente nativo clickhouse-connect
    via HTTPS), tal como valida el repositorio de referencia.

Variables de entorno requeridas (ver env.example):
    CLICKHOUSE_HOST
    CLICKHOUSE_PORT
    CLICKHOUSE_USER
    CLICKHOUSE_PASSWORD
    CLICKHOUSE_DATABASE   (tangara_plata)
    CLICKHOUSE_SECURE     (True/False)
    CLICKHOUSE_TABLE      (plata_tangara_sensores)
    TANGARA_SENSOR_NAMES  (lista de sensores separados por coma,
                           ej: 2FF6,F1AE,1712,3O7A)
    TANGARA_LOOKBACK_HOURS (opcional, ventana incremental, default 24)

Ejecucion:
    python extract_tangara_data.py
"""

import os

import clickhouse_connect
import pandas as pd

from dotenv import load_dotenv

from sqlalchemy import create_engine, text


load_dotenv()


RAW_FILE = "data/raw/tangara_sensores_api_data.csv"


def get_clickhouse_client():

    print("=== CONECTANDO A CLICKHOUSE (TANGARA) ===")

    client = clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST"),
        port=int(os.getenv("CLICKHOUSE_PORT", 443)),
        username=os.getenv("CLICKHOUSE_USER"),
        password=os.getenv("CLICKHOUSE_PASSWORD"),
        secure=os.getenv("CLICKHOUSE_SECURE", "True").lower() == "true",
        database=os.getenv("CLICKHOUSE_DATABASE", "tangara_plata"),
    )

    print("=== CONEXION EXITOSA ===")

    return client


def extract_api_data():

    client = get_clickhouse_client()

    table = os.getenv("CLICKHOUSE_TABLE", "plata_tangara_sensores")

    lookback_hours = int(
        os.getenv("TANGARA_LOOKBACK_HOURS", 24)
    )

    sensor_names_raw = os.getenv("TANGARA_SENSOR_NAMES", "")

    sensor_names = [
        name.strip()
        for name in sensor_names_raw.split(",")
        if name.strip()
    ]

    # =====================================
    # SE EXTRAEN: time, name, geo, tmp, hum, pm25
    # =====================================

    query = f"""
        SELECT
            time,
            name,
            geo,
            tmp,
            hum,
            pm25
        FROM {table}
        WHERE time >= now() - INTERVAL {lookback_hours} HOUR
          AND tmp IS NOT NULL
          AND hum IS NOT NULL
    """

    if sensor_names:

        # Los codigos cortos (ej. 2FF6) son el sufijo final del
        # nombre completo del sensor en ClickHouse
        # (ej. D29ESP32DED2FF6), por eso se filtra con LIKE
        # en vez de una igualdad exacta.

        sensor_conditions = " OR ".join(
            f"name LIKE '%{name}'" for name in sensor_names
        )

        query += f" AND ({sensor_conditions})"

    query += " ORDER BY name, time"

    print("=== DESCARGANDO DATOS DE TEMPERATURA Y HUMEDAD ===")
    print(f"Tabla origen: {table}")
    print(f"Ventana: ultimas {lookback_hours} horas")

    if sensor_names:

        print(f"Sensores filtrados: {', '.join(sensor_names)}")

    else:

        print(
            "Sensores filtrados: todos "
            "(no se definio TANGARA_SENSOR_NAMES)"
        )

    df = client.query_df(query)

    print("=== EXTRACCION COMPLETADA ===")
    print(f"Total registros descargados: {len(df)}")

    if len(df) > 0:

        print("Registro mas antiguo:")
        print(df["time"].min())

        print("Registro mas reciente:")
        print(df["time"].max())

    return df


def save_raw_data(df):

    os.makedirs(
        "data/raw",
        exist_ok=True
    )

    df.to_csv(
        RAW_FILE,
        index=False
    )

    print("=== ARCHIVO RAW CREADO ===")
    print(f"Archivo: {RAW_FILE}")
    print(f"Registros guardados: {len(df)}")


def load_to_bronze(df):

    engine = create_engine(
        "postgresql+psycopg2://ai_admin:ai_admin@postgres:5432/ai_project"
    )

    with engine.begin() as conn:

        conn.execute(
            text(
                """
                CREATE SCHEMA IF NOT EXISTS bronze
                """
            )
        )

    df.to_sql(
        name="tangara_sensores_api_data",
        schema="bronze",
        con=engine,
        if_exists="append",
        index=False
    )

    print("=== CARGA A BRONZE COMPLETADA ===")
    print("Schema: bronze")
    print("Tabla: tangara_sensores_api_data")
    print(f"Registros insertados: {len(df)}")


if __name__ == "__main__":

    dataframe = extract_api_data()

    if len(dataframe) > 0:

        save_raw_data(dataframe)

        load_to_bronze(dataframe)

    print("Proceso completado exitosamente.")
