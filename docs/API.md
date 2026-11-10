# API 摘要

业务接口基础路径：`/api/v1`。除登录外均需 `Authorization: Bearer <token>`。账号由学校统一开通并保存在数据库中，不提供自助注册；游客只能进入前端静态预览，不能调用首页、检索、文档和问答接口。

## 公共响应

```json
{"code":0,"message":"success","data":{},"pagination":{"page":1,"page_size":20,"total":0,"has_more":false},"timestamp":1730000000}
```

## 业务接口

- `POST /auth/login`、`POST /auth/logout`、`GET /auth/me`、`PUT /auth/profile`
- 登录支持 `USERNAME`、`PHONE`、`EMAIL`、`STUDENT_NO`；`client_type=MOBILE` 只允许普通用户，`client_type=ADMIN` 只允许管理员。
- `PUT /auth/profile`：学号、昵称直接更新；手机号、邮箱首次补录直接生效，已有值再修改会生成待审核申请。`GET /auth/profile/change-requests` 查看本人申请记录。
- `GET /home/categories`、`GET /documents`、`GET /documents/{id}`、`GET /documents/{id}/download`
- `GET /card/balance`：只按当前登录用户查询本人校园卡余额，不接受学号或卡号参数。
- `GET|POST /chat/sessions`、`PATCH|DELETE /chat/sessions/{id}`、`GET /chat/sessions/{id}/messages`
- `POST /chat/messages`，支持 SSE；`POST /chat/messages/{id}/feedback`
- `GET|POST /admin/categories`、`PUT|DELETE /admin/categories/{id}`
- `GET|POST /admin/documents`、`GET|PUT|PATCH|DELETE /admin/documents/{id}`
- `GET /admin/users`、`PATCH /admin/users/{id}/status`
- `GET /admin/profile-requests`、`PATCH /admin/profile-requests/{id}`：手机号/邮箱变更审核。
- `GET /admin/feedbacks`、`PATCH /admin/feedbacks/{id}`
- `GET /admin/statistics/overview`、`POST /admin/statistics/export`
- `GET /admin/configs`、`PUT /admin/configs/{config_key}`

原先的 `GET /admin/sync/tasks` 与 `POST /admin/sync/tasks/{id}/retry` 已删除；文档发布后的索引由后台自动完成，不再作为独立管理功能暴露。

## SSE 事件

`delta`、`citation`、`suggestion`、`done`、`error`。引用来源按问题类型自动选择 `DOCUMENT`、`TOOL`、`WEB`，Web 只在本地无依据或明确要求最新信息时参与。移动端界面只展示文字回答和推荐问题，引用数据仍保存在接口与数据库中供审计。每帧格式：

```text
event: delta
data: {"content":"增量文本"}
```

## AI 内部接口

前缀 `/internal/v1`，需 `X-Internal-Token`：

- `POST /index`、`POST /unindex`、`POST /retrieve`
- `POST /chat/stream`、`POST /summarize`
- 业务内部工具 `POST /internal/v1/tools/query` 支持 `find_documents`、`list_categories`、`get_service_channels`、`get_card_balance`
- `GET /health`

`get_card_balance` 只能按当前登录普通用户查询本人账户；尝试按学号或卡号查询他人账户会返回 403，AI 服务会直接给出隐私提示，不继续检索网页。

## 业务错误码

`0` 成功；`100xxx` 认证权限；`200xxx` 文档；`300xxx` RAG；`400xxx` 模型；`500xxx` 搜索；`700xxx` 会话与反馈；`800xxx` 通用限流；`900001` 未处理异常。
