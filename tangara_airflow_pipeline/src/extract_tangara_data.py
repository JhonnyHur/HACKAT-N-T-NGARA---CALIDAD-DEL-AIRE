
import os

from zoneinfo import ZoneInfo

import clickhouse_connect
import pandas as pd

from dotenv import load_dotenv

from sqlalchemy import text

from db_engines import get_engines, get_local_engine


load_dotenv()


RAW_FILE = "data/raw/tangara_sensores_api_data.csv"

#
CALI_TZ = ZoneInfo("America/Bogota")


def cali_to_utc(cali_naive_datetime):

    if cali_naive_datetime is None:

        return None

    cali_aware = pd.Timestamp(cali_naive_datetime).tz_localize(
        CALI_TZ
    )

    return cali_aware.tz_convert("UTC").tz_localize(None)


def get_last_extracted_time():

    engine = get_local_engine()

    try:

        with engine.connect() as conn:

            result = conn.execute(
                text(
                    """
                    SELECT MAX(time)
                    FROM bronze.tangara_sensores_api_data
                    """
                )
            ).scalar()

        return result

    except Exception:

        return None


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

    start_date = os.getenv(
        "TANGARA_START_DATE", "2026-07-01 00:00:00"
    )

    sensor_names_raw = os.getenv("TANGARA_SENSOR_NAMES", "")

    sensor_names = [
        name.strip()
        for name in sensor_names_raw.split(",")
        if name.strip()
    ]

    start_date_cali = pd.Timestamp(start_date)
    start_date_utc = cali_to_utc(start_date_cali)

    last_extracted_time = get_last_extracted_time()

    if last_extracted_time:

        since_time_incremental = cali_to_utc(last_extracted_time)

        since_time = max(since_time_incremental, start_date_utc)

        if since_time_incremental < start_date_utc:

            print(
                "[AVISO] El ultimo dato en bronze "
                f"({since_time_incremental} UTC) es anterior a "
                f"TANGARA_START_DATE ({start_date_cali} hora Cali "
                f"/ {start_date_utc} UTC). Se aplica el piso: no "
                "se trae nada de antes de esa fecha."
            )

        print(
            "=== EXTRACCION INCREMENTAL: retomando desde el "
            f"ultimo dato guardado ({last_extracted_time} hora "
            f"Cali / {since_time} UTC) ==="
        )

    else:

        since_time = start_date_utc

        print(
            "=== PRIMERA CORRIDA (bronze vacia): trayendo "
            f"historico completo desde {start_date_cali} hora "
            f"Cali ({since_time} UTC) hasta el presente ==="
        )

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
        WHERE time > '{since_time}'
          AND tmp IS NOT NULL
          AND hum IS NOT NULL
    """

    if sensor_names:


        sensor_conditions = " OR ".join(
            f"name LIKE '%{name}'" for name in sensor_names
        )

        query += f" AND ({sensor_conditions})"

    query += " ORDER BY name, time"

    print("=== DESCARGANDO DATOS DE TEMPERATURA Y HUMEDAD ===")
    print(f"Tabla origen: {table}")
    print(f"Desde (UTC): {since_time} (hasta el presente)")

    if sensor_names:

        print(f"Sensores filtrados: {', '.join(sensor_names)}")

    else:

        print(
            "Sensores filtrados: todos "
            "(no se definio TANGARA_SENSOR_NAMES)"
        )

    df = client.query_df(query)

    if len(df) > 0:

        df["time"] = (
            pd.to_datetime(df["time"], utc=True)
            .dt.tz_convert(CALI_TZ)
            .dt.tz_localize(None)
        )

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

    for label, engine in get_engines():

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

        print(f"=== CARGA A BRONZE COMPLETADA ({label}) ===")
        print("Schema: bronze")
        print("Tabla: tangara_sensores_api_data")
        print(f"Registros insertados: {len(df)}")


if __name__ == "__main__":

    dataframe = extract_api_data()

    if len(dataframe) > 0:

        save_raw_data(dataframe)

        load_to_bronze(dataframe)

    print("Proceso completado exitosamente.")