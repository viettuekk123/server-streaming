"""Script khởi tạo schema cho demo. Không xóa bảng hoặc dữ liệu đã có."""

import pyodbc

from app import models  # noqa: F401 — Đăng ký model trước create_all.
from app.config import settings
from app.database import Base, engine

if not settings.db_name.replace("_", "").isalnum():
    raise ValueError("DB_NAME chỉ gồm chữ, số và dấu gạch dưới")
connection = pyodbc.connect(
    f"DRIVER={{{settings.db_driver}}};SERVER={settings.db_host};DATABASE=master;"
    f"UID={settings.db_user};PWD={{{settings.db_password.replace('}', '}}')}}};TrustServerCertificate=yes;",
    autocommit=True,
)
with connection.cursor() as cursor:
    cursor.execute(f"IF DB_ID(?) IS NULL CREATE DATABASE [{settings.db_name}]", settings.db_name)
connection.close()
Base.metadata.create_all(engine)
print("Database và schema đã sẵn sàng.")
