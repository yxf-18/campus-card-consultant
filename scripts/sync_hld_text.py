from __future__ import annotations

import copy
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

OUTPUT = Path(r"D:\AIProject\campus-card-consultant\docs\校园一卡通使用智能咨询工具 概要设计说明书_实现同步版.docx")


def replace_para(doc, old: str, new: str) -> bool:
    for para in doc.paragraphs:
        if para.text.strip() == old:
            para.text = new
            return True
    return False


def insert_after(para, text: str):
    new_p = copy.deepcopy(para._p)
    para._p.addnext(new_p)
    inserted = Paragraph(new_p, para._parent)
    inserted.text = text
    return inserted


def find_row(table, first: str, second: str | None = None):
    for row in table.rows:
        if row.cells[0].text.strip() == first and (second is None or row.cells[1].text.strip() == second):
            return row
    return None


def set_row_values(row, values: list[str]) -> None:
    for cell, value in zip(row.cells, values):
        cell.text = value


def insert_row_after(table, after_index: int, values: list[str]):
    source_tr = table.rows[after_index]._tr
    new_tr = copy.deepcopy(source_tr)
    source_tr.addnext(new_tr)
    row = table.rows[after_index + 1]
    set_row_values(row, values)
    return row


def table_by_header(doc, expected: list[str], marker: str):
    for table in doc.tables:
        if not table.rows:
            continue
        headers = [cell.text.strip() for cell in table.rows[0].cells]
        if headers[:len(expected)] == expected and any(marker in cell.text for row in table.rows for cell in row.cells):
            return table
    raise RuntimeError(f"table not found: {expected}, marker={marker}")


def main() -> None:
    doc = Document(OUTPUT)
    replacements = {
        "访问层：管理员通过 PC 浏览器使用管理后台，普通用户和游客通过移动浏览器使用 H5 页面。":
            "访问层：管理员通过 PC 浏览器使用管理后台；普通用户通过移动浏览器使用 H5 页面；游客只能进入静态预览页，首页和文档接口均要求登录。",
        "典型问答流程为：前端提交问题 → 后端保存会话和用户消息 → 检索Chroma并读取MySQL切片 → 必要时调用Web Search或本地数据库工具 → 调云端大模型生成回答 → 保存消息、检索记录和引用 → 返回前端。":
            "典型问答流程为：前端提交问题 → 后端保存会话和用户消息 → 判断需要知识库、数据库工具或两者 → 仅在本地无依据或明确要求最新信息时补充Web Search → 调云端大模型生成回答 → 保存消息、引用和来源类型 → 返回前端。",
        "本系统数据库采用MySQL 8.0，字符集utf8mb4，存储引擎InnoDB。全部表字段、说明和索引集中在本节描述，各功能章节只列出该功能实际使用的表和字段。":
            "系统生产环境采用MySQL 8.0，字符集utf8mb4，存储引擎InnoDB；开发演示可切换SQLite。全部表字段、说明和索引集中在本节描述，各功能章节只列出该功能实际使用的表和字段。",
        "【功能描述】接收游客提交的注册信息，创建普通用户账号，并保存隐私协议确认时间。":
            "【功能描述】接收游客提交的基础注册信息，创建普通用户账号并保存隐私协议确认时间；手机号和学号在首次登录后通过账号绑定操作完善。",
        "1. 校验用户名、手机号、邮箱和学号是否唯一。": "1. 校验用户名唯一性；手机号、邮箱和学号如已填写则校验唯一性。",
        "2. 校验密码长度和隐私协议确认状态。": "2. 校验密码复杂度、密码长度和隐私协议确认状态。",
        "3. 对密码生成摘要并写入sys_user。": "3. 对密码生成摘要并写入sys_user，默认role=USER、status=ACTIVE。",
        "4. 默认role=USER、status=ACTIVE。": "4. 首次登录后进入账号绑定步骤，要求补全手机号和学号。",
        "【输出】注册结果、用户ID和错误提示。":
            "【输出】注册结果、用户ID和错误提示。账号绑定接口为PUT /api/v1/auth/profile，手机号和学号为必填且保持唯一，绑定后可作为登录账号。",
        "【功能描述】校验用户账号和密码，处理登录失败锁定，并建立或结束登录状态。":
            "【功能描述】校验用户账号和密码，处理连续失败锁定，按客户端类型校验角色，并建立或结束登录状态。",
        "1. 按用户名、手机号或邮箱查询用户。": "1. 按用户名、手机号、邮箱或学号查询用户。",
        "2. 校验status和locked_until。": "2. 校验status、locked_until和client_type；移动端仅允许USER，管理端仅允许ADMIN。",
        "4. 成功后清零失败次数和锁定时间，生成登录令牌。": "4. 成功后清零失败次数和锁定时间，生成包含用户角色的访问令牌。",
        "【功能描述】限制未登录用户只能查看首页缩略信息，不能进入文档详情、AI问答和个人会话。":
            "【功能描述】未登录用户只能进入登录页、注册页和静态游客预览页，不能调用首页数据、文档检索、文档详情、下载、AI问答或会话接口。",
        "1. 请求上下文不存在有效用户时按游客处理。": "1. 请求上下文不存在有效用户时按游客处理，仅展示静态预览界面。",
        "2. 仅查询分类和文档缩略字段。": "2. 首页、检索、详情、下载和问答接口统一返回登录失效提示。",
        "3. 点击详情、下载或问答时返回未登录提示，并携带原访问地址。": "3. 登录成功后按redirect_url回到原业务页面；未绑定手机号和学号的用户先进入绑定页。",
        "【输出】首页缩略信息、登录引导和登录后回跳地址。": "【输出】静态界面预览、登录与注册入口、登录后回跳地址。",
        "【功能描述】按分类展示前N篇已发布文档的标题、封面和摘要，形成首页卡片信息流。":
            "【功能描述】登录后按分类展示前N篇已发布文档的标题、封面和摘要，形成首页卡片信息流。",
        "【操作者】游客、普通用户": "【操作者】普通用户",
        "【功能描述】根据关键词、分类和分页条件查询已发布文档，返回匹配列表。":
            "【功能描述】登录后根据关键词、分类和分页条件查询已发布文档，返回匹配列表。",
        "【功能描述】理解用户问题，检索本地知识库并生成带引用的回答，支持连续追问和追问建议。":
            "【功能描述】判断问题需要知识库、数据库工具或两者，按需调用本地来源生成带引用的回答，支持连续追问和追问建议。",
        "1. 校验登录状态并创建或继续会话。": "1. 校验移动端普通用户身份并创建或继续会话。",
        "2. 保存用户问题。": "2. 保存用户问题并识别知识库、数据库或混合查询意图。",
        "3. 检索ACTIVE切片并过滤无效来源。": "3. 文档类或混合类问题检索ACTIVE切片；数据库类问题调用白名单只读工具。",
        "4. 调用大模型生成回答。": "4. 本地来源不足或明确要求最新信息时，才补充Web Search。",
        "5. 保存AI回答、引用和追问建议，更新会话摘要。": "5. 调用云端模型生成回答，保存回答、引用、来源类型和追问建议，并更新会话摘要。",
        "【功能描述】本地知识不足时调用Web Search，补充公开实时信息并展示网页引用。":
            "【功能描述】Web Search仅作为补充来源；本地知识库和数据库均无有效依据，或用户明确要求最新、实时、官网等信息时调用。",
        "1. 判断本地知识是否不足或需要最新信息。": "1. 判断本地知识库和数据库是否均无有效依据，或问题是否要求最新信息。",
        "【功能描述】通过后端白名单工具查询文档元数据、分类和服务渠道等结构化数据。":
            "【功能描述】通过后端白名单工具查询文档元数据、分类、服务渠道和当前普通用户的校园卡余额等结构化数据。",
        "1. 校验工具白名单和参数。": "1. 校验工具白名单、当前用户身份和查询参数；管理员不得查询学生余额。",
        "2. 执行只读查询。": "2. 执行只读查询，普通用户只能查询与本人关联的校园卡账户。",
        "【功能描述】查询普通用户和管理员账号，查看状态并启用或禁用账号。":
            "【功能描述】查询普通用户和管理员账号，查看状态；仅允许封禁或解封普通用户，管理员账号不可禁用。",
        "3. 修改用户status并保存。": "3. 校验目标账号角色，仅修改普通用户的status并保存。",
        "移动端底部导航为“首页、问答、会话、我的”。首页使用双列文档卡片，问答页采用聊天消息和引用卡片，会话页展示本人历史会话。":
            "移动端打开网站先进入登录页，底部导航为“首页、问答、会话、我的”。首次登录后绑定手机号和学号；游客只能进入静态预览。首页使用双列文档卡片，问答页采用聊天消息、来源引用和追问卡片，会话页展示本人历史会话。",
        "PC后台左侧导航包括运营概览、分类管理、文档管理、用户管理、同步任务、反馈处理和系统配置。常见问题资料通过普通文档管理维护，不设置独立问答条目管理页面。":
            "PC后台打开网站先进入管理员登录页，左侧导航包括运营概览、分类管理、文档管理、用户管理、同步任务、反馈处理和系统配置。管理员仅使用PC管理端，不提供移动登录和AI问答入口；常见问题资料通过普通文档管理维护。",
    }
    for old, new in replacements.items():
        replace_para(doc, old, new)

    anchor = next((p for p in doc.paragraphs if p.text.strip() == "引用表保存标题、片段和页码快照。"), None)
    if anchor is not None and not any("校园卡账户与用户账户分离" in p.text for p in doc.paragraphs):
        insert_after(anchor, "校园卡账户与用户账户分离；余额只保存在本地campus_card_account表，通过受控工具按当前普通用户身份查询，不发送给外部模型或Web Search。")

    anchor = next((p for p in doc.paragraphs if p.text.strip() == "一个用户可以拥有多个会话和反馈。"), None)
    if anchor is not None and not any("一个普通用户对应一个校园卡账户" in p.text for p in doc.paragraphs):
        insert_after(anchor, "一个普通用户对应一个校园卡账户；管理员账号不绑定校园卡余额，也不能查询学生余额。")


    auth_register = table_by_header(doc, ["属性", "内容"], "INT-AUTH-01")
    for row in auth_register.rows:
        if row.cells[0].text.strip() == "接口说明":
            row.cells[1].text = "提交用户名、昵称、密码和隐私协议创建普通用户账号；手机号和学号在首次登录后绑定。"

    auth_inputs = table_by_header(doc, ["参数名", "类型", "必填", "说明与校验规则"], "privacy_agreed")
    for row in auth_inputs.rows:
        if row.cells[0].text.strip() == "phone":
            row.cells[3].text = "中国大陆手机号；注册时可为空，首次登录后绑定，全库唯一。"
        elif row.cells[0].text.strip() == "email":
            row.cells[3].text = "邮箱地址；可为空，填写时校验格式和唯一性。"
        elif row.cells[0].text.strip() == "student_no":
            row.cells[3].text = "学号；注册时可为空，首次登录后绑定，全库唯一。"

    login_inputs = table_by_header(doc, ["参数名", "类型", "必填", "说明与校验规则"], "login_type")
    for row in login_inputs.rows:
        if row.cells[0].text.strip() == "account":
            row.cells[3].text = "登录账号；支持用户名、手机号、邮箱或学号。"
        elif row.cells[0].text.strip() == "login_type":
            row.cells[3].text = "账号类型，枚举USERNAME、PHONE、EMAIL、STUDENT_NO；未传时自动识别。"
    if find_row(login_inputs, "client_type") is None:
        for index, row in enumerate(login_inputs.rows):
            if row.cells[0].text.strip() == "login_type":
                insert_row_after(login_inputs, index, ["client_type", "string", "否",
                                                        "MOBILE仅允许普通用户；ADMIN仅允许管理员。移动端强制传MOBILE。"])
                break

    for marker in ["INT-DOC-01", "INT-DOC-02"]:
        table = table_by_header(doc, ["属性", "内容"], marker)
        for row in table.rows:
            if row.cells[0].text.strip() == "权限要求":
                row.cells[1].text = "需登录；管理员只能通过PC管理端访问后台功能"

    interface_table = table_by_header(doc, ["接口编号", "接口名称", "调用者", "请求方式与路径", "主要输入", "主要输出", "约束"], "INT-AUTH-01")
    for row in interface_table.rows:
        key = row.cells[0].text.strip()
        if key == "INT-AUTH-01":
            set_row_values(row, ["INT-AUTH-01", "用户注册", "移动H5", "POST /api/v1/auth/register",
                                 "用户名、密码、昵称、隐私协议", "用户ID、账号状态", "用户名唯一；手机号和学号首次登录后绑定"])
        elif key == "INT-AUTH-02":
            set_row_values(row, ["INT-AUTH-02", "登录与退出", "移动H5、PC后台",
                                 "POST /api/v1/auth/login、POST /api/v1/auth/logout",
                                 "登录账号、密码、client_type", "访问令牌、用户信息",
                                 "移动端仅USER，管理端仅ADMIN；失败5次锁定10分钟"])
        elif key == "INT-DOC-01":
            row.cells[6].text = "需登录；只返回启用分类和已发布有效文档"
        elif key == "INT-DOC-02":
            row.cells[6].text = "需登录；支持标题、摘要、关键词检索"
        elif key == "INT-CHAT-02":
            row.cells[4].text = "问题、会话ID、当前文档ID、自动来源路由"
            row.cells[6].text = "仅普通用户；按意图调用知识库/数据库，Web仅补充"
        elif key == "INT-ADMIN-04":
            row.cells[6].text = "仅管理员；管理员账号不可禁用，只能封禁普通用户"
    if find_row(interface_table, "INT-AUTH-03") is None:
        for index, row in enumerate(interface_table.rows):
            if row.cells[0].text.strip() == "INT-AUTH-02":
                insert_row_after(interface_table, index, ["INT-AUTH-03", "账号绑定", "移动H5",
                                                          "PUT /api/v1/auth/profile", "手机号、学号、昵称、邮箱",
                                                          "更新后的用户信息", "登录后绑定；手机号和学号必填且唯一"])
                break

    mobile_pages = table_by_header(doc, ["页面", "主要区域与操作", "对应接口", "数据表"], "登录/注册")
    for row in mobile_pages.rows:
        if row.cells[0].text.strip() == "登录/注册":
            set_row_values(row, ["登录/注册", "用户名、密码、用户名/手机号/学号登录方式、隐私协议",
                                 "INT-AUTH-01、INT-AUTH-02、INT-AUTH-03", "sys_user"])
    if find_row(mobile_pages, "游客预览") is None:
        idx = next(i for i, row in enumerate(mobile_pages.rows) if row.cells[0].text.strip() == "登录/注册")
        insert_row_after(mobile_pages, idx, ["游客预览", "静态界面示意、登录和注册入口，不加载真实业务数据", "无", "无"])
    if find_row(mobile_pages, "账号绑定") is None:
        idx = next(i for i, row in enumerate(mobile_pages.rows) if row.cells[0].text.strip() == "游客预览")
        insert_row_after(mobile_pages, idx, ["账号绑定", "绑定手机号和学号，绑定后支持手机号或学号登录", "INT-AUTH-03", "sys_user"])

    admin_pages = table_by_header(doc, ["页面", "主要区域与操作", "对应接口", "数据表"], "管理员登录")
    for row in admin_pages.rows:
        if row.cells[0].text.strip() == "用户管理":
            set_row_values(row, ["用户管理", "账号筛选、状态查看、普通用户封禁和解封；管理员账号只读保护", "INT-ADMIN-04", "sys_user"])

    settings = doc.settings._element
    update_fields = settings.find(qn("w:updateFields"))
    if update_fields is None:
        update_fields = OxmlElement("w:updateFields")
        settings.append(update_fields)
    update_fields.set(qn("w:val"), "true")
    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
