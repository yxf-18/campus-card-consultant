from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import auth_headers, login


INTERNAL_HEADERS = {"X-Internal-Token": "test-internal"}


def _user_context(client: TestClient, username: str) -> dict:
    token = login(client, username, "Student123", "MOBILE")
    user = client.get("/api/v1/auth/me", headers=auth_headers(token)).json()["data"]["user"]
    return {"user_id": user["user_id"], "role": user["role"],
            "student_no": user["student_no"]}


def _query(client: TestClient, tool_name: str, context: dict, params: dict | None = None,
           question: str = ""):
    return client.post(
        "/internal/v1/tools/query",
        headers=INTERNAL_HEADERS,
        json={"tool_name": tool_name, "question": question,
              "params": params or {}, "user_context": context},
    )


def test_conversation_reads_are_private_and_numerically_backend_owned(client: TestClient):
    own = _user_context(client, "student")
    other = _user_context(client, "student01")
    balance = _query(client, "get_balance", own)
    assert balance.status_code == 200, balance.text
    assert balance.json()["result"]["ok"] is True
    assert balance.json()["result"]["data"]["card_no"].endswith("0001")

    denied = _query(client, "get_balance", own, {"student_no": other["student_no"]})
    assert denied.status_code == 200
    assert denied.json()["result"]["ok"] is False
    assert "他人" in denied.json()["result"]["message"]

    aggregate = _query(client, "aggregate_transactions", own, {
        "range": "this_month", "group_by": "category", "direction": "OUT",
    })
    assert aggregate.status_code == 200
    data = aggregate.json()["result"]["data"]
    assert abs(
        float(data["total_amount"])
        - sum(float(item["amount"]) for item in data["items"])
    ) < 0.011


def test_two_stage_write_is_idempotent_and_requires_a_token(client: TestClient):
    context = _user_context(client, "student02")
    no_token = _query(client, "commit_action", context)
    assert no_token.json()["result"]["error_code"] == "TOKEN_REQUIRED"

    prepared = _query(client, "prepare_action", context,
                      {"action_type": "recharge", "amount": "100"})
    payload = prepared.json()["result"]
    assert payload["ok"] is True, payload
    token = payload["data"]["confirm_token"]
    assert token

    committed = _query(client, "commit_action", context, {"confirm_token": token})
    assert committed.json()["result"]["ok"] is True
    order_no = committed.json()["result"]["data"]["order"]["order_no"]
    repeated = _query(client, "commit_action", context, {"confirm_token": token})
    assert repeated.json()["result"]["error_code"] == "TOKEN_USED"

    latest = _query(client, "query_order_status", context, {"order_no": order_no})
    order = latest.json()["result"]["data"]["order"]
    assert order["type"] == "recharge"
    assert order["status"] == "submitted"


def test_compound_conversation_commits_loss_then_reissue(client: TestClient):
    context = _user_context(client, "demo0119")
    response = _query(client, "conversation", context,
                      question="先挂失，然后再帮我预约后天的补办")
    result = response.json()["result"]
    assert result["ok"] is True, result
    operations = result["data"]["operations"]
    assert len(operations) == 2
    assert operations[0]["order"]["type"] == "loss"
    assert operations[1]["order"]["type"] == "reissue"
    assert operations[1]["order"]["payload"]["date"]
    assert operations[1]["order"]["payload"]["slot"]

    blocked = _query(client, "conversation", context, question="我要充值 100 元")
    blocked_result = blocked.json()["result"]
    assert blocked_result["ok"] is False
    assert blocked_result["error_code"] == "INVALID_CARD_STATE"


def test_conversation_refuses_other_users_balance(client: TestClient):
    context = _user_context(client, "student")
    response = _query(client, "conversation", context, question="查一下别人的余额")
    result = response.json()["result"]
    assert result["ok"] is False
    assert result["error_code"] == "PRIVACY"
    assert "本人" in result["message"]


def test_demo_mode_disables_mock_writes(client: TestClient, monkeypatch):
    context = _user_context(client, "demo0118")
    monkeypatch.setenv("DEMO_MODE", "false")
    response = _query(client, "prepare_action", context,
                      {"action_type": "recharge", "amount": "100"})
    result = response.json()["result"]
    assert result["ok"] is False
    assert result["error_code"] == "NOT_IMPLEMENTED"


def test_state_machine_rejects_skipping_completed_transition():
    import pytest
    from decimal import Decimal
    from uuid import uuid4

    from app.conversation_models import CardOrder
    from app.conversation_service import _event

    order = CardOrder(
        order_no=f"TEST-{uuid4().hex}", card_no="CARD-TEST", user_id=1,
        type="loss", status="created", amount=Decimal("0"),
        payload_json={}, idempotency_key=f"test-{uuid4().hex}",
    )
    with pytest.raises(ValueError):
        _event(None, order, "completed")
