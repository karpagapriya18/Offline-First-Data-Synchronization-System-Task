from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models, schemas
from app.sync_service import process_sync


def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def create_user(db):
    user = models.User(name="Test User", email="test@example.com", hashed_password="hashed", role="user")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_sync_create_is_idempotent():
    db = session()
    user = create_user(db)
    request = schemas.SyncRequest(
        changes=[
            schemas.SyncChange(
                operation_id="op-1",
                client_id="record-1",
                operation="create",
                title="First",
                content="Offline draft",
                version=0,
            )
        ]
    )

    _, first_counts, _ = process_sync(db, request=request, current_user=user)
    db.commit()
    _, second_counts, second_results = process_sync(db, request=request, current_user=user)

    assert first_counts["synced"] == 1
    assert second_counts["duplicates"] == 1
    assert second_results[0]["status"] == "duplicate"
    assert db.query(models.Record).count() == 1


def test_sync_update_version_mismatch_creates_conflict():
    db = session()
    user = create_user(db)
    record = models.Record(client_id="record-1", title="Server", content="Server text", user_id=user.id, version=2)
    db.add(record)
    db.commit()

    request = schemas.SyncRequest(
        strategy="manual",
        changes=[
            schemas.SyncChange(
                operation_id="op-2",
                client_id="record-1",
                operation="update",
                title="Client",
                content="Client text",
                version=1,
            )
        ],
    )

    _, counts, results = process_sync(db, request=request, current_user=user)

    assert counts["conflicts"] == 1
    assert results[0]["status"] == "conflict"
    assert db.query(models.Conflict).count() == 1
    assert db.query(models.Record).first().title == "Server"
