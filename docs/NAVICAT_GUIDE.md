# Navicat 连接说明

## 当前开发数据库（SQLite）

项目默认使用 SQLite，可直接在 Navicat 中新建 SQLite 连接：

- 连接名：`CampusCardConsultant-Local`
- 连接类型：`SQLite`
- 数据库文件：

```text
D:\AIProject\campus-card-consultant\backend-api\data\campus_card.db
```

连接后重点查看：

- `sys_user`：用户名、手机号、学号和角色
- `campus_card_account`：校园卡号、余额和状态
- `profile_change_request`：手机号/邮箱修改申请与审核结果
- `knowledge_document`：知识文档及索引状态
- `knowledge_chunk`：RAG 切片
- `chat_session` / `chat_message` / `chat_citation`：会话与引用

## 验证 SQL

```sql
SELECT u.student_no, u.nickname, c.card_no, c.balance, c.status
FROM campus_card_account c
JOIN sys_user u ON u.id = c.user_id
ORDER BY u.id;

SELECT id, title, status, sync_status, active_index_version
FROM knowledge_document
ORDER BY id;
```

## MySQL 8.0 部署数据库

先执行：

```text
database/database_schema_v1.3.sql
```

然后在 Navicat 中新建 MySQL 连接：

- 主机：`127.0.0.1`
- 端口：`3306`
- 数据库：`campus_card_consultant`
- 用户名/密码：使用本机 MySQL 实际配置

项目不会保存或暴露 MySQL 密码。
