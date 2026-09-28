from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=8)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    name: str | None = None
    password: str | None = Field(default=None, min_length=8)


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class RecordCreate(BaseModel):
    client_id: str
    title: str
    content: str | None = None


class RecordUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    version: int


class RecordResponse(BaseModel):
    id: int
    client_id: str
    title: str
    content: str | None = None
    user_id: int
    version: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SyncChange(BaseModel):
    operation_id: str
    client_id: str
    operation: Literal["create", "update", "delete"]
    title: str | None = None
    content: str | None = None
    version: int = 0
    updated_at: datetime | None = None


class SyncRequest(BaseModel):
    changes: list[SyncChange]
    strategy: Literal["last_write_wins", "server_wins", "client_wins", "manual"] = "manual"


class ConflictResponse(BaseModel):
    id: int
    sync_id: str
    operation_id: str
    client_id: str
    status: str
    strategy: str
    server_version: int | None = None
    client_version: int | None = None
    server_payload: dict[str, Any] | None = None
    client_payload: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SyncHistoryResponse(BaseModel):
    id: int
    sync_id: str
    operation_id: str
    client_id: str
    operation_type: str
    sync_status: str
    error_details: str | None = None
    conflict_status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SyncResultItem(BaseModel):
    operation_id: str
    client_id: str
    status: Literal["synced", "failed", "conflict", "duplicate"]
    record: RecordResponse | None = None
    conflict: ConflictResponse | None = None
    error: str | None = None


class SyncResponse(BaseModel):
    sync_id: str
    message: str
    synced: int
    conflicts: int
    failed: int
    duplicates: int
    results: list[SyncResultItem]


class DashboardStats(BaseModel):
    pending_changes: int
    synchronized_records: int
    failed_synchronizations: int
    conflicts: int
    last_sync_time: datetime | None = None
    total_records: int
    deleted_records: int


class AuditLogResponse(BaseModel):
    id: int
    user_id: int | None = None
    action: str
    entity_type: str
    entity_id: str | None = None
    details: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
