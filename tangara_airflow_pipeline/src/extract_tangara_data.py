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
    TANGARA_START_DATE    (opcional, fecha desde la que se trae el
                           historico la PRIMERA vez que corre el
                           pipeline (bronze todavia vacia), en hora
                           Cali/Colombia, default
                           2026-07-01 00:00:00)
    DATABASE_URL          (opcional; Postgres destino. Si no se
                           define, usa el Postgres local del
                           docker-compose)

Zona horaria:
    ClickHouse devuelve la columna "time" en UTC (ej.
    2026-07-26T04:15:05Z). Antes de guardar en bronze, esa columna
    se convierte a hora de Cali/Colombia (America/Bogota, UTC-5) y
    se guarda como datetime naive en esa zona horaria. La consulta
    incremental contra ClickHouse (ver mas abajo) sigue
    comparandose en UTC, ya que asi es como ClickHouse almacena el
    dato; el timestamp guardado en bronze (en hora Cali) se
    reconvierte a UTC unicamente para poder construir esa consulta.

Logica de extraccion incremental:
    En cada corrida se consulta el timestamp mas reciente ya
    guardado en bronze.tangara_sensores_api_data (en hora Cali).
    Si existe, se reconvierte a UTC y solo se trae de ClickHouse lo
    que sea posterior a ese timestamp (sin volver a traer, ni
    duplicar, lo que ya se cargo antes). Si bronze todavia esta
    vacia (primera corrida), se trae desde TANGARA_START_DATE
    (interpretada en hora Cali, igual que el resto del pipeline;
    se reconvierte a UTC solo para consultar ClickHouse) hasta el
    presente. TANGARA_START_DATE tambien actua como un PISO DURO:
    nunca se trae de ClickHouse nada anterior a esa fecha (en hora
    Cali), ni siquiera en corridas incrementales. Esto permite
    correr el
    pipeline con la frecuencia que sea (cada hora, una vez a la
    semana, etc.) sin perder datos ni repetir trabajo: siempre
    retoma desde donde se quedo la ultima vez.

Ejecucion:
    python extract_tangara_data.py
"""

import os

from zoneinfo import ZoneInfo

import clickhouse_connect
import pandas as pd

from dotenv import load_dotenv

from sqlalchemy import text

from db_engines import get_engines, get_local_engine


load_dotenv()


RAW_FILE = "data/raw/tangara_sensores_api_data.csv"

# ClickHouse guarda "time" en UTC. Este proyecto guarda y muestra
# todo en hora de Cali/Colombia.
CALI_TZ = ZoneInfo("America/Bogota")


def cali_to_utc(cali_naive_datetime):
    """
    Convierte un datetime naive que representa hora de Cali
    (America/Bogota) -- tal como queda guardado en bronze -- de
    vuelta a UTC naive, para poder usarlo en la consulta contra
    ClickHouse (que almacena "time" en UTC).
    """

    if cali_naive_datetime is None:

        return None

    cali_aware = pd.Timestamp(cali_naive_datetime).tz_localize(
        CALI_TZ
    )

    return cali_aware.tz_convert("UTC").tz_localize(None)


def get_last_extracted_time():
    """
    Consulta el timestamp mas reciente ya guardado en
    bronze.tangara_sensores_api_data (siempre en el Postgres
    LOCAL, que es la fuente de verdad que el propio pipeline usa
    para saber por donde va), para retomar la extraccion justo
    desde ahi. Si la tabla/schema todavia no existe (primera
    corrida del pipeline), devuelve None.
    """

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

    # =====================================
    # EXTRACCION INCREMENTAL: se retoma desde el ultimo timestamp
    # ya guardado en bronze. Si bronze esta vacia (primera
    # corrida), se retoma desde TANGARA_START_DATE. Ademas,
    # TANGARA_START_DATE actua como un PISO DURO: pase lo que pase
    # (bronze vacia, corrupta, reseteada, etc.), nunca se trae de
    # ClickHouse nada anterior a esa fecha.
    #
    # TANGARA_START_DATE se interpreta en hora Cali/Colombia (ej.
    # "2026-07-01 00:00:00" = medianoche del 1 de julio en Cali),
    # igual que el resto del pipeline, y se convierte a UTC
    # unicamente para poder compararla contra ClickHouse.
    # =====================================

    start_date_cali = pd.Timestamp(start_date)
    start_date_utc = cali_to_utc(start_date_cali)

    last_extracted_time = get_last_extracted_time()

    if last_extracted_time:

        # last_extracted_time viene en hora Cali (asi se guarda en
        # bronze); se reconvierte a UTC porque asi es como
        # ClickHouse almacena y compara la columna "time".
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

        # ClickHouse devuelve "time" en UTC (ej.
        # 2026-07-26T04:15:05Z). Se convierte a hora de
        # Cali/Colombia antes de guardar en bronze, y se deja como
        # datetime naive (sin info de zona) para simplificar su
        # uso en el resto del pipeline.
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