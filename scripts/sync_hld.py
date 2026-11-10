from __future__ import annotations

import copy
import re
import shutil
import zipfile
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

SOURCE = Path(r"D:\袁希锋\word\校园一卡通使用智能咨询工具 概要设计说明书.docx")
PROJECT = Path(r"D:\AIProject\campus-card-consultant")
OUTPUT = PROJECT / "docs" / "校园一卡通使用智能咨询工具 概要设计说明书_实现同步版.docx"
ER_IMAGE = Path(r"C:\Users\袁希锋\Desktop\图表_1.png")


def set_cell(cell, text: str) -> None:
    cell.text = text


def find_row(table, first: str, second: str | None = None):
    for row in table.rows:
        if row.cells[0].text.strip() == first and (second is None or row.cells[1].text.strip() == second):
            return row
    return None


def insert_row_after(table, after_index: int, values: list[str]):
    source_tr = table.rows[after_index]._tr
    new_tr = copy.deepcopy(source_tr)
    source_tr.addnext(new_tr)
    row = table.rows[after_index + 1]
    for cell, value in zip(row.cells, values):
        set_cell(cell, value)
    return row


def insert_row_after_match(table, first: str, values: list[str], second: str | None = None):
    for index, row in enumerate(table.rows):
        if row.cells[0].text.strip() == first and (second is None or row.cells[1].text.strip() == second):
            return insert_row_after(table, index, values)
    raise RuntimeError(f"row not found: {first}/{second}")


def add_row(table, values: list[str]):
    row = table.add_row()
    for cell, value in zip(row.cells, values):
        set_cell(cell, value)
    return row


def main() -> None:
    doc = Document(SOURCE)
    tables = doc.tables

    # 2.5.2 数据表清单
    table_list = tables[7]
    if not any(row.cells[1].text.strip() == "campus_card_account" for row in table_list.rows):
        add_row(table_list, ["11", "campus_card_account", "校园卡账户表",
                             "保存普通用户的校园卡号、余额、账户状态和最后交易时间，为本地数据库工具查询提供依据。"])

    # sys_config.config_group
    sys_config = tables[9]
    if not any(row.cells[0].text.strip() == "config_group" for row in sys_config.rows):
        insert_row_after_match(sys_config, "config_key",
                               ["config_group", "VARCHAR(50)", "否", "", "配置分组，用于后台分类展示和过滤"])

    # knowledge_document 实际新增字段
    document_fields = tables[11]
    if not any(row.cells[0].text.strip() == "active_index_version" for row in document_fields.rows):
        insert_row_after_match(document_fields, "sync_status",
                               ["active_index_version", "INT UNSIGNED", "否", "", "当前对问答生效的索引版本"])
        insert_row_after_match(document_fields, "active_index_version",
                               ["view_count", "BIGINT UNSIGNED", "否", "", "文档浏览次数"])

    # knowledge_chunk.version_no
    chunk_fields = tables[12]
    if not any(row.cells[0].text.strip() == "version_no" for row in chunk_fields.rows):
        insert_row_after_match(chunk_fields, "document_id",
                               ["version_no", "INT UNSIGNED", "否", "", "文档索引版本，与document_id和chunk_index组成唯一键"])

    # rag_sync_task.target_version
    sync_fields = tables[13]
    if not any(row.cells[0].text.strip() == "target_version" for row in sync_fields.rows):
        insert_row_after_match(sync_fields, "task_type",
                               ["target_version", "INT UNSIGNED", "否", "", "本次任务生成或切换的目标索引版本"])

    # chat_message 实际新增字段
    message_fields = tables[15]
    if not any(row.cells[0].text.strip() == "is_grounded" for row in message_fields.rows):
        insert_row_after_match(message_fields, "latency_ms",
                               ["is_grounded", "TINYINT(1)", "否", "", "回答是否具有本地知识库或数据库依据"])
        insert_row_after_match(message_fields, "is_grounded",
                               ["suggestions", "JSON", "是", "", "最多3条追问建议"])

    # 索引设计增加校园卡账户表
    index_table = tables[18]
    if not any(row.cells[0].text.strip() == "campus_card_account" for row in index_table.rows):
        add_row(index_table, ["campus_card_account",
                              "user_id唯一索引；card_no唯一索引；status",
                              "账户唯一性和状态筛选"])

    # 为后续新增表腾出表号：现有表17-22顺延为18-23
    for para in doc.paragraphs:
        match = re.match(r"^表\s+(\d+)\s", para.text.strip())
        if match and int(match.group(1)) >= 17:
            para.text = re.sub(r"^表\s+\d+", f"表 {int(match.group(1)) + 1}", para.text, count=1)

    # 新增 campus_card_account 字段章节和表格
    heading = next(p for p in doc.paragraphs if p.text.strip() == "2.5.4 索引设计")
    desc = heading.insert_paragraph_before(
        "用于保存普通用户与校园卡的对应关系、卡号、余额、账户状态和最后交易时间。余额属于本地业务数据，只通过受控数据库工具查询，不写入知识库或发送给外部搜索服务。")
    desc.style = "Normal"
    caption = heading.insert_paragraph_before("表 17 campus_card_account 字段说明")
    caption.style = "Normal"
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER

    card_table = doc.add_table(rows=1, cols=5)
    card_table.style = tables[17].style
    headers = ["字段", "类型", "允许空", "键", "说明"]
    for cell, value in zip(card_table.rows[0].cells, headers):
        set_cell(cell, value)
    card_rows = [
        ["id", "BIGINT UNSIGNED", "否", "PK", "校园卡账户ID"],
        ["user_id", "BIGINT UNSIGNED", "否", "FK/UK", "用户ID，与sys_user一对一"],
        ["card_no", "VARCHAR(64)", "否", "UK", "校园卡号"],
        ["balance", "DECIMAL(10,2)", "否", "", "当前余额"],
        ["status", "ENUM('ACTIVE','FROZEN','CLOSED')", "否", "", "账户状态"],
        ["last_transaction_at", "DATETIME", "是", "", "最后交易时间"],
        ["created_at", "DATETIME", "否", "", "创建时间"],
        ["updated_at", "DATETIME", "否", "", "更新时间"],
    ]
    for values in card_rows:
        add_row(card_table, values)
    heading._p.addprevious(card_table._tbl)
    spacer = heading.insert_paragraph_before("")
    spacer.style = "Normal"

    # 添加 2.5.3.11 标题
    subsection = heading.insert_paragraph_before("2.5.3.11 campus_card_account 校园卡账户表", style="Heading 4")
    # 标题需要在说明之前
    desc._p.addprevious(subsection._p)

    # 保存正文修改后的临时文件
    doc.save(OUTPUT)

    # 替换 ER 图 image3.png
    temp_zip = OUTPUT.with_suffix(".zip")
    with zipfile.ZipFile(OUTPUT, "r") as zin, zipfile.ZipFile(temp_zip, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/media/image3.png":
                data = ER_IMAGE.read_bytes()
            zout.writestr(item, data)
    temp_zip.replace(OUTPUT)

    print(OUTPUT)


if __name__ == "__main__":
    main()
