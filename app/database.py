from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


def now() -> datetime:
    # SQL Server DATETIME2 lưu UTC không kèm timezone; API chuyển sang ISO UTC.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


url = URL.create(
    "mssql+pyodbc",
    username=settings.db_user,
    password=settings.db_password,
    host=settings.db_host,
    database=settings.db_name,
    query={"driver": settings.db_driver, "TrustServerCertificate": "yes"},
)
engine = create_engine(
    url, pool_pre_ping=True, use_setinputsizes=settings.db_driver != "SQL Server"
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        yield db
