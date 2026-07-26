"""
Modulo: db_engines.py

Descripcion:
    Punto unico donde se decide a que Postgres(s) escribe el
    pipeline. Siempre incluye el Postgres LOCAL (el que levanta
    este mismo docker-compose, servicio "postgres"), y ademas,
    SOLO SI se define la variable de entorno DATABASE_URL_RENDER
    en el .env, tambien escribe en un segundo Postgres externo
    (por ejemplo, uno administrado en Render).

    Si DATABASE_URL_RENDER se deja vacio, el pipeline se comporta
    exactamente igual que antes: escribe unicamente en el Postgres
    local.

    El resto de los scripts (extract, transform, load_train_test,
    predict) usan get_engines() en vez de crear su propio engine
    a mano, para que escribir "en los dos Postgres a la vez" sea
    un cambio centralizado en un solo archivo.

Variables de entorno (ver env.example):
    DATABASE_URL          Postgres LOCAL / principal. Si no se
                          define, usa el Postgres del
                          docker-compose (servicio "postgres").
    DATABASE_URL_RENDER   Postgres de RENDER (opcional). Si se
                          deja vacio, no se escribe ahi.
"""

import os

from sqlalchemy import create_engine


DATABASE_URL = os.environ.get("DATABASE_URL") or (
    "postgresql+psycopg2://ai_admin:ai_admin@postgres:5432/ai_project"
)

DATABASE_URL_RENDER = os.environ.get("DATABASE_URL_RENDER", "").strip()


def get_engines():
    """
    Devuelve la lista de engines de SQLAlchemy a los que hay que
    escribir: siempre el local, y el de Render solo si esta
    configurado. Se crea un engine nuevo en cada llamada (barato,
    SQLAlchemy solo abre la conexion real cuando se usa).
    """

    engines = [("LOCAL", create_engine(DATABASE_URL))]

    if DATABASE_URL_RENDER:

        engines.append(
            ("RENDER", create_engine(DATABASE_URL_RENDER))
        )

    return engines


def get_local_engine():
    """
    Engine del Postgres local unicamente. Se usa para las LECTURAS
    del pipeline (ej. leer bronze para transformar, leer silver
    para predecir), ya que el local es siempre la fuente de verdad
    que el pipeline consulta a si mismo.
    """

    return create_engine(DATABASE_URL)