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
SAFE_REFUSAL_PHRASES = ("帮我充值", "替我充值", "帮我挂失", "替我挂失", "冻结我的卡", "解冻我的卡",
                        "帮我退款", "替我退款")


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
        if response.status_code in {401, 403}:
            try:
                message = response.json().get("message") or "没有权限查询该校园卡账户"
            except Exception:
                message = "没有权限查询该校园卡账户"
            return {"tool_name": tool_name,
                    "result": {"found": False, "denied": True, "message": message}}
        response.raise_for_status()
        return {"tool_name": tool_name, "result": response.json().get("result")}
    except Exception:
        return None


def safe_refusal(question: str) -> str | None:
    if any(phrase in question for phrase in SAFE_REFUSAL_PHRASES):
        return ("本工具只提供校园一卡通使用咨询和办理指引，不能直接执行充值、挂失、解冻或退款等账户操作。"
                "请通过学校正式服务渠道办理；不要向任何非官方人员提供密码、验证码或完整身份信息。")
    return None


CARD_STATUS_TEXT = {"ACTIVE": "账户状态正常", "FROZEN": "账户已冻结", "LOST": "账户已挂失",
                    "DISABLED": "账户已停用", "INACTIVE": "账户尚未激活"}


def _clip(text: object, limit: int = 220) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip("，。；、,; ") + "……"


def _clean_snippet(value: object, limit: int = 220, title: str = "") -> str:
    """去掉切片自带的 Markdown 标题行，避免气泡里出现 “## 挂失” 或标题重复。"""
    lines = [line.strip() for line in str(value or "").splitlines() if line.strip()]
    if len(lines) > 1 and re.fullmatch(r"#{1,6}\s*.*", lines[0]):
        lines = lines[1:]
    text = " ".join(re.sub(r"^#{1,6}\s*", "", line) for line in lines)
    text = re.sub(r"\s+", " ", text).strip()
    if title and text.startswith(title):
        text = text[len(title):].lstrip(" ：:，,。.、")
    return _clip(text, limit)


def _amount(value: object) -> str:
    text = str(value if value is not None else "").strip()
    return f"{text} 元" if text else "金额暂未显示"


def _dict_to_text(data: dict) -> str:
    """把配置型返回值摊平成「标题：内容」的短句，避免把 JSON 直接显示给用户。"""
    chunks: list[str] = []
    for key, value in data.items():
        if isinstance(value, (list, tuple)):
            items = []
            for item in value:
                if isinstance(item, dict):
                    items.append(str(item.get("name") or item.get("title") or "").strip())
                else:
                    items.append(str(item).strip())
            items = [item for item in items if item]
            if items:
                chunks.append(f"{key}：" + "、".join(_clip(item, 40) for item in items[:6]))
        elif isinstance(value, dict):
            nested = "，".join(f"{sub_key} {_clip(sub_value, 40)}"
                               for sub_key, sub_value in value.items() if sub_value not in (None, ""))
            if nested:
                chunks.append(f"{key}：{nested}")
        elif value not in (None, ""):
            chunks.append(f"{key}：{_clip(value, 60)}")
    return "；".join(chunks) + "。" if chunks else ""


def describe_tool_result(tool_name: str, result: Any) -> str:
    """把内部数据库工具的结果翻译成一句人话，绝不把原始参数原样丢给用户。"""
    if isinstance(result, list):
        titles = [str(item.get("title") or item.get("name") or "").strip()
                  for item in result if isinstance(item, dict)]
        titles = [item for item in titles if item]
        if not titles:
            return "本地数据库暂时没有可展示的记录。"
        return "本地数据库里可以找到这些内容：" + "、".join(titles[:5]) + "。"
    if not isinstance(result, dict):
        return _clip(result)
    if result.get("found") is False:
        return str(result.get("message") or "本地数据库没有查询到对应记录，请核对信息或联系学校卡务中心。")
    if tool_name == "get_card_balance":
        parts = [f"你当前的校园卡余额为 {_amount(result.get('balance'))}"]
        if result.get("card_no"):
            parts.append(f"卡号 {result['card_no']}")
        status = str(result.get("status") or "").upper()
        if status:
            parts.append(CARD_STATUS_TEXT.get(status, "账户状态请以卡务中心登记为准"))
        return "，".join(parts) + "。该结果来自学校校园卡账户数据库，只支持查询本人账户。"
    return _dict_to_text(result)


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
        parts.append("根据学校公开的校园卡资料，可以这样处理：")
        seen_titles: set[str] = set()
        for item in contexts:
            title = _clip(item.get("title") or "相关资料", 40)
            if title in seen_titles:
                continue
            snippet = _clean_snippet(item.get("snippet") or "", 220, title)
            if not snippet:
                continue
            seen_titles.add(title)
            parts.append(f"- {title}：{snippet}")
            if len(seen_titles) >= 3:
                break
    if tool_result and tool_result.get("result") is not None:
        sentence = describe_tool_result(str(tool_result.get("tool_name") or ""), tool_result.get("result"))
        if sentence:
            parts.append(sentence)
    if web_results:
        parts.append("网上还有这些公开信息可以参考：")
        for item in web_results[:2]:
            snippet = _clip(item.get("snippet") or "", 160)
            parts.append(f"- {_clip(item.get('title') or '网页资料', 40)}：{snippet}")
    parts.append("以上内容仅供参考，具体办理要求请以学校最新正式通知为准。")
    return "\n\n".join(parts)


SUGGESTION_BANK = {
    "balance": ["如何给校园卡充值？", "校园卡消费流水怎么查询？", "校园卡余额不足时还能消费吗？"],
    "lost": ["补办校园卡需要准备什么材料？", "校园卡挂失后原卡还能用吗？", "校园卡补办期间怎么在校内消费？"],
    "consume": ["校园卡消费限额是多少？", "校园卡消费异常怎么核查？", "校园卡可以在哪里消费？"],
    "discount": ["学生优惠资格怎么认定？", "校园卡优惠活动在哪里查询？", "毕业离校后优惠还在吗？"],
    "activate": ["校园卡首次使用怎么激活？", "校园卡密码忘记怎么办？", "校园码在哪里出示？"],
}
DEFAULT_SUGGESTIONS = ["校园卡丢失后如何补办？", "校园卡有哪些充值方式？", "校园卡消费范围包括哪些？"]


def make_suggestions(question: str, contexts: list[dict]) -> list[str]:
    """按用户刚问的话题推荐下一轮可以继续问的问题，而不是永远给同一组固定问题。"""
    text = question or ""
    if any(word in text for word in ("余额", "充值", "到账", "扣款", "退费")):
        suggestions = SUGGESTION_BANK["balance"]
    elif any(word in text for word in ("丢", "挂失", "补办", "补卡", "解挂", "盗刷")):
        suggestions = SUGGESTION_BANK["lost"]
    elif any(word in text for word in ("消费", "流水", "限额", "商户", "终端", "对账")):
        suggestions = SUGGESTION_BANK["consume"]
    elif any(word in text for word in ("优惠", "活动", "减免", "资格")):
        suggestions = SUGGESTION_BANK["discount"]
    elif any(word in text for word in ("激活", "密码", "校园码", "门禁", "图书馆")):
        suggestions = SUGGESTION_BANK["activate"]
    else:
        suggestions = DEFAULT_SUGGESTIONS
    if any("优惠" in str(item.get("title", "")) for item in contexts):
        suggestions = ["校园卡优惠政策如何查询？"] + list(suggestions)
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
        "资料不足时必须明确说明，并建议联系学校正式渠道。回答简洁、使用中文。\n"
        "输出要求：用自然语言直接回答，不要输出[资料1]这类引用编号，不要列出参考来源，"
        "不要输出 JSON、字段名、参数名或接口路径；涉及金额时写成“128.50 元”。\n\n"
        "可用资料：\n" + "\n\n".join(sources)
    )
    # 会话摘要属于系统上下文，不能混入历史轮次，否则会被模型当成用户发言。
    summary_parts = [str(item.get("content", "")).strip() for item in history
                     if item.get("role") == "system" and str(item.get("content", "")).strip()]
    if summary_parts:
        system += "\n\n此前会话摘要：" + " ".join(summary_parts)[:1200]
    messages = [{"role": "system", "content": system}]
    turns = [item for item in history if item.get("role") in {"user", "assistant"}][-10:]
    for item in turns:
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
        emitted = False
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
                            break
                        try:
                            data = json.loads(raw)
                            content = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        except (json.JSONDecodeError, IndexError, AttributeError):
                            continue
                        if content:
                            emitted = True
                            yield content
        except Exception:
            # 已经流式输出过内容时，再追加整段抽取式兜底会得到“半截大模型 + 整段模板”的重复回答。
            if emitted:
                yield "\n\n（回答生成中断，请稍后重试。）"
                return
        # 模型正常返回但内容为空时也走抽取式兜底，避免用户收到空回答。
        if emitted:
            return
    answer = build_answer(question, contexts, web_results, tool_result)
    for index in range(0, len(answer), 20):
        yield answer[index:index + 20]
