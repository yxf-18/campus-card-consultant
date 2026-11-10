from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import auth_headers, login


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


def test_register_login_document_chat_and_feedback(client: TestClient):
    suffix = uuid.uuid4().hex[:8]
    username = f"user_{suffix}"
    register = client.post("/api/v1/auth/register", json={
        "username": username, "password": "Password123", "nickname": "测试用户", "privacy_agreed": True})
    assert register.status_code == 201, register.text
    token = login(client, username, "Password123")
    headers = auth_headers(token)
    student_no = f"T{uuid.uuid4().hex[:10]}"
    phone = f"139{uuid.uuid4().int % 100000000:08d}"
    bound = client.put("/api/v1/auth/profile", headers=headers,
                       json={"phone": phone, "student_no": student_no})
    assert bound.status_code == 200, bound.text
    assert client.post("/api/v1/auth/login", json={"account": phone, "password": "Password123", "login_type": "PHONE"}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"account": student_no, "password": "Password123", "login_type": "STUDENT_NO"}).status_code == 200
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
    feedback = client.post(f"/api/v1/chat/messages/{payload['message_id']}/feedback", headers=headers,
                           json={"rating": "LIKE", "reason": "回答清晰"})
    assert feedback.status_code == 201
    duplicate = client.post(f"/api/v1/chat/messages/{payload['message_id']}/feedback", headers=headers,
                            json={"rating": "DISLIKE"})
    assert duplicate.status_code == 409
    admin_token = login(client, "admin", "Admin12345")
    admin_headers = auth_headers(admin_token)
    feedback_list = client.get("/api/v1/admin/feedbacks", headers=admin_headers,
                               params={"status": "PENDING", "page": 1, "page_size": 100}).json()
    target = next(item for item in feedback_list["data"]["list"] if item["message_id"] == payload["message_id"])
    handled = client.patch(f"/api/v1/admin/feedbacks/{target['feedback_id']}", headers=admin_headers,
                           json={"status": "PROCESSED"})
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
    username = f"lock_{uuid.uuid4().hex[:8]}"
    created = client.post("/api/v1/auth/register", json={
        "username": username, "password": "Password123", "nickname": "锁定测试", "privacy_agreed": True})
    assert created.status_code == 201
    for _ in range(5):
        failed = client.post("/api/v1/auth/login", json={
            "account": username, "password": "WrongPass123", "client_type": "MOBILE"})
        assert failed.status_code == 401
    locked = client.post("/api/v1/auth/login", json={
        "account": username, "password": "Password123", "client_type": "MOBILE"})
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
