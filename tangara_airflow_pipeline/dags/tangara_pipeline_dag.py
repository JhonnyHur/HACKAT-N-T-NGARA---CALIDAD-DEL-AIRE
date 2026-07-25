from datetime import datetime, timedelta

import sys

sys.path.append("/opt/airflow/src")

from airflow import DAG
from airflow.operators.python import PythonOperator

from extract_tangara_data import (
    extract_api_data,
    save_raw_data,
    load_to_bronze
)

from transform_tangara_data import (
    transform_api_data
)

from load_train_test_csv_data import (
    load_train_test_data
)


default_args = {
    "owner": "TEAM",
    "depends_on_past": False,
    "start_date": datetime(2026, 1, 1),
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


dag = DAG(
    "tangara_pipeline",
    default_args=default_args,
    description="Pipeline Medallon Temperatura y Humedad - Tangara",
    schedule_interval="@hourly",
    catchup=False,
    tags=["bronze", "silver", "tangara", "clickhouse"]
)


def bronze_pipeline():

    df = extract_api_data()

    if len(df) > 0:

        save_raw_data(df)

        load_to_bronze(df)

    else:

        print("Sin registros nuevos en la ventana consultada.")


def silver_pipeline():

    transform_api_data()


def train_test_pipeline():

    load_train_test_data()


extract_and_load_bronze_task = PythonOperator(
    task_id="extract_and_load_bronze_tangara_data",
    python_callable=bronze_pipeline,
    dag=dag,
)


transform_and_load_silver_task = PythonOperator(
    task_id="transform_and_load_silver_tangara_data",
    python_callable=silver_pipeline,
    dag=dag,
)


load_train_test_csv_task = PythonOperator(
    task_id="load_train_test_csv_to_silver",
    python_callable=train_test_pipeline,
    dag=dag,
)


extract_and_load_bronze_task >> transform_and_load_silver_task
