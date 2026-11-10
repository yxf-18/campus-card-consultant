from __future__ import annotations

import json
import math
import threading
from pathlib import Path

from .config import get_settings

settings = get_settings()


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (
        math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right)) + 1e-12)


class LocalVectorStore:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self, rows: list[dict]) -> None:
        temp = self.path.with_name(self.path.name + ".tmp")
        temp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        temp.replace(self.path)

    def index(self, document_id: int, version_no: int, title: str, category: str,
              chunks: list[dict], vectors: list[list[float]], embedding_model: str) -> list[dict]:
        with self.lock:
            # 同一版本重试/重排时整版替换，避免文件变短后残留旧切片；更早版本保留。
            rows = [row for row in self._load()
                    if not (row["document_id"] == document_id and row["version_no"] == version_no)]
            for chunk, vector in zip(chunks, vectors):
                vector_id = f"{document_id}:{version_no}:{chunk['chunk_index']}"
                rows.append({"vector_id": vector_id, "document_id": document_id, "version_no": version_no,
                             "title": title, "category": category, "heading_path": chunk.get("heading_path") or "",
                             "page_no": chunk.get("page_no"), "snippet": chunk["content"], "vector": vector,
                             "embedding_model": embedding_model})
            self._save(rows)
            return [{"vector_id": item["vector_id"], "chunk_index": int(item["vector_id"].rsplit(":", 1)[1])}
                    for item in rows if item["document_id"] == document_id and item["version_no"] == version_no]

    def unindex(self, document_id: int) -> None:
        with self.lock:
            self._save([row for row in self._load() if row["document_id"] != document_id])

    def retrieve(self, vector: list[float], allowed_versions: dict[int, int], top_k: int,
                 threshold: float, document_id: int | None = None) -> list[dict]:
        results = []
        with self.lock:
            for row in self._load():
                doc_id = int(row["document_id"])
                if allowed_versions.get(doc_id) != int(row["version_no"]):
                    continue
                if document_id is not None and doc_id != document_id:
                    continue
                score = cosine(vector, row["vector"])
                if score < threshold:
                    continue
                results.append({"vector_id": row["vector_id"], "document_id": doc_id,
                                "title": row["title"], "snippet": row["snippet"],
                                "page_no": row.get("page_no"), "heading_path": row.get("heading_path") or "",
                                "score": round(score, 4)})
        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:top_k]


class ChromaVectorStore:
    def __init__(self) -> None:
        import chromadb
        self.client = chromadb.PersistentClient(path=str(settings.chroma_dir))

    def _collection(self, document_id: int):
        return self.client.get_or_create_collection(name=f"doc_{document_id}", metadata={"hnsw:space": "cosine"})

    def index(self, document_id: int, version_no: int, title: str, category: str,
              chunks: list[dict], vectors: list[list[float]], embedding_model: str) -> list[dict]:
        collection = self._collection(document_id)
        ids = [f"{document_id}:{version_no}:{chunk['chunk_index']}" for chunk in chunks]
        metadatas = [{"document_id": document_id, "version_no": version_no, "title": title,
                      "category": category, "heading_path": chunk.get("heading_path") or "",
                      "page_no": chunk.get("page_no") or 0, "embedding_model": embedding_model}
                     for chunk in chunks]
        collection.upsert(ids=ids, embeddings=vectors, documents=[chunk["content"] for chunk in chunks],
                          metadatas=metadatas)
        existing = collection.get(include=["metadatas"])
        new_ids = set(ids)
        # 只清理“同一版本”中不再存在的切片；旧版本保留，避免索引成功但业务库回滚时无法回退。
        stale = [item_id for item_id, metadata in zip(existing.get("ids", []), existing.get("metadatas", []))
                 if int(metadata.get("version_no", 0)) == version_no and item_id not in new_ids]
        if stale:
            collection.delete(ids=stale)
        return [{"vector_id": item_id, "chunk_index": int(item_id.rsplit(":", 1)[1])} for item_id in ids]

    def unindex(self, document_id: int) -> None:
        try:
            self.client.delete_collection(name=f"doc_{document_id}")
        except Exception:
            pass

    def retrieve(self, vector: list[float], allowed_versions: dict[int, int], top_k: int,
                 threshold: float, document_id: int | None = None) -> list[dict]:
        results = []
        for doc_id, version_no in allowed_versions.items():
            if document_id is not None and doc_id != document_id:
                continue
            try:
                response = self._collection(doc_id).query(query_embeddings=[vector],
                    n_results=max(1, top_k), where={"version_no": version_no},
                    include=["documents", "metadatas", "distances"])
            except Exception:
                continue
            for item_id, text, metadata, distance in zip(
                    response.get("ids", [[]])[0], response.get("documents", [[]])[0],
                    response.get("metadatas", [[]])[0], response.get("distances", [[]])[0]):
                score = 1.0 - float(distance)
                if score < threshold:
                    continue
                results.append({"vector_id": item_id, "document_id": doc_id,
                                "title": metadata.get("title", "知识库文档"), "snippet": text,
                                "page_no": metadata.get("page_no") or None,
                                "heading_path": metadata.get("heading_path", ""),
                                "score": round(score, 4)})
        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:top_k]


def build_vector_store():
    if settings.vector_backend == "chroma":
        try:
            return ChromaVectorStore()
        except Exception:
            pass
    return LocalVectorStore(settings.local_vector_file)


vector_store = build_vector_store()
