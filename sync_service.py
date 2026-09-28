from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app import models, schemas


def record_payload(record: models.Record | None):
    if record is None:
        return None
    return {
        "client_id": record.client_id,
        "title": record.title,
        "content": record.content,
        "version": record.version,
        "is_deleted": record.is_deleted,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def change_payload(change: schemas.SyncChange):
    return {
        "client_id": change.client_id,
        "title": change.title,
        "content": change.content,
        "version": change.version,
        "updated_at": change.updated_at.isoformat() if change.updated_at else None,
    }


def add_history(db: Session, *, sync_id: str, change: schemas.SyncChange, user_id: int, status: str, record=None, error=None, conflict_status="none"):
    history = models.SyncHistory(
        sync_id=sync_id,
        operation_id=change.operation_id,
        user_id=user_id,
        record_id=record.id if record else None,
        client_id=change.client_id,
        operation_type=change.operation,
        sync_status=status,
        error_details=error,
        conflict_status=conflict_status,
    )
    db.add(history)
    return history


def create_conflict(db: Session, *, sync_id: str, change: schemas.SyncChange, user_id: int, record, strategy: str):
    conflict = models.Conflict(
        sync_id=sync_id,
        operation_id=change.operation_id,
        user_id=user_id,
        record_id=record.id if record else None,
        client_id=change.client_id,
        strategy=strategy,
        status="open",
        server_version=record.version if record else None,
        client_version=change.version,
        server_payload=record_payload(record),
        client_payload=change_payload(change),
    )
    db.add(conflict)
    db.flush()
    return conflict


def apply_change_to_record(record: models.Record, change: schemas.SyncChange):
    if change.operation == "delete":
        record.is_deleted = True
    else:
        if change.title is not None:
            record.title = change.title
        if change.content is not None:
            record.content = change.content
        record.is_deleted = False
    record.version += 1


def resolve_conflict_by_strategy(record: models.Record, change: schemas.SyncChange, strategy: str):
    if strategy == "server_wins":
        return "conflict"
    if strategy == "client_wins":
        apply_change_to_record(record, change)
        return "synced"
    if strategy == "last_write_wins":
        server_updated = record.updated_at or datetime.min.replace(tzinfo=timezone.utc)
        client_updated = change.updated_at or datetime.now(timezone.utc)
        if client_updated.replace(tzinfo=timezone.utc) >= server_updated.replace(tzinfo=timezone.utc):
            apply_change_to_record(record, change)
            return "synced"
        return "conflict"
    return "conflict"


def process_sync(db: Session, *, request: schemas.SyncRequest, current_user: models.User):
    sync_id = str(uuid4())
    results = []
    counters = {"synced": 0, "conflicts": 0, "failed": 0, "duplicates": 0}

    for change in request.changes:
        existing_operation = (
            db.query(models.LocalSyncOperation)
            .filter(
                models.LocalSyncOperation.user_id == current_user.id,
                models.LocalSyncOperation.operation_id == change.operation_id,
            )
            .first()
        )
        if existing_operation and existing_operation.status in {"synced", "duplicate"}:
            counters["duplicates"] += 1
            add_history(db, sync_id=sync_id, change=change, user_id=current_user.id, status="duplicate")
            results.append({
                "operation_id": change.operation_id,
                "client_id": change.client_id,
                "status": "duplicate",
                "record": None,
                "conflict": None,
                "error": "Operation was already processed.",
            })
            continue

        operation = existing_operation or models.LocalSyncOperation(
            operation_id=change.operation_id,
            user_id=current_user.id,
            client_id=change.client_id,
            operation_type=change.operation,
            payload=change_payload(change),
            base_version=change.version,
            status="pending",
        )
        db.add(operation)

        record = (
            db.query(models.Record)
            .filter(models.Record.user_id == current_user.id, models.Record.client_id == change.client_id)
            .with_for_update()
            .first()
        )

        try:
            if change.operation == "create":
                if record:
                    conflict = create_conflict(db, sync_id=sync_id, change=change, user_id=current_user.id, record=record, strategy=request.strategy)
                    operation.status = "conflict"
                    counters["conflicts"] += 1
                    add_history(db, sync_id=sync_id, change=change, user_id=current_user.id, status="conflict", record=record, conflict_status="open")
                    results.append({"operation_id": change.operation_id, "client_id": change.client_id, "status": "conflict", "record": record, "conflict": conflict, "error": "Record already exists on the server."})
                    continue
                if not change.title:
                    raise ValueError("Title is required for create operations.")
                record = models.Record(client_id=change.client_id, title=change.title, content=change.content, user_id=current_user.id)
                db.add(record)
                db.flush()
            else:
                if record is None:
                    raise ValueError("Record does not exist on the server.")
                if record.version != change.version:
                    resolved = resolve_conflict_by_strategy(record, change, request.strategy)
                    if resolved == "conflict":
                        conflict = create_conflict(db, sync_id=sync_id, change=change, user_id=current_user.id, record=record, strategy=request.strategy)
                        operation.status = "conflict"
                        counters["conflicts"] += 1
                        add_history(db, sync_id=sync_id, change=change, user_id=current_user.id, status="conflict", record=record, conflict_status="open")
                        results.append({"operation_id": change.operation_id, "client_id": change.client_id, "status": "conflict", "record": record, "conflict": conflict, "error": "Version mismatch detected."})
                        continue
                else:
                    apply_change_to_record(record, change)

            operation.status = "synced"
            counters["synced"] += 1
            add_history(db, sync_id=sync_id, change=change, user_id=current_user.id, status="synced", record=record)
            results.append({"operation_id": change.operation_id, "client_id": change.client_id, "status": "synced", "record": record, "conflict": None, "error": None})
        except Exception as exc:
            operation.status = "failed"
            operation.error_details = str(exc)
            counters["failed"] += 1
            add_history(db, sync_id=sync_id, change=change, user_id=current_user.id, status="failed", record=record, error=str(exc))
            results.append({"operation_id": change.operation_id, "client_id": change.client_id, "status": "failed", "record": record, "conflict": None, "error": str(exc)})

    return sync_id, counters, results
