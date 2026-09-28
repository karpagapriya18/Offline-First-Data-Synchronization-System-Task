from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), default="user", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    records = relationship("Record", back_populates="owner", cascade="all, delete-orphan")
    sync_operations = relationship("LocalSyncOperation", back_populates="owner", cascade="all, delete-orphan")


class Record(Base):
    __tablename__ = "records"
    __table_args__ = (UniqueConstraint("user_id", "client_id", name="uq_records_user_client_id"),)

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(String(100), index=True, nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    version = Column(Integer, default=1, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    owner = relationship("User", back_populates="records")
    sync_history = relationship("SyncHistory", back_populates="record")
    conflicts = relationship("Conflict", back_populates="record")


class LocalSyncOperation(Base):
    __tablename__ = "local_sync_operations"
    __table_args__ = (UniqueConstraint("user_id", "operation_id", name="uq_sync_operation_user_operation"),)

    id = Column(Integer, primary_key=True, index=True)
    operation_id = Column(String(100), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    client_id = Column(String(100), nullable=False, index=True)
    operation_type = Column(Enum("create", "update", "delete"), nullable=False)
    payload = Column(JSON, nullable=True)
    base_version = Column(Integer, default=0, nullable=False)
    status = Column(Enum("pending", "synced", "failed", "conflict", "duplicate"), default="pending", nullable=False)
    error_details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    owner = relationship("User", back_populates="sync_operations")


class SyncHistory(Base):
    __tablename__ = "sync_history"

    id = Column(Integer, primary_key=True, index=True)
    sync_id = Column(String(100), nullable=False, index=True)
    operation_id = Column(String(100), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    record_id = Column(Integer, ForeignKey("records.id"), nullable=True)
    client_id = Column(String(100), nullable=False, index=True)
    operation_type = Column(Enum("create", "update", "delete"), nullable=False)
    sync_status = Column(Enum("synced", "failed", "conflict", "duplicate"), nullable=False)
    error_details = Column(Text, nullable=True)
    conflict_status = Column(String(50), default="none", nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    record = relationship("Record", back_populates="sync_history")


class Conflict(Base):
    __tablename__ = "conflicts"

    id = Column(Integer, primary_key=True, index=True)
    sync_id = Column(String(100), nullable=False, index=True)
    operation_id = Column(String(100), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    record_id = Column(Integer, ForeignKey("records.id"), nullable=True)
    client_id = Column(String(100), nullable=False, index=True)
    strategy = Column(Enum("last_write_wins", "server_wins", "client_wins", "manual"), default="manual", nullable=False)
    status = Column(Enum("open", "resolved"), default="open", nullable=False)
    server_version = Column(Integer, nullable=True)
    client_version = Column(Integer, nullable=True)
    server_payload = Column(JSON, nullable=True)
    client_payload = Column(JSON, nullable=True)
    resolution = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    record = relationship("Record", back_populates="conflicts")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(String(100), nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
