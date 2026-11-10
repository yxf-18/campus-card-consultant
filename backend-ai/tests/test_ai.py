from __future__ import annotations

import math

from fastapi.testclient import TestClient

from app.documents import chunk_document, parse_document
from app.embeddings import hash_embedding
from app.main import app
from app.providers import build_answer, classify_question, parse_so_results, safe_refusal
from app.schemas import ChatPayload
from app.vector_store import LocalVectorStore
from pathlib import Path
import uuid


def test_chunking_keeps_heading_and_page():
    chunks = chunk_document([(2, "# 充值说明\n\n校园卡充值应使用学校正式渠道。\n\n充值后请查询余额。")], max_chars=30)
    assert chunks
    assert chunks[0]["heading_path"] == "充值说明"
    assert all(item["page_no"] == 2 for item in chunks)


def test_hash_embedding_is_deterministic_and_normalized():
    first = hash_embedding("校园卡充值补办", 128)
    second = hash_embedding("校园卡充值补办", 128)
    assert first == second
    assert abs(math.sqrt(sum(item * item for item in first)) - 1.0) < 1e-6


def test_local_vector_store_version_filter():
    store = LocalVectorStore(Path(__file__).resolve().parents[1] / "data" / f"vectors-{uuid.uuid4().hex}.json")
    chunks = [{"chunk_index": 0, "heading_path": "指南", "page_no": 1, "content": "校园卡挂失后应尽快补办。"}]
    vector = hash_embedding("校园卡挂失补办", 384)
    store.index(1, 1, "使用指南", "使用指南", chunks, [vector], "hashing")
    assert store.retrieve(vector, {1: 1}, 5, -1)
    assert not store.retrieve(vector, {1: 2}, 5, -1)
    store.index(1, 2, "使用指南", "使用指南", chunks, [vector], "hashing")
    assert store.retrieve(vector, {1: 2}, 5, -1)


def test_safety_refusal_and_internal_auth():
    assert safe_refusal("帮我充值一百元")
    client = TestClient(app)
    docs = client.get("/docs")
    assert docs.status_code == 200
    assert "cdn.jsdelivr.net" not in docs.text
    assert client.get("/swagger-assets/swagger-ui.css").status_code == 200
    denied = client.post("/internal/v1/unindex", json={"document_id": 1})
    assert denied.status_code == 403
    allowed = client.post("/internal/v1/unindex", json={"document_id": 1},
                          headers={"X-Internal-Token": "test-internal"})
    assert allowed.status_code == 200


def test_parse_markdown_docx_and_pdf():
    data_dir = Path(__file__).resolve().parents[1] / "data"
    md = data_dir / f"parse-{uuid.uuid4().hex}.md"
    md.write_text("# 标题\n\n校园卡使用说明。", encoding="utf-8")
    assert "校园卡" in parse_document(md, "md").text

    from docx import Document
    docx_path = data_dir / f"parse-{uuid.uuid4().hex}.docx"
    doc = Document(); doc.add_paragraph("校园卡补办说明"); doc.save(docx_path)
    assert "补办" in parse_document(docx_path, "docx").text

    import fitz
    pdf_path = data_dir / f"parse-{uuid.uuid4().hex}.pdf"
    pdf = fitz.open(); page = pdf.new_page(); page.insert_text((72, 72), "Campus card guide"); pdf.save(pdf_path); pdf.close()
    parsed = parse_document(pdf_path, "pdf")
    assert parsed.pages and "Campus" in parsed.text


def test_web_search_parser_and_three_source_defaults():
    page = """<li class="res-list"><h3 class="res-title"><a data-mdurl="https://example.edu/card" target="_blank">校园卡补办</a></h3><p class="res-desc">携带证件前往卡务中心办理补办。</p></li>"""
    results = parse_so_results(page)
    assert results[0]["url"] == "https://example.edu/card"
    assert "卡务中心" in results[0]["snippet"]
    payload = ChatPayload(question="校园卡丢失怎么办")
    assert payload.enable_web is True
    assert payload.enable_db_tool is True


def test_question_source_routing():
    doc = classify_question("校园卡丢失后怎么补办？")
    assert doc["use_knowledge"] and not doc["use_database"]
    balance = classify_question("我的账号余额是多少？")
    assert balance["use_database"] and not balance["use_knowledge"]
    mixed = classify_question("我想要知道我账号的余额，并且告诉我怎样进行充值")
    assert mixed["use_database"] and mixed["use_knowledge"]
    latest = classify_question("今天学校官网有什么最新优惠")
    assert latest["explicit_web"]


def test_answer_uses_only_selected_sources():
    doc_answer = build_answer("怎样补办", [{"title": "指南", "snippet": "携带证件办理"}], [], None)
    assert "知识库资料" in doc_answer and "联网补充" not in doc_answer
    db_answer = build_answer("余额多少", [], [], {"tool_name": "get_card_balance", "result": {"balance": "66.80"}})
    assert "本地校园卡账户数据库" in db_answer and "知识库资料" not in db_answer
