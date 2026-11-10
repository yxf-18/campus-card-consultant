from __future__ import annotations

import os
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
os.environ.setdefault("VECTOR_BACKEND", "local")
os.environ.setdefault("LOCAL_VECTOR_FILE", str(BASE / "data" / "pytest_vectors.json"))
os.environ.setdefault("INTERNAL_TOKEN", "test-internal")
os.environ.setdefault("EMBEDDING_PROVIDER", "hashing")
(BASE / "data").mkdir(exist_ok=True)
(BASE / "data" / "pytest_vectors.json").unlink(missing_ok=True)
