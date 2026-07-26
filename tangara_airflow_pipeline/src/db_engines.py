
import os

from sqlalchemy import create_engine


DATABASE_URL = os.environ.get("DATABASE_URL") or (
    "postgresql+psycopg2://ai_admin:ai_admin@postgres:5432/ai_project"
)

DATABASE_URL_RENDER = os.environ.get("DATABASE_URL_RENDER", "").strip()


def get_engines():

    engines = [("LOCAL", create_engine(DATABASE_URL))]

    if DATABASE_URL_RENDER:

        engines.append(
            ("RENDER", create_engine(DATABASE_URL_RENDER))
        )

    return engines


def get_local_engine():

    return create_engine(DATABASE_URL)