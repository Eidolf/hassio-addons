import os
import json
import asyncio
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DB_PATH = os.getenv("DB_PATH", "/data/db/adlernest.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

Base = declarative_base()

class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    source_type = Column(String(50), default="rtsp")  # rtsp, reolink, ha_camera, onvif, mjpeg
    stream_url = Column(String(500), nullable=False)
    substream_url = Column(String(500), nullable=True)
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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

