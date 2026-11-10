from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import auth_headers, login


def test_local_fallback_answer_stays_readable():
    """AI 服务不可用时的兜底回答也要像人话：不加编号、不出现原始参数和 Markdown 标题。"""
    from app.routers.chat import local_answer
    text = local_answer("校园卡丢了怎么办", [
        {"title": "补办说明", "snippet": "# 补办说明\n\n携带证件到卡务中心办理"},
        {"title": "补办说明", "snippet": "重复切片应被合并"},
    ])
    assert "补办说明：携带证件到卡务中心办理" in text
    assert "#" not in text and "重复切片" not in text
    assert "根据已入库资料" not in text and "{" not in text
    empty = local_answer("校园卡丢了怎么办", [])
    assert "暂未在知识库中找到足够依据" in empty


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "backend-api"
    docs = client.get("/docs")
    assert docs.status_code == 200
    assert "swagger-assets/swagger-ui-bundle.js" in docs.text
    assert "cdn.jsdelivr.net" not in docs.text
    assert client.get("/swagger-assets/swagger-ui-bundle.js").status_code == 200


def test_guest_cannot_access_documents(client: TestClient):
    home = client.get("/api/v1/home/categories")
    assert home.status_code == 401
    search = client.get("/api/v1/documents")
    assert search.status_code == 401
    detail = client.get("/api/v1/documents/1")
    assert detail.status_code == 401
    assert detail.json()["code"] == 100106


def test_registration_is_disabled(client: TestClient):
    response = client.post("/api/v1/auth/register", json={
        "username": "new_user", "password": "Password123", "nickname": "新用户", "privacy_agreed": True})
    assert response.status_code in {404, 405}


def test_login_validation_message_is_chinese(client: TestClient):
    response = client.post("/api/v1/auth/login", json={"account": "", "password": ""})
    assert response.status_code == 400
    message = response.json()["message"]
    assert "参数校验失败" in message
    assert "String should" not in message
    assert "账号" in message


def test_login_document_chat_and_feedback(client: TestClient):
    headers = auth_headers(login(client, "student", "Student123", "MOBILE"))
    assert client.post("/api/v1/auth/login", json={
        "account": "13800000000", "password": "Student123", "login_type": "PHONE",
        "client_type": "MOBILE"}).status_code == 200
    assert client.post("/api/v1/auth/login", json={
        "account": "20230001", "password": "Student123", "login_type": "STUDENT_NO",
        "client_type": "MOBILE"}).status_code == 200
    home = client.get("/api/v1/home/categories", headers=headers).json()
    document_id = home["data"]["categories"][0]["documents"][0]["document_id"]
    detail = client.get(f"/api/v1/documents/{document_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["document"]["content"]
    chat = client.post("/api/v1/chat/messages", headers=headers, json={
        "question": "校园卡丢失后如何处理？", "stream": False, "enable_db_tool": False})
    assert chat.status_code == 200, chat.text
    payload = chat.json()["data"]
    assert payload["message_id"] and payload["session_id"]
    assert "校园卡" in payload["content"]
    feedback = client.post("/api/v1/chat/messages/{}/feedback".format(payload["message_id"]),
                           headers=headers, json={"rating": "LIKE", "reason": "回答清晰"})
    assert feedback.status_code == 201
    duplicate = client.post("/api/v1/chat/messages/{}/feedback".format(payload["message_id"]),
                            headers=headers, json={"rating": "DISLIKE"})
    assert duplicate.status_code == 409
    admin_token = login(client, "admin", "Admin12345")
    admin_headers = auth_headers(admin_token)
    feedback_list = client.get("/api/v1/admin/feedbacks", headers=admin_headers,
                               params={"status": "PENDING", "page": 1, "page_size": 100}).json()
    target = next(item for item in feedback_list["data"]["list"] if item["message_id"] == payload["message_id"])
    handled = client.patch("/api/v1/admin/feedbacks/{}".format(target["feedback_id"]),
                           headers=admin_headers, json={"status": "PROCESSED"})
    assert handled.status_code == 200
    refreshed = client.get("/api/v1/admin/feedbacks", headers=admin_headers,
                           params={"status": "PROCESSED", "page": 1, "page_size": 100}).json()
    assert any(item["feedback_id"] == target["feedback_id"] for item in refreshed["data"]["list"])
    sessions = client.get("/api/v1/chat/sessions", headers=headers)
    assert sessions.status_code == 200
    assert sessions.json()["data"]["list"]


def test_admin_category_and_config_management(client: TestClient):
    token = login(client, "admin", "Admin12345")
    headers = auth_headers(token)
    name = f"测试分类_{uuid.uuid4().hex[:6]}"
    created = client.post("/api/v1/admin/categories", headers=headers,
                          json={"name": name, "sort_order": 99, "status": "ENABLED"})
    assert created.status_code == 201, created.text
    category_id = created.json()["data"]["category"]["category_id"]
    updated = client.put(f"/api/v1/admin/categories/{category_id}", headers=headers,
                         json={"name": name + "_更新", "sort_order": 98, "status": "DISABLED"})
    assert updated.status_code == 200
    configs = client.get("/api/v1/admin/configs", headers=headers)
    assert configs.status_code == 200
    response = client.put("/api/v1/admin/configs/rag.top_k", headers=headers, json={"config_value": "6"})
    assert response.status_code == 200
    assert response.json()["data"]["config"]["config_value"] == "6"
    deleted = client.delete(f"/api/v1/admin/categories/{category_id}", headers=headers)
    assert deleted.status_code == 200
    stats = client.get("/api/v1/admin/statistics/overview", headers=headers)
    assert stats.status_code == 200
    assert "trend" in stats.json()["data"]
    export = client.post("/api/v1/admin/statistics/export", headers=headers,
                         json={"type": "qa", "start_date": "2026-01-01", "end_date": "2026-12-31", "format": "CSV"})
    assert export.status_code == 200
    assert export.json()["data"]["file_url"].startswith("http")
    admin_me = client.get("/api/v1/auth/me", headers=headers).json()["data"]["user"]
    protected = client.patch(f"/api/v1/admin/users/{admin_me['user_id']}/status", headers=headers,
                             json={"status": "DISABLED"})
    assert protected.status_code == 400
    assert "管理员账号不能被禁用" in protected.json()["message"]


def test_internal_card_balance_tool_and_privacy(client: TestClient):
    token = login(client, "student", "Student123")
    user = client.get("/api/v1/auth/me", headers=auth_headers(token)).json()["data"]["user"]
    own = client.post("/internal/v1/tools/query",
                      headers={"X-Internal-Token": "test-internal"},
                      json={"tool_name": "get_card_balance", "params": {"student_no": "20230001"},
                            "user_context": {"user_id": user["user_id"], "role": "USER",
                                             "student_no": user["student_no"]}})
    assert own.status_code == 200
    assert own.json()["result"]["balance"] == "128.50"
    denied = client.post("/internal/v1/tools/query",
                         headers={"X-Internal-Token": "test-internal"},
                         json={"tool_name": "get_card_balance", "params": {"student_no": "01"},
                               "user_context": {"user_id": user["user_id"], "role": "USER",
                                                "student_no": user["student_no"]}})
    assert denied.status_code == 403
    assert "只能查询本人" in denied.json()["message"]
    admin_token = login(client, "admin", "Admin12345")
    admin = client.get("/api/v1/auth/me", headers=auth_headers(admin_token)).json()["data"]["user"]
    admin_query = client.post("/internal/v1/tools/query",
                              headers={"X-Internal-Token": "test-internal"},
                              json={"tool_name": "get_card_balance", "params": {"student_no": "01"},
                                    "user_context": {"user_id": admin["user_id"], "role": "ADMIN",
                                                     "student_no": ""}})
    assert admin_query.status_code == 403


def test_admin_cannot_use_mobile_login_or_chat(client: TestClient):
    mobile_admin = client.post("/api/v1/auth/login", json={
        "account": "admin", "password": "Admin12345", "client_type": "MOBILE"})
    assert mobile_admin.status_code == 403
    student_admin = client.post("/api/v1/auth/login", json={
        "account": "student01", "password": "Student123", "client_type": "ADMIN"})
    assert student_admin.status_code == 403
    admin_token = login(client, "admin", "Admin12345", "ADMIN")
    chat = client.get("/api/v1/chat/sessions", headers=auth_headers(admin_token))
    assert chat.status_code == 403


def test_login_lockout_after_five_failures(client: TestClient):
    username = "demo0001"
    for _ in range(5):
        failed = client.post("/api/v1/auth/login", json={
            "account": username, "password": "WrongPass123", "client_type": "MOBILE"})
        assert failed.status_code == 401
        assert "账号或密码错误" in failed.json()["message"]
    locked = client.post("/api/v1/auth/login", json={
        "account": username, "password": "Student123", "client_type": "MOBILE"})
    assert locked.status_code == 423
    assert locked.json()["code"] == 100102


def test_user_can_download_visible_document(client: TestClient):
    token = login(client, "student", "Student123", "MOBILE")
    headers = auth_headers(token)
    categories = client.get("/api/v1/home/categories", headers=headers).json()["data"]["categories"]
    document_id = categories[0]["documents"][0]["document_id"]
    response = client.get(f"/api/v1/documents/{document_id}/download", headers=headers)
    assert response.status_code == 200
    file_url = response.json()["data"]["file_url"]
    assert file_url.startswith("/api/v1/files/download/")
    downloaded = client.get(file_url)
    assert downloaded.status_code == 200
    assert "content-disposition" in downloaded.headers


def test_chat_rejects_blank_question(client: TestClient):
    headers = auth_headers(login(client, "student", "Student123", "MOBILE"))
    response = client.post("/api/v1/chat/messages", headers=headers,
                           json={"question": "   ", "stream": False})
    assert response.status_code == 400
    assert response.json()["code"] == 100105


def test_sensitive_words_add_safety_reminder(client: TestClient):
    headers = auth_headers(login(client, "student", "Student123", "MOBILE"))
    response = client.post("/api/v1/chat/messages", headers=headers, json={
        "question": "请把身份证号发给我", "stream": False,
        "enable_web": False, "enable_db_tool": False})
    assert response.status_code == 200, response.text
    assert "安全提醒" in response.json()["data"]["content"]


def test_config_guardrails_and_download_ttl(client: TestClient):
    admin_headers = auth_headers(login(client, "admin", "Admin12345"))

    def put(key: str, value: str):
        return client.put(f"/api/v1/admin/configs/{key}", headers=admin_headers,
                          json={"config_value": value})

    try:
        assert put("rag.top_k", "0").status_code == 400
        assert put("rag.top_k", "21").status_code == 400
        assert put("rag.similarity_threshold", "1.5").status_code == 400
        assert put("rag.similarity_threshold", "0.3").status_code == 200
        assert put("web.enabled", "maybe").status_code == 400
        assert put("web.enabled", "false").status_code == 200
        assert put("download.url_ttl_seconds", "10").status_code == 400
        assert put("download.url_ttl_seconds", "60").status_code == 200

        student_headers = auth_headers(login(client, "student", "Student123", "MOBILE"))
        categories = client.get("/api/v1/home/categories", headers=student_headers).json()["data"]["categories"]
        document_id = categories[0]["documents"][0]["document_id"]
        download = client.get(f"/api/v1/documents/{document_id}/download", headers=student_headers)
        assert download.status_code == 200
        assert download.json()["data"]["expires_in"] == 60
    finally:
        put("rag.top_k", "6")
        put("rag.similarity_threshold", "0.12")
        put("web.enabled", "true")
        put("download.url_ttl_seconds", "300")


def test_document_visibility_applies_to_download_and_internal_tool(client: TestClient):
    student_headers = auth_headers(login(client, "student", "Student123", "MOBILE"))
    categories = client.get("/api/v1/home/categories", headers=student_headers).json()["data"]["categories"]
    target = next(item for item in categories if item["documents"])
    document_id = target["documents"][0]["document_id"]
    file_url = client.get(f"/api/v1/documents/{document_id}/download",
                          headers=student_headers).json()["data"]["file_url"]

    admin_headers = auth_headers(login(client, "admin", "Admin12345"))
    detail = client.get(f"/api/v1/admin/documents/{document_id}",
                        headers=admin_headers).json()["data"]["document"]
    admin_categories = client.get("/api/v1/admin/categories", headers=admin_headers).json()["data"]["list"]
    category = next(item for item in admin_categories if item["category_id"] == detail["category_id"])
    payload = {"name": category["name"], "icon": category["icon"], "sort_order": category["sort_order"]}
    try:
        disabled = client.put(f"/api/v1/admin/categories/{category['category_id']}", headers=admin_headers,
                              json={**payload, "status": "DISABLED"})
        assert disabled.status_code == 200
        # 已签发的下载令牌在分类停用后也必须失效。
        assert client.get(file_url).status_code == 404
        # 内部工具与公开查询共用同一套可见性规则。
        tool = client.post("/internal/v1/tools/query", headers={"X-Internal-Token": "test-internal"},
                           json={"tool_name": "find_documents", "params": {"keyword": detail["title"]}})
        assert tool.status_code == 200
        assert document_id not in [item["document_id"] for item in tool.json()["result"]]
        search = client.get("/api/v1/documents", headers=student_headers,
                            params={"keyword": detail["title"]}).json()["data"]["list"]
        assert document_id not in [item["document_id"] for item in search]
    finally:
        restored = client.put(f"/api/v1/admin/categories/{category['category_id']}", headers=admin_headers,
                              json={**payload, "status": "ENABLED"})
        assert restored.status_code == 200


def test_document_date_rules_and_no_orphan_upload(client: TestClient):
    from datetime import timedelta

    from app.config import get_settings
    from app.models import now_local

    admin_headers = auth_headers(login(client, "admin", "Admin12345"))
    category_id = client.get("/api/v1/admin/categories", headers=admin_headers).json()["data"]["list"][0]["category_id"]
    settings = get_settings()
    before = len(list(settings.upload_dir.glob("*")))
    files = {"file": ("date-check.md", b"# date\n\ncontent", "text/markdown")}
    common = {"title": "日期规则校验文档", "category_id": str(category_id), "status": "DRAFT"}

    invalid = client.post("/api/v1/admin/documents", headers=admin_headers, files=files,
                          data={**common, "effective_date": "2026-12-31", "expire_date": "2026-01-01"})
    assert invalid.status_code == 400, invalid.text
    assert "生效日期" in invalid.json()["message"]
    # 日期校验发生在落盘前，失败请求不应留下孤儿上传文件。
    assert len(list(settings.upload_dir.glob("*"))) == before

    yesterday = (now_local().date() - timedelta(days=1)).isoformat()
    created = client.post("/api/v1/admin/documents", headers=admin_headers, files=files,
                          data={**common, "expire_date": yesterday})
    assert created.status_code == 201, created.text
    document_id = created.json()["data"]["document"]["document_id"]
    published = client.patch(f"/api/v1/admin/documents/{document_id}/status", headers=admin_headers,
                             json={"status": "PUBLISHED"})
    assert published.status_code == 400
    assert "失效日期" in published.json()["message"]
    assert client.delete(f"/api/v1/admin/documents/{document_id}", headers=admin_headers).status_code == 200


def test_deleted_sessions_are_purged_after_retention(client: TestClient):
    from datetime import timedelta

    from app.database import SessionLocal
    from app.models import ChatMessage, ChatSession, SysUser, now_local
    from app.services import purge_expired_sessions

    db = SessionLocal()
    try:
        user = db.query(SysUser).filter(SysUser.username == "student").first()
        old = ChatSession(user_id=user.id, title="过期会话", status="DELETED",
                          last_message_at=now_local() - timedelta(days=400),
                          deleted_at=now_local() - timedelta(days=400))
        recent = ChatSession(user_id=user.id, title="近期删除会话", status="DELETED",
                             last_message_at=now_local(), deleted_at=now_local())
        db.add_all([old, recent])
        db.flush()
        db.add_all([ChatMessage(session_id=old.id, role="USER", content="过期问题", status="SUCCESS"),
                    ChatMessage(session_id=recent.id, role="USER", content="近期问题", status="SUCCESS")])
        db.commit()
        old_id, recent_id = old.id, recent.id
        assert purge_expired_sessions(db, 180) == 1
        db.expire_all()
        assert db.get(ChatSession, old_id) is None
        assert db.query(ChatMessage).filter(ChatMessage.session_id == old_id).count() == 0
        assert db.get(ChatSession, recent_id) is not None
        db.query(ChatMessage).filter(ChatMessage.session_id == recent_id).delete(synchronize_session=False)
        db.query(ChatSession).filter(ChatSession.id == recent_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_local_retrieve_uses_threshold_and_best_snippet(client: TestClient):
    from app.database import SessionLocal
    from app.models import KnowledgeCategory, KnowledgeDocument, SysUser, now_local
    from app.services import local_retrieve

    db = SessionLocal()
    document_id = None
    category_id = None
    try:
        admin = db.query(SysUser).filter(SysUser.role == "ADMIN").first()
        category = KnowledgeCategory(name=f"检索测试_{uuid.uuid4().hex[:6]}", sort_order=999, status="ENABLED")
        db.add(category)
        db.flush()
        category_id = category.id
        filler = "前言内容。" * 200
        doc = KnowledgeDocument(
            category_id=category.id, title="校园卡挂失补办专项测试", summary="挂失补办",
            keywords="挂失,补办", file_name="local-test.md", storage_path="local-test.md",
            parsed_text=filler + "\n\n校园卡挂失后请携带身份证到卡务中心补办。\n\n" + "结尾内容。" * 100,
            file_type="MD", file_size=1, status="PUBLISHED", sync_status="NOT_INDEXED",
            active_index_version=0, allow_download=True, created_by=admin.id, updated_by=admin.id,
            published_at=now_local())
        db.add(doc)
        db.commit()
        document_id = doc.id
        hits = local_retrieve(db, "校园卡挂失后怎么补办", {document_id: 0}, 3,
                              document_id=document_id, threshold=0.12)
        assert hits and hits[0]["document_id"] == document_id
        assert "卡务中心" in hits[0]["snippet"]
        # 无关问题不应仅凭一两个汉字就产生“有依据”的引用。
        assert local_retrieve(db, "ZZZQQQ XKCD", {}, 3, threshold=0.12) == []
    finally:
        if document_id is not None:
            db.query(KnowledgeDocument).filter(KnowledgeDocument.id == document_id).delete(synchronize_session=False)
        if category_id is not None:
            db.query(KnowledgeCategory).filter(KnowledgeCategory.id == category_id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_card_balance_endpoint_only_returns_own_account(client: TestClient):
    headers = auth_headers(login(client, "student", "Student123", "MOBILE"))
    response = client.get("/api/v1/card/balance", headers=headers)
    assert response.status_code == 200, response.text
    account = response.json()["data"]["account"]
    assert account["balance"] == "128.50"
    assert account["card_no"] == "CARD****0001"
    admin_headers = auth_headers(login(client, "admin", "Admin12345"))
    assert client.get("/api/v1/card/balance", headers=admin_headers).status_code == 403


def test_profile_phone_change_requires_admin_approval(client: TestClient):
    user_headers = auth_headers(login(client, "student02", "Student123", "MOBILE"))
    new_phone = "13800000088"
    submitted = client.put("/api/v1/auth/profile", headers=user_headers, json={"phone": new_phone})
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()["data"]
    assert body["pending_changes"]["phone"] == new_phone
    assert body["user"]["phone"] == "13800000002"
    mine = client.get("/api/v1/auth/profile/change-requests", headers=user_headers).json()["data"]["list"]
    request = next(item for item in mine if item["field_name"] == "phone"
                   and item["status"] == "PENDING" and item["new_value"] == new_phone)
    admin_headers = auth_headers(login(client, "admin", "Admin12345"))
    pending = client.get("/api/v1/admin/profile-requests", headers=admin_headers,
                         params={"status": "PENDING", "page_size": 100}).json()["data"]["list"]
    row = next(item for item in pending if item["request_id"] == request["request_id"])
    assert row["old_value"] == "13800000002"
    approved = client.patch(f"/api/v1/admin/profile-requests/{row['request_id']}",
                            headers=admin_headers, json={"status": "APPROVED", "remark": "信息核对无误"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["request"]["status"] == "APPROVED"
    assert login(client, new_phone, "Student123", "MOBILE")
    old_login = client.post("/api/v1/auth/login", json={
        "account": "13800000002", "password": "Student123", "login_type": "PHONE",
        "client_type": "MOBILE"})
    assert old_login.status_code == 401


def test_profile_email_change_can_be_rejected(client: TestClient):
    user_headers = auth_headers(login(client, "student02", "Student123", "MOBILE"))
    new_email = "student02.tmp@demo.edu.cn"
    submitted = client.put("/api/v1/auth/profile", headers=user_headers, json={"email": new_email})
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["data"]["user"]["email"] == "student02@demo.edu.cn"
    mine = client.get("/api/v1/auth/profile/change-requests", headers=user_headers).json()["data"]["list"]
    request = next(item for item in mine if item["field_name"] == "email"
                   and item["status"] == "PENDING" and item["new_value"] == new_email)
    admin_headers = auth_headers(login(client, "admin", "Admin12345"))
    rejected = client.patch(f"/api/v1/admin/profile-requests/{request['request_id']}",
                            headers=admin_headers, json={"status": "REJECTED", "remark": "请到卡务中心变更"})
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["data"]["request"]["status"] == "REJECTED"
    me = client.get("/api/v1/auth/me", headers=user_headers).json()["data"]["user"]
    assert me["email"] == "student02@demo.edu.cn"


def test_sync_task_admin_api_is_removed(client: TestClient):
    admin_headers = auth_headers(login(client, "admin", "Admin12345"))
    assert client.get("/api/v1/admin/sync/tasks", headers=admin_headers).status_code == 404
    assert client.post("/api/v1/admin/sync/tasks/1/retry", headers=admin_headers).status_code == 404


def test_seed_fills_every_category_and_demo_workspace(client: TestClient):
    """每个板块都要有可用文档，并且后台演示数据（用户/审核/反馈）不能是空页面。"""
    admin_headers = auth_headers(login(client, "admin", "Admin12345"))
    categories = client.get("/api/v1/admin/categories", headers=admin_headers,
                            params={"page_size": 100}).json()["data"]["list"]
    assert len(categories) >= 5
    assert all(item["document_count"] >= 1 for item in categories)
    documents = client.get("/api/v1/admin/documents", headers=admin_headers,
                           params={"page_size": 100}).json()
    assert documents["pagination"]["total"] >= 25
    titles = {item["title"] for item in documents["data"]["list"]}
    assert {"校园卡办理与领取指引", "校园卡消费明细与对账指引", "校园卡常见报错与处理"} <= titles
    users = client.get("/api/v1/admin/users", headers=admin_headers,
                       params={"page_size": 1}).json()
    assert users["pagination"]["total"] >= 120
    pending = client.get("/api/v1/admin/profile-requests", headers=admin_headers,
                         params={"status": "PENDING"}).json()
    assert pending["pagination"]["total"] >= 2
    today = "2026-01-01"
    feedbacks = client.get("/api/v1/admin/feedbacks", headers=admin_headers,
                           params={"page": 1, "page_size": 100}).json()
    assert feedbacks["pagination"]["total"] >= 1
    stats = client.get("/api/v1/admin/statistics/overview", headers=admin_headers,
                       params={"start_date": today, "end_date": "2026-12-31"}).json()["data"]
    assert stats["qa"]["total"] >= 1
