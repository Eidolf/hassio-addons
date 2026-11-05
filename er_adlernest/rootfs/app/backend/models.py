"""Database models and migrations for ER-Adlernest."""
import logging
import os
import sqlite3
from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from db_migrations import migrate_database

logger = logging.getLogger("adlernest.models")

DB_PATH = os.getenv("DB_PATH", "/data/db/adlernest.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

Base = declarative_base()


class AppSetting(Base):
    __tablename__ = "settings"
    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)


class Camera(Base):
    __tablename__ = "cameras"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    source_type = Column(String(50), default="rtsp")
    stream_url = Column(String(500), nullable=True)
    substream_url = Column(String(500), nullable=True)
    ha_entity_id = Column(String(200), nullable=True)
    folder_mapping = Column(String(255), nullable=True)
    fps = Column(Integer, default=15)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Recording(Base):
    __tablename__ = "recordings"
    id = Column(Integer, primary_key=True, index=True)
    camera_name = Column(String(100), index=True, nullable=False)
    file_path = Column(String(1000), unique=True, index=True, nullable=False)
    relative_path = Column(String(1000), nullable=False)
    filename = Column(String(255), nullable=False)
    file_size = Column(Integer, default=0)
    duration = Column(Float, default=0.0)
    width = Column(Integer, default=1920)
    height = Column(Integer, default=1080)
    codec = Column(String(50), default="h264")
    recorded_at = Column(DateTime, index=True, nullable=False)
    event_type = Column(String(50), default="regular")
    thumbnail_path = Column(String(1000), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------------------------------------------------------------------------
# Schema migrations (including legacy NOT NULL camera URLs)
# ---------------------------------------------------------------------------
def run_migrations() -> None:
    """Upgrade the SQLite schema; fatal on unexpected errors."""
    try:
        migrate_database(DB_PATH)
    except sqlite3.Error as exc:
        logger.critical("DB migration failed – cannot start safely: %s", exc)
        raise SystemExit(1) from exc


# Run on import so the DB is always up-to-date
run_migrations()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_setting(key: str, default: str = "") -> str:
    db = SessionLocal()
    try:
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        return row.value if row else default
    finally:
        db.close()


def set_setting(key: str, value: str) -> None:
    db = SessionLocal()
    try:
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        if row:
            row.value = value
        else:
            db.add(AppSetting(key=key, value=value))
        db.commit()
    finally:
        db.close()
