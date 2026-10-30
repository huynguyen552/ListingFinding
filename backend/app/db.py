import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .settings import database_url

DATABASE_URL = database_url(
    os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://leadfinder:leadfinder@localhost/leadfinder"
    )
)
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    **({"connect_args": {"check_same_thread": False}} if DATABASE_URL.startswith("sqlite") else {}),
    **({"pool_size": 2, "max_overflow": 2} if not DATABASE_URL.startswith("sqlite") else {}),
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    with SessionLocal() as session:
        yield session
