from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import Base, engine, get_db
from app.redis_client import get_redis_client
from app.security import create_access_token, decode_access_token, hash_password, verify_password
from app.sync_service import process_sync

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Offline-First Data Synchronization System",
    version="1.0.0",
    openapi_tags=[
        {"name": "Authorization Test"},
        {"name": "Authentication"},
        {"name": "Records"},
        {"name": "Synchronization"},
        {"name": "Conflict Resolution"},
        {"name": "Sync History"},
        {"name": "Dashboard"},
        {"name": "Audit Logs"},
        {"name": "default"},
    ],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
security = HTTPBearer()


def audit(db: Session, user_id: int | None, action: str, entity_type: str, entity_id: str | None = None, details=None):
    db.add(models.AuditLog(user_id=user_id, action=action, entity_type=entity_type, entity_id=entity_id, details=details))


@app.get("/", tags=["default"])
def root():
    return {"message": "Offline-First Sync API is running", "docs": "/docs"}


@app.get("/health", tags=["default"])
def health():
    redis_client = get_redis_client()
    return {"status": "healthy", "redis": "connected" if redis_client else "unavailable"}


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    payload = decode_access_token(credentials.credentials)
    if payload is None or payload.get("sub") is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = db.query(models.User).filter(models.User.id == int(payload["sub"])).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


@app.get("/auth/test-token", tags=["Authorization Test"])
def test_token(current_user: models.User = Depends(get_current_user)):
    return {
        "message": "JWT token is valid",
        "user_id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
    }


@app.post("/auth/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED, tags=["Authentication"])
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    new_user = models.User(name=user.name, email=user.email, hashed_password=hash_password(user.password), role="user")
    db.add(new_user)
    audit(db, None, "register", "user", user.email)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.post("/auth/login", response_model=schemas.TokenResponse, tags=["Authentication"])
def login(user: schemas.UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    token = create_access_token(data={"sub": str(db_user.id), "email": db_user.email, "role": db_user.role})
    return {"access_token": token, "token_type": "bearer"}


@app.get("/auth/me", response_model=schemas.UserResponse, tags=["Authentication"])
def me(current_user: models.User = Depends(get_current_user)):
    return current_user


@app.patch("/auth/me", response_model=schemas.UserResponse, tags=["Authentication"])
def update_profile(payload: schemas.UserUpdate, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.name is not None:
        current_user.name = payload.name
    if payload.password is not None:
        current_user.hashed_password = hash_password(payload.password)
    audit(db, current_user.id, "update_profile", "user", str(current_user.id))
    db.commit()
    db.refresh(current_user)
    return current_user


@app.get("/admin/users", response_model=list[schemas.UserResponse], tags=["Authentication"])
def get_all_users(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return db.query(models.User).all()


@app.get("/records", response_model=list[schemas.RecordResponse], tags=["Records"])
def list_records(
    search: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.Record).filter(models.Record.user_id == current_user.id)
    if search:
        query = query.filter(or_(models.Record.title.contains(search), models.Record.content.contains(search)))
    if status_filter == "active":
        query = query.filter(models.Record.is_deleted.is_(False))
    elif status_filter == "deleted":
        query = query.filter(models.Record.is_deleted.is_(True))
    if date_from:
        query = query.filter(models.Record.updated_at >= date_from)
    if date_to:
        query = query.filter(models.Record.updated_at <= date_to)
    sort_column = getattr(models.Record, sort_by, models.Record.updated_at)
    query = query.order_by(desc(sort_column) if sort_order == "desc" else asc(sort_column))
    return query.offset((page - 1) * page_size).limit(page_size).all()


@app.post("/records", response_model=schemas.RecordResponse, status_code=status.HTTP_201_CREATED, tags=["Records"])
def create_record(payload: schemas.RecordCreate, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.query(models.Record).filter(models.Record.user_id == current_user.id, models.Record.client_id == payload.client_id).first():
        raise HTTPException(status_code=409, detail="Record client_id already exists")
    record = models.Record(client_id=payload.client_id, title=payload.title, content=payload.content, user_id=current_user.id)
    db.add(record)
    audit(db, current_user.id, "create", "record", payload.client_id)
    db.commit()
    db.refresh(record)
    return record


def find_record(db: Session, current_user: models.User, record_id: str):
    query = db.query(models.Record).filter(models.Record.user_id == current_user.id)
    if record_id.isdigit():
        return query.filter(or_(models.Record.id == int(record_id), models.Record.client_id == record_id)).first()
    return query.filter(models.Record.client_id == record_id).first()


@app.put("/records/{record_id}", response_model=schemas.RecordResponse, tags=["Records"])
def update_record(record_id: str, payload: schemas.RecordUpdate, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    record = find_record(db, current_user, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.version != payload.version:
        raise HTTPException(status_code=409, detail="Version conflict")
    if payload.title is not None:
        record.title = payload.title
    if payload.content is not None:
        record.content = payload.content
    record.version += 1
    audit(db, current_user.id, "update", "record", record_id)
    db.commit()
    db.refresh(record)
    return record


@app.delete("/records/{record_id}", response_model=schemas.RecordResponse, tags=["Records"])
def delete_record(record_id: str, version: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    record = find_record(db, current_user, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.version != version:
        raise HTTPException(status_code=409, detail="Version conflict")
    record.is_deleted = True
    record.version += 1
    audit(db, current_user.id, "delete", "record", record_id)
    db.commit()
    db.refresh(record)
    return record


@app.post("/sync", response_model=schemas.SyncResponse, include_in_schema=False)
@app.post("/sync/synchronize", response_model=schemas.SyncResponse, tags=["Synchronization"])
def sync_data(request: schemas.SyncRequest, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    redis_client = get_redis_client()
    lock_key = f"sync:user:{current_user.id}"
    lock = redis_client.lock(lock_key, timeout=30, blocking_timeout=5) if redis_client else None
    if lock:
        lock.acquire()
    try:
        sync_id, counters, results = process_sync(db, request=request, current_user=current_user)
        audit(db, current_user.id, "sync", "sync_batch", sync_id, counters)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        if lock:
            lock.release()
    return {
        "sync_id": sync_id,
        "message": "Synchronization completed",
        "synced": counters["synced"],
        "conflicts": counters["conflicts"],
        "failed": counters["failed"],
        "duplicates": counters["duplicates"],
        "results": results,
    }


@app.get("/sync/history", response_model=list[schemas.SyncHistoryResponse], tags=["Sync History"])
def sync_history(
    status_filter: str | None = Query(default=None, alias="status"),
    conflict: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.SyncHistory).filter(models.SyncHistory.user_id == current_user.id)
    if status_filter:
        query = query.filter(models.SyncHistory.sync_status == status_filter)
    if conflict is not None:
        query = query.filter(models.SyncHistory.conflict_status != "none" if conflict else models.SyncHistory.conflict_status == "none")
    return query.order_by(models.SyncHistory.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()


@app.get("/conflicts", response_model=list[schemas.ConflictResponse], tags=["Conflict Resolution"])
def list_conflicts(open_only: bool = True, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(models.Conflict).filter(models.Conflict.user_id == current_user.id)
    if open_only:
        query = query.filter(models.Conflict.status == "open")
    return query.order_by(models.Conflict.created_at.desc()).all()


@app.post("/conflicts/{conflict_id}/resolve", response_model=schemas.ConflictResponse, tags=["Conflict Resolution"])
def resolve_conflict(conflict_id: int, resolution: dict, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    conflict = db.query(models.Conflict).filter(models.Conflict.id == conflict_id, models.Conflict.user_id == current_user.id).first()
    if not conflict:
        raise HTTPException(status_code=404, detail="Conflict not found")
    conflict.status = "resolved"
    conflict.resolution = resolution
    conflict.resolved_at = datetime.now(timezone.utc)
    audit(db, current_user.id, "resolve_conflict", "conflict", str(conflict_id), resolution)
    db.commit()
    db.refresh(conflict)
    return conflict


@app.get("/dashboard", response_model=schemas.DashboardStats, tags=["Dashboard"])
def dashboard(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    last_sync = (
        db.query(func.max(models.SyncHistory.created_at))
        .filter(models.SyncHistory.user_id == current_user.id)
        .scalar()
    )
    return {
        "pending_changes": db.query(models.LocalSyncOperation).filter(models.LocalSyncOperation.user_id == current_user.id, models.LocalSyncOperation.status == "pending").count(),
        "synchronized_records": db.query(models.SyncHistory).filter(models.SyncHistory.user_id == current_user.id, models.SyncHistory.sync_status == "synced").count(),
        "failed_synchronizations": db.query(models.SyncHistory).filter(models.SyncHistory.user_id == current_user.id, models.SyncHistory.sync_status == "failed").count(),
        "conflicts": db.query(models.Conflict).filter(models.Conflict.user_id == current_user.id, models.Conflict.status == "open").count(),
        "last_sync_time": last_sync,
        "total_records": db.query(models.Record).filter(models.Record.user_id == current_user.id).count(),
        "deleted_records": db.query(models.Record).filter(models.Record.user_id == current_user.id, models.Record.is_deleted.is_(True)).count(),
    }


@app.get("/audit-logs", response_model=list[schemas.AuditLogResponse], tags=["Audit Logs"])
def audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.AuditLog)
    if current_user.role != "admin":
        query = query.filter(models.AuditLog.user_id == current_user.id)
    return query.order_by(models.AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()


@app.get("/test-db", tags=["default"])
def test_db(db: Session = Depends(get_db)):
    db.execute(select(func.count(models.User.id)))
    return {"status": "ok", "message": "Database connection successful"}


@app.get("/test-redis", tags=["default"])
def test_redis():
    redis_client = get_redis_client()
    if not redis_client:
        return {"status": "unavailable", "message": "Redis is not configured or not running"}
    redis_client.set("offline_sync_test", "ok", ex=30)
    return {"status": redis_client.get("offline_sync_test")}


@app.get("/test-user-role", tags=["default"])
def test_user_role(current_user: models.User = Depends(get_current_user)):
    return {"user_id": current_user.id, "role": current_user.role, "is_admin": current_user.role == "admin"}


@app.get("/security-test", tags=["default"])
def security_test(current_user: models.User = Depends(get_current_user)):
    return {"message": "Protected endpoint reached", "email": current_user.email}
