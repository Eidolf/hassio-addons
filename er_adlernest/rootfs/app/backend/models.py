import os
import json
import sqlite3
import logging
from datetime import datetime
from typing import List, Optional
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, create_engine, Text, text
from sqlalchemy.orm import declarative_base, sessionmaker

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
    source_type = Column(String(50), default="rtsp")  # ha_camera, rtsp, reolink, onvif, mjpeg
    stream_url = Column(String(500), nullable=True)
    substream_url = Column(String(500), nullable=True)
    ha_entity_id = Column(String(200), nullable=True) # e.g. camera.driveway
    folder_mapping = Column(String(255), nullable=True) # Subfolder name inside storage, e.g. "Holzhuette"
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
    event_type = Column(String(50), default="regular") # regular, motion, person, vehicle, doorbell
    thumbnail_path = Column(String(1000), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def run_migrations():
    """Ensure older DB schemas are upgraded with missing columns (e.g. ha_entity_id, folder_mapping)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check columns of cameras table
        cursor.execute("PRAGMA table_info(cameras);")
        columns = [row[1] for row in cursor.fetchall()]
        
        if columns:
            if "ha_entity_id" not in columns:
                logger.info("Migrating DB: Adding ha_entity_id column to cameras")
                cursor.execute("ALTER TABLE cameras ADD COLUMN ha_entity_id VARCHAR(200);")
            if "folder_mapping" not in columns:
                logger.info("Migrating DB: Adding folder_mapping column to cameras")
                cursor.execute("ALTER TABLE cameras ADD COLUMN folder_mapping VARCHAR(255);")
            conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Migration error: {e}")

# Run automatic schema migration on import
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
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        return setting.value if setting else default
    finally:
        db.close()

def set_setting(key: str, value: str):
    db = SessionLocal()
    try:
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        if setting:
            setting.value = value
        else:
            setting = AppSetting(key=key, value=value)
            db.add(setting)
        db.commit()
    finally:
        db.close()
