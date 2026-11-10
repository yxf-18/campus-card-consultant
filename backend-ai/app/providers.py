from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .config import get_settings

settings = get_settings()
SAFE_REFUSAL_PHRASES = ("帮我充值", "替我充值", "帮我挂失", "替我挂失", "冻结我的卡", "解冻我的卡", "帮我退款")


def parse_so_results(page: str) -> list[dict[str, Any]]:
    results = []
    for block in re.findall(r'<li class="res-list".*?</li>', page, re.S)[:6]:
        title_match = re.search(r'<h3[^>]*>\s*<a[^>]*data-mdurl="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not title_match:
            continue
        title = html.unescape(re.sub(r"<[^>]+>", "", title_match.group(2))).strip()
        url = html.unescape(title_match.group(1)).strip()
        desc_match = re.search(r'<p class="res-desc"[^>]*>(.*?)</p>', block, re.S)
        snippet = html.unescape(re.sub(r"<[^>]+>", " ", desc_match.group(1) if desc_match else "")).strip()
        snippet = re.sub(r"\s+", " ", snippet)[:500]
        if title and url:
            results.append({"title": title, "url": url, "snippet": snippet})
    return results[:3]


async def so_search(question: str) -> list[dict[str, Any]]:
    """Chinese Web Search fallback without an API key."""
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            response = await client.get(
                "https://www.so.com/s", params={"q": question},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CampusCardConsultant/1.0"},
            )
        response.raise_for_status()
        return parse_so_results(response.text)
    except Exception:
        return []


async def bing_rss_search(question: str) -> list[dict[str, Any]]:
    """No-key Web Search fallback using Bing's public RSS result format."""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(
                "https://www.bing.com/search",
                params={"q": question, "format": "rss", "setlang": "zh-cn", "cc": "cn"},
                headers={"User-Agent": "Mozilla/5.0 CampusCardConsultant/1.0"},
            )
        response.raise_for_status()
        root = ET.fromstring(response.text)
        results = []
        for item in root.findall(".//item")[:4]:
            title = (item.findtext("title") or "网页资料").strip()
            link = (item.findtext("link") or "").strip()
            description = html.unescape(re.sub(r"<[^>]+>", " ", item.findtext("description") or ""))
            description = re.sub(r"\s+", " ", description).strip()
            if link and title:
                results.append({"title": title, "url": link, "snippet": description[:500]})
        return results[:3]
    except Exception:
        return []


async def tavily_search(question: str) -> list[dict[str, Any]]:
    if settings.search_provider == "tavily" and settings.tavily_api_key:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.post("https://api.tavily.com/search", json={
                    "api_key": settings.tavily_api_key, "query": question,
                    "max_results": 3, "search_depth": "basic", "include_answer": False})
            response.raise_for_status()
            results = [{"title": item.get("title", "网页资料"), "url": item.get("url", ""),
                        "snippet": item.get("content", "")} for item in response.json().get("results", [])[:3]]
            if results:
                return results
        except Exception:
            pass
    results = await so_search(question)
    if results:
        return results
    return await bing_rss_search(question)


DOCUMENT_HINTS = (
    "怎么", "如何", "怎样", "流程", "指南", "规定", "政策", "补办", "挂失",
    "充值方式", "充值", "消费", "优惠", "办理", "材料", "注意事项", "常见问题",
)
FRESHNESS_HINTS = ("最新", "实时", "今天", "今日", "今年", "新闻", "官网", "联网", "网上查询")


def db_tool_request(question: str) -> tuple[str | None, dict[str, Any], str | None]:
    params: dict[str, Any] = {}
    if any(word in question for word in ("余额", "卡内金额", "校园卡账户", "卡号")):
        student_match = re.search(r"(?:学号|学生学号)\s*(?:为|是|[:：])?\s*([A-Za-z0-9_-]{1,32})", question)
        card_match = re.search(r"(?:卡号)\s*(?:为|是|[:：])?\s*([A-Za-z0-9_-]{4,64})", question)
        if student_match:
            params["student_no"] = student_match.group(1)
        if card_match:
            params["card_no"] = card_match.group(1)
        return "get_card_balance", params, "card_balance"
    if any(word in question for word in ("服务中心", "服务渠道", "办理地点", "开放时间")):
        return "get_service_channels", params, "service"
    if any(word in question for word in ("有哪些文档", "资料目录", "文档目录")):
        return "find_documents", {"keyword": question[:20]}, "catalog"
    if any(word in question for word in ("有哪些分类", "分类目录")):
        return "list_categories", params, "categories"
    return None, params, None


def classify_question(question: str) -> dict[str, Any]:
    tool_name, params, db_domain = db_tool_request(question)
    document_hint = any(word in question for word in DOCUMENT_HINTS)
    explicit_web = any(word in question for word in FRESHNESS_HINTS)
    return {
        "use_knowledge": document_hint or tool_name is None,
        "use_database": tool_name is not None,
        "db_tool": tool_name,
        "params": params,
        "db_domain": db_domain,
        "explicit_web": explicit_web,
    }


def tool_has_evidence(tool_result: dict[str, Any] | None) -> bool:
    if not tool_result:
        return False
    result = tool_result.get("result")
    if isinstance(result, dict) and result.get("found") is False:
        return False
    return bool(result)


async def core_tool(question: str, user_context: dict[str, Any] | None = None,
                    tool_name: str | None = None,
                    params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if tool_name is None:
        tool_name, inferred_params, _ = db_tool_request(question)
        params = inferred_params
    if not tool_name:
        return None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(f"{settings.core_base_url}/internal/v1/tools/query",
                                         headers={"X-Internal-Token": settings.internal_token},
                                         json={"tool_name": tool_name, "params": params or {},
                                               "user_context": user_context or {}})
        response.raise_for_status()
        return {"tool_name": tool_name, "result": response.json().get("result")}
    except Exception:
        return None


def safe_refusal(question: str) -> str | None:
    if any(phrase in question for phrase in SAFE_REFUSAL_PHRASES):
        return ("本工具只提供校园一卡通使用咨询和办理指引，不能直接执行充值、挂失、解冻或退款等账户操作。"
                "请通过学校正式服务渠道办理；不要向任何非官方人员提供密码、验证码或完整身份信息。")
    return None


def build_answer(question: str, contexts: list[dict], web_results: list[dict],
                 tool_result: dict | None) -> str:
    refusal = safe_refusal(question)
    if refusal:
        return refusal
    if not contexts and not web_results and not tool_result:
        return ("暂未在本地知识库找到足够依据。请补充问题，或联系校园卡服务中心等学校正式渠道核实。"
                "本工具不会编造政策、金额或办理时限。")
    parts: list[str] = []
    if contexts:
        parts.append("根据知识库资料整理如下：")
        for index, item in enumerate(contexts[:3], start=1):
            parts.append(f"{index}. {item.get('title', '相关资料')}：{str(item.get('snippet', ''))[:260]}")
    if tool_result and tool_result.get("result"):
        result = tool_result["result"]
        result_text = json.dumps(result, ensure_ascii=False)[:500] if isinstance(result, (dict, list)) else str(result)[:500]
        parts.append("本地校园卡账户数据库查询结果：" if tool_result.get("tool_name") == "get_card_balance" else "本地数据库查询结果：")
        parts.append(result_text)
    if web_results:
        parts.append("联网补充信息：")
        parts.extend(f"- {item['title']}：{item['snippet'][:180]}" for item in web_results[:2])
    parts.append("以上仅作为咨询指引，具体办理要求请以学校最新正式通知为准。")
    return "\n\n".join(parts)


def make_suggestions(question: str, contexts: list[dict]) -> list[str]:
    suggestions = ["校园卡丢失后如何补办？", "校园卡有哪些充值方式？", "校园卡消费范围包括哪些？"]
    if any("优惠" in str(item.get("title", "")) for item in contexts):
        suggestions.insert(0, "校园卡优惠政策如何查询？")
    if "补办" in question:
        suggestions.insert(0, "补办校园卡需要准备什么材料？")
    return list(dict.fromkeys(suggestions))[:3]


def _chat_messages(question: str, contexts: list[dict], history: list[dict], web_results: list[dict],
                   tool_result: dict | None) -> list[dict[str, str]]:
    sources = []
    for index, item in enumerate(contexts[:5], start=1):
        sources.append(f"[资料{index}] {item.get('title', '')}\n{item.get('snippet', '')}")
    for index, item in enumerate(web_results, start=1):
        sources.append(f"[网页{index}] {item.get('title', '')}\n{item.get('snippet', '')}\n{item.get('url', '')}")
    if tool_result:
        sources.append("[系统工具] " + json.dumps(tool_result.get("result"), ensure_ascii=False))
    system = (
        "你是校园一卡通使用咨询助手。只能依据给定资料回答，不得编造金额、电话、时限或政策。"
        "涉及充值、挂失、退款等账户操作时只提供办理指引，不承诺代为执行。"
        "资料不足时必须明确说明，并建议联系学校正式渠道。回答简洁、使用中文。\n\n"
        "可用资料：\n" + "\n\n".join(sources)
    )
    messages = [{"role": "system", "content": system}]
    for item in history[-10:]:
        role = "assistant" if item.get("role") == "assistant" else "user"
        content = str(item.get("content", ""))[:2000]
        if content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})
    return messages


async def stream_llm(question: str, contexts: list[dict], history: list[dict], web_results: list[dict],
                     tool_result: dict | None) -> AsyncIterator[str]:
    if settings.llm_base_url and settings.llm_api_key and settings.llm_model:
        headers = {"Authorization": f"Bearer {settings.llm_api_key}", "Content-Type": "application/json"}
        payload = {"model": settings.llm_model, "messages": _chat_messages(question, contexts, history, web_results, tool_result),
                   "temperature": 0.2, "stream": True}
        try:
            async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
                async with client.stream("POST", f"{settings.llm_base_url}/chat/completions",
                                         headers=headers, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == "[DONE]":
                            return
                        try:
                            data = json.loads(raw)
                            content = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        except (json.JSONDecodeError, IndexError, AttributeError):
                            continue
                        if content:
                            yield content
            return
        except Exception:
            pass
    answer = build_answer(question, contexts, web_results, tool_result)
    for index in range(0, len(answer), 20):
        yield answer[index:index + 20]
