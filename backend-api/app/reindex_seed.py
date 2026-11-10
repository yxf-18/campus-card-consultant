from __future__ import annotations

import asyncio
import time

from .database import SessionLocal
from .models import KnowledgeDocument, SysUser
from .services import run_sync_task, trigger_sync


def main() -> None:
    failures = 0
    for attempt in range(1, 4):
        db = SessionLocal()
        try:
            admin = db.query(SysUser).filter(SysUser.role == "ADMIN").order_by(SysUser.id).first()
            documents = (db.query(KnowledgeDocument)
                         .filter(KnowledgeDocument.status == "PUBLISHED",
                                 KnowledgeDocument.is_deleted.is_(False),
                                 KnowledgeDocument.active_index_version == 0).all())
            if not documents:
                print("All published seed documents already have active indexes.")
                return
            if admin is None:
                raise RuntimeError("No administrator account is available.")
            task_ids = []
            for document in documents:
                task = trigger_sync(db, document, "CREATE", admin.id)
                task_ids.append(task.id)
            for task_id in task_ids:
                asyncio.run(run_sync_task(task_id))
            db.expire_all()
            pending = (db.query(KnowledgeDocument)
                       .filter(KnowledgeDocument.status == "PUBLISHED",
                               KnowledgeDocument.is_deleted.is_(False),
                               KnowledgeDocument.active_index_version == 0).count())
            if pending == 0:
                print(f"Indexed {len(task_ids)} seed documents on attempt {attempt}.")
                return
            failures = pending
        finally:
            db.close()
        time.sleep(3)
    print(f"Seed indexing incomplete; {failures} published documents remain unindexed.")


if __name__ == "__main__":
    main()
