"""
Script: load_train_test_csv_data.py

Descripcion:
    Carga a la capa Silver (PostgreSQL) los datasets de
    entrenamiento/prueba (train/test) que ya vienen preparados
    como archivos CSV, uno por sensor y por split, ubicados en la
    carpeta `datos_train_test/` en la raiz del proyecto:

        Sensor 2FF6 Train.csv   Sensor 2FF6 Test.csv
        Sensor F1AE Train.csv   Sensor F1AE Test.csv
        Sensor 1712 Train.csv   Sensor 1712 Test.csv
        Sensor 307A Train.csv   Sensor 307A Test.csv

    A diferencia del resto del pipeline (que extrae en vivo desde
    ClickHouse), estos archivos son estaticos: se cargan tal cual
    vienen, con sus columnas originales, sin transformar.

    Tablas resultantes en Silver:

        silver.sensor_2ff6_train   silver.sensor_2ff6_test
        silver.sensor_f1ae_train   silver.sensor_f1ae_test
        silver.sensor_1712_train   silver.sensor_1712_test
        silver.sensor_307a_train   silver.sensor_307a_test

Ejecucion:
    python load_train_test_csv_data.py
"""

import os

import pandas as pd

from sqlalchemy import create_engine, text


DATA_DIR = "/opt/airflow/datos_train_test"

SENSOR_CODES = [
    "2FF6",
    "F1AE",
    "1712",
    "307A",
]

SPLITS = [
    "Train",
    "Test",
]


def load_train_test_data():

    print("=== INICIANDO CARGA DE DATASETS TRAIN/TEST A SILVER ===")

    engine = create_engine(
        "postgresql+psycopg2://ai_admin:ai_admin@postgres:5432/ai_project"
    )

    with engine.begin() as conn:

        conn.execute(
            text(
                """
                CREATE SCHEMA IF NOT EXISTS silver
                """
            )
        )

    loaded_files = 0
    missing_files = 0

    for sensor_code in SENSOR_CODES:

        for split in SPLITS:

            file_name = f"Sensor {sensor_code} {split}.csv"
            file_path = os.path.join(DATA_DIR, file_name)

            if not os.path.exists(file_path):

                print(f"[AVISO] No encontrado: {file_path}")
                missing_files += 1
                continue

            df = pd.read_csv(file_path)

            table_name = f"sensor_{sensor_code.lower()}_{split.lower()}"

            df.to_sql(
                name=table_name,
                schema="silver",
                con=engine,
                if_exists="replace",
                index=False
            )

            print(
                f"Tabla silver.{table_name}: "
                f"{len(df)} registros cargados desde '{file_name}'"
            )

            loaded_files += 1

    print("=== CARGA DE DATASETS TRAIN/TEST COMPLETADA ===")
    print(f"Archivos cargados: {loaded_files}")
    print(f"Archivos no encontrados: {missing_files}")

    print("=== PROCESO FINALIZADO EXITOSAMENTE ===")


if __name__ == "__main__":

    load_train_test_data()
