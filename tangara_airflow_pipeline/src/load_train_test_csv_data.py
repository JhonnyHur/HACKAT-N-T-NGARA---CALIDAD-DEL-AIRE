

import os

import pandas as pd

from sqlalchemy import text

from db_engines import get_engines


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

    loaded_files = 0
    missing_files = 0

    for label, engine in get_engines():

        with engine.begin() as conn:

            conn.execute(
                text(
                    """
                    CREATE SCHEMA IF NOT EXISTS silver
                    """
                )
            )

        for sensor_code in SENSOR_CODES:

            for split in SPLITS:

                file_name = f"Sensor {sensor_code} {split}.csv"
                file_path = os.path.join(DATA_DIR, file_name)

                if not os.path.exists(file_path):

                    print(f"[AVISO] No encontrado: {file_path}")
                    missing_files += 1
                    continue

                df = pd.read_csv(file_path)

                table_name = (
                    f"sensor_{sensor_code.lower()}_{split.lower()}"
                )

                df.to_sql(
                    name=table_name,
                    schema="silver",
                    con=engine,
                    if_exists="replace",
                    index=False
                )

                print(
                    f"[{label}] Tabla silver.{table_name}: "
                    f"{len(df)} registros cargados desde "
                    f"'{file_name}'"
                )

                loaded_files += 1

    print("=== CARGA DE DATASETS TRAIN/TEST COMPLETADA ===")
    print(f"Archivos cargados: {loaded_files}")
    print(f"Archivos no encontrados: {missing_files}")

    print("=== PROCESO FINALIZADO EXITOSAMENTE ===")


if __name__ == "__main__":

    load_train_test_data()