"""
SQLAlchemy ORM models and database helpers.
"""
import os
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./emg_hand.db")


def _build_engine(url: str):
    options = {
        "pool_pre_ping": True,
    }
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **options)


engine = _build_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    openid = Column(String(64), unique=True, index=True, nullable=True)
    phone = Column(String(20), unique=True, index=True, nullable=True)
    username = Column(String(64), unique=True, index=True, nullable=True)
    password_hash = Column(String(256), default="")
    role = Column(String(16), default="user")
    name = Column(String(64), default="用户")
    avatar_url = Column(String(512), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    devices = relationship("Device", back_populates="user")
    health_data = relationship("HealthRecord", back_populates="user")
    posts = relationship("ForumPost", back_populates="author")
    comments = relationship("ForumComment", back_populates="author", foreign_keys="ForumComment.user_id")
    emg_sessions = relationship("EmgCollectionSession", back_populates="user")
    emg_batches = relationship("EmgCollectionBatch", back_populates="user")


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    hardware_id = Column(String(64), unique=True, index=True)
    device_name = Column(String(128), default="")
    transport = Column(String(16), default="ble")
    board_token = Column(String(128), default="")
    wifi_host = Column(String(128), default="")
    wifi_port = Column(Integer, default=0)
    status = Column(String(16), default="offline")
    firmware_version = Column(String(64), default="")
    last_ip = Column(String(64), default="")
    battery_level = Column(Integer, nullable=True)
    signal_strength = Column(Integer, nullable=True)
    telemetry_json = Column(Text, default="{}")
    pending_command_json = Column(Text, default="")
    last_command_ack_json = Column(Text, default="")
    bind_time = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="devices")


class HealthRecord(Base):
    __tablename__ = "health_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rms_value = Column(Float, default=0.0)
    side_presure = Column(Float, default=0.0)
    muscle_status = Column(String(32), default="正常")
    diagnostics = Column(Text, default="")
    recorded_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="health_data")


class TrainingSession(Base):
    __tablename__ = "training_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    gesture_name = Column(String(64), default="")
    file_path = Column(String(512), default="")
    total_chunks = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class EmgCollectionSession(Base):
    __tablename__ = "emg_collection_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    hardware_id = Column(String(64), index=True, default="")
    transport = Column(String(16), default="wifi")
    source = Column(String(32), default="wifi")
    gesture_name = Column(String(64), default="")
    sample_rate_hz = Column(Integer, default=0)
    channel_count = Column(Integer, default=0)
    batch_count = Column(Integer, default=0)
    total_samples = Column(Integer, default=0)
    rms_value = Column(Float, default=0.0)
    file_path = Column(String(512), default="")
    preview_json = Column(Text, default="[]")
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="emg_sessions")


class EmgCollectionBatch(Base):
    __tablename__ = "emg_collection_batches"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    hardware_id = Column(String(64), index=True, default="")
    transport = Column(String(16), default="wifi")
    sequence_no = Column(Integer, default=0)
    sample_count = Column(Integer, default=0)
    channel_count = Column(Integer, default=0)
    sample_rate_hz = Column(Integer, default=0)
    rms_value = Column(Float, default=0.0)
    samples_json = Column(Text, default="[]")
    is_final = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="emg_batches")


class ForumPost(Base):
    __tablename__ = "forum_posts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    image_urls = Column(Text, default="")
    like_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    author = relationship("User", back_populates="posts")
    comments = relationship("ForumComment", back_populates="post")
    likes = relationship("PostLike", back_populates="post")


class ForumComment(Base):
    __tablename__ = "forum_comments"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("forum_posts.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("forum_comments.id"), nullable=True)
    reply_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    post = relationship("ForumPost", back_populates="comments")
    author = relationship("User", back_populates="comments", foreign_keys=[user_id])
    parent = relationship("ForumComment", remote_side=[id], back_populates="replies")
    replies = relationship("ForumComment", back_populates="parent")
    reply_to_user = relationship("User", foreign_keys=[reply_to_user_id])


class PostLike(Base):
    __tablename__ = "post_likes"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("forum_posts.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    post = relationship("ForumPost", back_populates="likes")


class SmsCode(Base):
    __tablename__ = "sms_codes"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(20), index=True)
    code = Column(String(6))
    expired_at = Column(DateTime)
    used = Column(Boolean, default=False)


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True, index=True)
    hardware_id = Column(String(64), index=True, default="")
    error_code = Column(String(64), index=True, default="")
    error_msg = Column(Text, default="")
    level = Column(String(16), default="warning")
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)
    _ensure_user_columns()
    _ensure_device_columns()
    _ensure_forum_comment_columns()


def _ensure_user_columns():
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("users")}
    column_ddls = {
        "username": "ALTER TABLE users ADD COLUMN username VARCHAR(64)",
        "password_hash": "ALTER TABLE users ADD COLUMN password_hash VARCHAR(256) DEFAULT ''",
        "role": "ALTER TABLE users ADD COLUMN role VARCHAR(16) DEFAULT 'user'",
    }

    with engine.begin() as conn:
        for name, ddl in column_ddls.items():
            if name not in existing:
                conn.execute(text(ddl))


def _ensure_device_columns():
    inspector = inspect(engine)
    if "devices" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("devices")}
    column_ddls = {
        "device_name": "ALTER TABLE devices ADD COLUMN device_name VARCHAR(128) DEFAULT ''",
        "transport": "ALTER TABLE devices ADD COLUMN transport VARCHAR(16) NOT NULL DEFAULT 'ble'",
        "board_token": "ALTER TABLE devices ADD COLUMN board_token VARCHAR(128) DEFAULT ''",
        "wifi_host": "ALTER TABLE devices ADD COLUMN wifi_host VARCHAR(128) DEFAULT ''",
        "wifi_port": "ALTER TABLE devices ADD COLUMN wifi_port INTEGER DEFAULT 0",
        "status": "ALTER TABLE devices ADD COLUMN status VARCHAR(16) DEFAULT 'offline'",
        "firmware_version": "ALTER TABLE devices ADD COLUMN firmware_version VARCHAR(64) DEFAULT ''",
        "last_ip": "ALTER TABLE devices ADD COLUMN last_ip VARCHAR(64) DEFAULT ''",
        "battery_level": "ALTER TABLE devices ADD COLUMN battery_level INTEGER",
        "signal_strength": "ALTER TABLE devices ADD COLUMN signal_strength INTEGER",
        "telemetry_json": "ALTER TABLE devices ADD COLUMN telemetry_json TEXT DEFAULT '{}'",
        "pending_command_json": "ALTER TABLE devices ADD COLUMN pending_command_json TEXT DEFAULT ''",
        "last_command_ack_json": "ALTER TABLE devices ADD COLUMN last_command_ack_json TEXT DEFAULT ''",
        "last_seen_at": "ALTER TABLE devices ADD COLUMN last_seen_at DATETIME",
        "updated_at": "ALTER TABLE devices ADD COLUMN updated_at DATETIME",
    }

    with engine.begin() as conn:
        for name, ddl in column_ddls.items():
            if name not in existing:
                conn.execute(text(ddl))


def _ensure_forum_comment_columns():
    inspector = inspect(engine)
    if "forum_comments" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("forum_comments")}
    column_ddls = {
        "parent_id": "ALTER TABLE forum_comments ADD COLUMN parent_id INTEGER",
        "reply_to_user_id": "ALTER TABLE forum_comments ADD COLUMN reply_to_user_id INTEGER",
    }

    with engine.begin() as conn:
        for name, ddl in column_ddls.items():
            if name not in existing:
                conn.execute(text(ddl))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
