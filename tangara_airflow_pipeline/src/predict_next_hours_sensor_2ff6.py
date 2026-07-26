
import pandas as pd

from sqlalchemy import text

from db_engines import get_engines

from predict_pm25_sensor_2ff6 import (
    GOLD_COLUMNS,
    GOLD_SCHEMA,
    GOLD_TABLE,
    LAGS,
    FEATURE_COLUMNS,
    SILVER_SCHEMA,
    SILVER_TABLE,
    ensure_gold_schema,
    gold_table_exists,
    load_model,
    load_silver_data,
)


# Cuantas horas hacia adelante se pronostican, de forma recursiva,
# en cada corrida de este DAG.
N_HORAS_PREDICCION = 6


def predict_next_hours(model, historial_df, n_horas=N_HORAS_PREDICCION):


    if len(historial_df) < max(LAGS):

        print(
            "[AVISO] No hay suficiente historico "
            f"(se necesitan al menos {max(LAGS)} horas reales) "
            "para generar el pronostico de las proximas horas."
        )

        return None

    ultima = historial_df.iloc[-1].copy()

    historial_pm25 = list(historial_df["PM2.5 (µg/m³)"].values)

    predicciones = []

    print(
        f"=== PRONOSTICO RECURSIVO: proximas {n_horas} horas "
        "(sensor 2FF6) ==="
    )

    for i in range(n_horas):

        nueva_fecha = ultima["Fecha & Hora"] + pd.Timedelta(hours=1)

        entrada = pd.DataFrame({
            "Temperatura_(°C)_2FF6": [ultima["Temperatura (°C)"]],
            "Humedad_(%)_2FF6": [ultima["Humedad (%)"]],
            "PM2.5_lag_1": [historial_pm25[-1]],
            "PM2.5_lag_2": [historial_pm25[-2]],
            "PM2.5_lag_3": [historial_pm25[-3]],
            "PM2.5_lag_6": [historial_pm25[-6]],
            "PM2.5_lag_12": [historial_pm25[-12]],
            "PM2.5_lag_24": [historial_pm25[-24]],
        })[FEATURE_COLUMNS]

        pred = float(model.predict(entrada)[0])

        historial_pm25.append(pred)

        print(
            f"Hora +{i + 1} ({nueva_fecha}): "
            f"PM2.5 pronosticado = {pred:.2f} µg/m³"
        )

        predicciones.append({
            "Fecha & Hora": nueva_fecha,
            "Temperatura (°C)": ultima["Temperatura (°C)"],
            "Humedad (%)": ultima["Humedad (%)"],
            "PM2.5_Real (µg/m³)": None,
            "PM2.5_lag_1": round(historial_pm25[-2], 2),
            "PM2.5_lag_2": round(historial_pm25[-3], 2),
            "PM2.5_lag_3": round(historial_pm25[-4], 2),
            "PM2.5_lag_6": round(historial_pm25[-7], 2),
            "PM2.5_lag_12": round(historial_pm25[-13], 2),
            "PM2.5_lag_24": round(historial_pm25[-25], 2),
            "Latitud": ultima["Latitud"],
            "Longitud": ultima["Longitud"],
            "PM2.5_Predicho (µg/m³)": round(pred, 2),
        })

        ultima["Fecha & Hora"] = nueva_fecha

    return pd.DataFrame(predicciones)[GOLD_COLUMNS]


def load_forecast_to_gold(engine, forecast_df):


    ensure_gold_schema(engine)

    if gold_table_exists(engine):

        with engine.begin() as conn:

            conn.execute(
                text(
                    f'''
                    DELETE FROM {GOLD_SCHEMA}."{GOLD_TABLE}"
                    WHERE "PM2.5_Real (µg/m³)" IS NULL
                    '''
                )
            )

    forecast_df.to_sql(
        name=GOLD_TABLE,
        schema=GOLD_SCHEMA,
        con=engine,
        if_exists="append",
        index=False,
    )

    print(
        f"Tabla {GOLD_SCHEMA}.{GOLD_TABLE}: "
        f"{len(forecast_df)} filas de pronostico insertadas "
        "(filas historicas, si existen, no se tocan)"
    )


def run_forecast_pipeline():

    print(
        "=== INICIANDO PRONOSTICO DE PROXIMAS HORAS "
        "(PM2.5, SENSOR 2FF6) ==="
    )

    historial_df = load_silver_data()

    if len(historial_df) == 0:

        print(
            f"[AVISO] {SILVER_SCHEMA}.{SILVER_TABLE} esta vacia. "
            "Todavia no hay datos para pronosticar."
        )

        return

    model = load_model()

    forecast_df = predict_next_hours(
        model, historial_df, N_HORAS_PREDICCION
    )

    if forecast_df is None or len(forecast_df) == 0:

        return

    for label, engine in get_engines():

        print(f"--- Guardando pronostico en Gold ({label}) ---")

        load_forecast_to_gold(engine, forecast_df)

    print("=== PRONOSTICO COMPLETADO ===")
    print("=== PROCESO FINALIZADO EXITOSAMENTE ===")


if __name__ == "__main__":

    run_forecast_pipeline()