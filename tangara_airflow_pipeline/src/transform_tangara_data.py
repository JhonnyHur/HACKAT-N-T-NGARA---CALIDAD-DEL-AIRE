"""
Script: transform_tangara_data.py

Descripcion:
    Limpia, valida y transforma los datos crudos de Temperatura,
    Humedad, PM2.5 y ubicacion (geohash) de la capa Bronze
    (bronze.tangara_sensores_api_data), y los deja listos para
    consumo analitico en la capa Silver, generando UNA TABLA POR
    SENSOR, con UN PROMEDIO POR HORA (todas las lecturas que caen
    dentro de una misma hora, ej. de 1pm a 2pm, se promedian y
    quedan como un unico dato en esa hora, ej. la 1pm):

        silver.stg_tangara_sensor_2ff6
        silver.stg_tangara_sensor_f1ae
        silver.stg_tangara_sensor_1712
        silver.stg_tangara_sensor_307a

    Cada tabla queda con las siguientes columnas:
        - Fecha & Hora
        - Temperatura (°C)
        - Humedad (%)
        - PM2.5 (µg/m³)
        - Latitud
        - Longitud

    Incluye:
        - Validacion de rangos fisicamente posibles.
        - Deduplicacion por sensor + timestamp.
        - Mapeo del nombre completo del sensor en ClickHouse
          (ej. D29ESP32DED2FF6) a su codigo corto (ej. 2FF6), usado
          para nombrar cada tabla.
        - Decodificacion de la columna "geo" (geohash) a Latitud y
          Longitud, usando la libreria `pygeohash`.
        - Filtro de "hora completa": una hora solo se promedia y se
          publica en silver una vez que ya termino por completo (mas
          un pequeno margen de seguridad, ver HORA_MARGEN_MINUTOS),
          para no mostrar un promedio calculado con datos parciales.
          Ej.: si ahora son las 11:xx, la hora 11 (11:00-12:00)
          todavia no aparece en silver; recien se ve una vez pasadas
          las 12:05 (con el margen por defecto de 5 minutos).

Variables de entorno:
    DATABASE_URL (opcional; Postgres origen/destino. Si no se
    define, usa el Postgres local del docker-compose)

Ejecucion:
    python transform_tangara_data.py
"""

import os

from datetime import datetime, timedelta

from zoneinfo import ZoneInfo

import pandas as pd

import pygeohash as pgh

from sqlalchemy import create_engine, text


# Postgres origen/destino: por defecto el del docker-compose local
# (servicio "postgres"). Se puede sobreescribir con DATABASE_URL
# en el .env para apuntar, por ejemplo, a un Postgres administrado
# en Render.
DATABASE_URL = os.environ.get("DATABASE_URL") or (
    "postgresql+psycopg2://ai_admin:ai_admin@postgres:5432/ai_project"
)

# "Fecha & Hora" en bronze ya viene en hora de Cali/Colombia (la
# conversion se hace en extract_tangara_data.py), por eso aqui la
# hora actual tambien se calcula en esa misma zona horaria.
CALI_TZ = ZoneInfo("America/Bogota")

# Margen de seguridad (en minutos) que se espera DESPUES de que una
# hora termina, antes de darla por completa y promediarla. Da chance
# a que terminen de llegar a bronze lecturas tardias de esa hora.
HORA_MARGEN_MINUTOS = 5

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


def decode_geohash(geohash_value):
    """
    Decodifica un geohash (ej. "d2b4z9x...") a una tupla
    (latitud, longitud). Si el valor viene vacio, nulo, o no se
    puede decodificar (geohash invalido), devuelve (None, None) en
    vez de lanzar una excepcion, para no tumbar toda la
    transformacion por un solo registro con geo mal formado.
    """

    if pd.isna(geohash_value):

        return None, None

    geohash_value = str(geohash_value).strip()

    if not geohash_value:

        return None, None

    try:

        latitude, longitude = pgh.decode(geohash_value)

        return latitude, longitude

    except Exception as error:

        print(
            f"[AVISO] Geohash invalido '{geohash_value}': {error}"
        )

        return None, None


def transform_api_data():

    print("=== INICIANDO TRANSFORMACION DE DATOS TANGARA ===")

    engine = create_engine(DATABASE_URL)

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

    # PM2.5 no se usa para descartar registros (puede venir nulo
    # ocasionalmente); solo se descartan valores negativos, que son
    # fisicamente imposibles, dejando el resto de la fila intacta.

    invalid_pm25_count = (df["pm25"] < 0).sum()

    if invalid_pm25_count > 0:

        print(
            f"[AVISO] PM2.5 negativo en {invalid_pm25_count} "
            "registros: se descarta solo el valor de PM2.5 "
            "(se deja como nulo), no la fila completa."
        )

        df.loc[df["pm25"] < 0, "pm25"] = None

    # =====================================
    # RENOMBRAR / ESTANDARIZAR COLUMNAS
    # =====================================

    transformed_df = pd.DataFrame()

    transformed_df["Fecha & Hora"] = pd.to_datetime(df["time"])
    transformed_df["Sensor"] = df["name"].apply(map_sensor_code)
    transformed_df["Temperatura (°C)"] = df["tmp"].round(1)
    transformed_df["Humedad (%)"] = df["hum"].round(1)
    transformed_df["PM2.5 (µg/m³)"] = df["pm25"].round(1)

    # =====================================
    # DECODIFICACION DE GEOHASH -> LATITUD / LONGITUD
    # =====================================

    print("=== DECODIFICANDO GEOHASH (geo -> Latitud / Longitud) ===")

    lat_long = df["geo"].apply(decode_geohash)

    transformed_df["Latitud"] = [
        coords[0] for coords in lat_long
    ]
    transformed_df["Longitud"] = [
        coords[1] for coords in lat_long
    ]

    decoded_count = transformed_df["Latitud"].notna().sum()

    print(
        f"Geohash decodificados correctamente: "
        f"{decoded_count} / {len(transformed_df)}"
    )

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
        "PM2.5 (µg/m³)",
    ]

    transformed_df[numeric_columns] = (
        transformed_df[numeric_columns].round(1)
    )

    coordinate_columns = [
        "Latitud",
        "Longitud",
    ]

    transformed_df[coordinate_columns] = (
        transformed_df[coordinate_columns].round(6)
    )

    print(f"Registros antes de promediar por hora: {len(transformed_df)}")

    # =====================================
    # PROMEDIO POR HORA
    # (todas las lecturas que caen dentro de una misma hora, ej.
    # de 1pm a 2pm, se promedian y quedan como un unico dato en
    # esa hora, ej. la 1pm. Latitud/Longitud no se promedian:
    # se conserva la primera, ya que la ubicacion del sensor no
    # cambia dentro de la hora)
    # =====================================

    transformed_df["Hora_Referencia"] = (
        transformed_df["Fecha & Hora"].dt.floor("h")
    )

    transformed_df = (
        transformed_df
        .groupby(["Sensor", "Hora_Referencia"], as_index=False)
        .agg({
            "Temperatura (°C)": "mean",
            "Humedad (%)": "mean",
            "PM2.5 (µg/m³)": "mean",
            "Latitud": "first",
            "Longitud": "first",
        })
    )

    transformed_df = transformed_df.rename(
        columns={"Hora_Referencia": "Fecha & Hora"}
    )

    # =====================================
    # FILTRO DE HORA COMPLETA
    # Una hora (ej. 11:00-12:00) solo se publica en silver una vez
    # que ya termino por completo, mas un pequeno margen de espera
    # (HORA_MARGEN_MINUTOS) para datos tardios. Ej.: si ahora son
    # las 11:xx, la hora 11 todavia no aparece; recien se ve pasadas
    # las 12:05 (con el margen por defecto de 5 minutos).
    # =====================================

    ahora_cali = datetime.now(CALI_TZ).replace(tzinfo=None)

    limite_hora_completa = ahora_cali - timedelta(
        minutes=HORA_MARGEN_MINUTOS
    )

    registros_antes_filtro_hora = len(transformed_df)

    transformed_df = transformed_df[
        transformed_df["Fecha & Hora"] + timedelta(hours=1)
        <= limite_hora_completa
    ]

    registros_despues_filtro_hora = len(transformed_df)

    print("=== FILTRO DE HORA COMPLETA ===")
    print(f"Hora actual (Cali): {ahora_cali}")
    print(
        "Se publican horas que terminaron antes de: "
        f"{limite_hora_completa}"
    )
    print(
        "Registros descartados (hora aun incompleta): "
        f"{registros_antes_filtro_hora - registros_despues_filtro_hora}"
    )

    numeric_columns_after_avg = [
        "Temperatura (°C)",
        "Humedad (%)",
        "PM2.5 (µg/m³)",
    ]

    transformed_df[numeric_columns_after_avg] = (
        transformed_df[numeric_columns_after_avg].round(1)
    )

    transformed_df = transformed_df[[
        "Fecha & Hora",
        "Sensor",
        "Temperatura (°C)",
        "Humedad (%)",
        "PM2.5 (µg/m³)",
        "Latitud",
        "Longitud",
    ]]

    print(f"Registros tras promediar por hora: {len(transformed_df)}")

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