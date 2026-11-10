from __future__ import annotations

import asyncio
import math

from fastapi.testclient import TestClient

from app.documents import chunk_document, parse_document
from app.embeddings import hash_embedding
from app.main import app, chat_events
from app.providers import (build_answer, classify_question, make_suggestions, parse_so_results,
                           safe_refusal, _chat_messages)
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
    doc_answer = build_answer("怎样补办", [{"title": "校园卡补办说明", "snippet": "携带证件办理"}], [], None)
    assert "校园卡补办说明" in doc_answer and "携带证件办理" in doc_answer
    assert "网页" not in doc_answer and "{" not in doc_answer
    db_answer = build_answer("余额多少", [], [], {"tool_name": "get_card_balance",
                                                  "result": {"balance": "66.80", "card_no": "CARD****0001",
                                                             "status": "ACTIVE"}})
    assert "校园卡账户数据库" in db_answer and "校园卡补办说明" not in db_answer


def test_balance_answer_is_plain_language_without_raw_payload():
    """手机号/余额这类结果必须变成一句人话，不能把工具返回的原始参数直接抛给用户。"""
    answer = build_answer("我的余额是多少", [], [], {
        "tool_name": "get_card_balance",
        "result": {"found": True, "student_no": "20230001", "student_name": "演示同学",
                   "card_no": "CARD****0001", "balance": "128.50", "status": "ACTIVE",
                   "source": "本地校园卡账户数据库"},
    })
    assert "128.50 元" in answer
    assert "账户状态正常" in answer
    for raw in ("{", "}", '"found"', "source", "student_no"):
        assert raw not in answer


def test_document_answer_strips_markdown_headings_and_duplicates():
    contexts = [
        {"title": "校园卡使用指南", "snippet": "# 校园卡使用指南\n\n校园卡用于身份识别与校内消费。"},
        {"title": "校园卡使用指南", "snippet": "重复标题的切片应该被合并掉。"},
        {"title": "挂失说明", "snippet": "## 挂失\n\n立即通过正式渠道挂失。"},
    ]
    answer = build_answer("校园卡丢了怎么挂失", contexts, [], None)
    assert "##" not in answer
    assert answer.count("校园卡使用指南：") == 1
    assert "重复标题的切片" not in answer
    assert "挂失说明：立即通过正式渠道挂失。" in answer


def test_suggestions_follow_the_current_topic():
    balance = make_suggestions("我的校园卡余额还有多少？", [])
    assert any("充值" in item for item in balance)
    lost = make_suggestions("校园卡丢了怎么补办？", [])
    assert any("材料" in item for item in lost)
    assert balance != lost
    assert len(make_suggestions("你好", [])) == 3


def test_local_vector_store_drops_stale_chunks_on_same_version():
    store = LocalVectorStore(Path(__file__).resolve().parents[1] / "data" / f"vectors-{uuid.uuid4().hex}.json")
    chunks = [
        {"chunk_index": 0, "heading_path": "指南", "page_no": 1, "content": "校园卡挂失后应尽快补办。"},
        {"chunk_index": 1, "heading_path": "指南", "page_no": 1, "content": "旧版本的第二段内容。"},
    ]
    vector = hash_embedding("校园卡挂失补办", 384)
    store.index(1, 1, "使用指南", "使用指南", chunks, [vector, vector], "hashing")
    # 同一版本重试时切片变少，旧的多余切片必须被清理。
    store.index(1, 1, "使用指南", "使用指南", chunks[:1], [vector], "hashing")
    rows = store.retrieve(vector, {1: 1}, 5, -1)
    assert len(rows) == 1
    assert rows[0]["vector_id"].endswith(":0")


def test_chat_messages_keeps_summary_as_system_context():
    history = [{"role": "system", "content": "此前会话摘要：用户问过补办流程。"}]
    history += [{"role": "user" if index % 2 == 0 else "assistant", "content": f"历史内容{index}"}
                for index in range(12)]
    messages = _chat_messages("新的问题", [], history, [], None)
    assert messages[0]["role"] == "system"
    assert "此前会话摘要" in messages[0]["content"]
    assert all(item["role"] != "user" or item["content"] != "此前会话摘要：用户问过补办流程。"
               for item in messages)
    assert messages[-1] == {"role": "user", "content": "新的问题"}


def test_answer_hides_raw_not_found_tool_payload():
    answer = build_answer("余额多少", [], [], {
        "tool_name": "get_card_balance",
        "result": {"found": False, "message": "未找到对应的校园卡账户"},
    })
    assert "未找到对应的校园卡账户" in answer
    assert "{" not in answer


def test_denied_balance_query_returns_privacy_message(monkeypatch):
    async def fake_core_tool(*_args, **_kwargs):
        return {"tool_name": "get_card_balance",
                "result": {"found": False, "denied": True,
                           "message": "普通用户只能查询本人校园卡余额"}}

    monkeypatch.setattr("app.main.core_tool", fake_core_tool)

    async def collect():
        events = []
        async for event, data in chat_events(ChatPayload(
                question="查询学号为01的学生的校园卡余额", enable_web=True, enable_db_tool=True)):
            events.append((event, data))
        return events

    events = asyncio.run(collect())
    text = "".join(data.get("content", "") for event, data in events if event == "delta")
    assert "只能查询本人" in text
    assert not any(event == "citation" for event, _ in events)
