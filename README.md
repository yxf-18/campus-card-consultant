# 校园一卡通使用智能咨询工具

基于概要设计实现的四项目单仓库应用，包含两个纯 Python 后端和两个 Vue 3 前端。

当前版本以聊天为唯一业务入口，支持本人余额、消费明细、统计、环比、补助解释、余额预测、挂失、解挂、补办预约、本地模拟充值和工单进度，也可以回答天气、常识、新闻等校园卡以外的普通问题。金额、笔数、占比、预测值和限额检查全部由后端工具计算；云端大模型、本地 RAG、本地数据库工具和实时 Web Search 会根据问题自动组合。所有办理结果仅写入本地演示库，不产生真实资金或真实校园卡系统操作。

## 项目结构

| 项目 | 说明 | 技术 | 端口 |
| --- | --- | --- | --- |
| `backend-api` | 认证、文档、会话、反馈、后台运营与统计 | FastAPI + SQLAlchemy | 8000 |
| `backend-ai` | 文件解析、切片、嵌入、Chroma 检索、LLM 与搜索编排 | FastAPI + Chroma | 8001 |
| `admin-web` | 管理员 PC 页面 | Vue 3 + Element Plus | 5173 |
| `mobile-web` | 游客/普通用户移动页面 | Vue 3 + Vant | 5174 |

公共目录：`database` 保存 MySQL 脚本，`deploy` 保存 Nginx 配置，`docs` 保存接口说明，`scripts` 保存 PowerShell 启动脚本。

## 快速启动（Windows）

1. 复制根目录 `.env.example` 为 `.env`，按需修改配置。
2. 初始化 Python 虚拟环境并安装依赖：

```powershell
cd D:\AIProject\campus-card-consultant
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend-api\requirements.txt -r backend-ai\requirements.txt
```

3. 安装前端依赖：

```powershell
npm --prefix admin-web install
npm --prefix mobile-web install
```

4. 启动四个开发服务：

```powershell
.\scripts\start-dev.ps1
```

如果 PowerShell 提示“在此系统上禁止运行脚本”，先为当前窗口放开一次执行策略再运行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

启动脚本会先检查 Python、虚拟环境、npm 是否可用；缺少依赖或 `.venv` 已失效时会直接给出中文提示，而不是抛出一串英文堆栈。

也可以分别执行：

```powershell
cd backend-api
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

```powershell
cd backend-ai
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

```powershell
npm --prefix admin-web run dev
npm --prefix mobile-web run dev
```

- 管理后台：<http://127.0.0.1:5173/login>（管理员专用，不能登录移动端）
- 移动端：<http://127.0.0.1:5174>（打开后先进入登录页）
- 业务 Swagger：<http://127.0.0.1:8000/docs>
- AI Swagger：<http://127.0.0.1:8001/docs>

两个 `/docs` 页面使用仓库内置的 Swagger UI 资源，断网或 CDN 不可用时仍可正常显示。

## 演示账号

| 角色 | 账号 | 密码 |
| --- | --- | --- |
| 管理员 | `admin` | `Admin12345` |
| 普通用户 | `student` | `Student123` |
| 普通用户 | `student01` | `Student123` |
| 普通用户 | `student02` | `Student123` |
| 挂失演示用户 | `lost_demo` | `Student123` |

演示用户绑定信息：`student` 手机号 `13800000000`、学号 `20230001`、余额 `128.50` 元；`student01` 学号 `01`、余额 `66.80` 元；`student02` 手机号 `13800000002`、学号 `20230002`、余额 `88.20` 元。系统还会生成 120 个批量演示用户 `demo0001`–`demo0120`，密码均为 `Student123`，用于测试用户列表、审核和数据量场景；需要更多测试数据时，在 `.env` 里调整 `SEED_DEMO_USER_COUNT`（例如 `300`）后重新启动即可补齐。

移动端不提供自助注册。账号由学校统一开通并保存在数据库中，没有账号数据无法登录；首次登录后如缺少手机号/学号会进入资料完善页。手机号和邮箱首次补录可直接生效，已有值再修改会提交管理员审核。

登录页支持用户名、手机号、学号三种方式，提供密码显示切换、记住账号和登录帮助；账号或密码错误、网络异常都会以中文提示直接显示在登录框内，输入错误后可直接重试。后台“资料审核”页面可查看、通过或驳回手机号/邮箱变更申请，审核通过前原信息继续有效。

首次启动会自动创建 SQLite 开发数据库、五个分类、二十六份标注为演示用途的资料、120 个批量演示用户、3～6 个月校园卡流水、补助与异常交易、3 个服务网点和未来 7 天预约时段、演示问答与反馈、资料变更申请和默认配置。正式部署请修改管理员密码，并使用 MySQL。

## 数据库

开发环境默认使用 `backend-api/data/campus_card.db`。MySQL 8.0 基础表脚本位于 `database/database_schema_v1.3.sql`，对话账单和工单能力表位于 `database/conversation_features_v1.sql`。

如需使用 Python 初始化 MySQL，可先安装 PyMySQL，在根 `.env` 中配置：

```env
DATABASE_URL=mysql+pymysql://root:password@127.0.0.1:3306/campus_card_consultant?charset=utf8mb4
```

然后执行：

```powershell
cd backend-api
..\.venv\Scripts\python.exe -m app.seed
```

正式环境建议先执行 SQL 脚本创建数据库和表，再运行种子脚本补齐默认配置与演示数据。Navicat 连接方式和验证 SQL 见 `docs/NAVICAT_GUIDE.md`。

Chroma 为可选增强依赖。未安装时 AI 服务自动使用本地持久化向量文件完成检索；需要 Chroma 时执行 `pip install -r backend-ai/requirements-chroma.txt`，并将 `backend-ai/.env` 中 `VECTOR_BACKEND` 设为 `chroma`。

## 外部 AI 配置

未配置外部密钥时，系统仍可完成文档上传、索引、检索、流式问答和引用展示：

- 嵌入：默认使用确定性的 384 维哈希嵌入。
- 大模型：未配置时使用基于知识库片段的抽取式回答。
- 问答来源按问题自动组合：校园卡问题使用本地 RAG、数据库工具和西安理工大学官网检索，联网结果限定 `xaut.edu.cn`；天气、常识、新闻等普通问题直接使用通用 Web Search 和云端模型，不再强制追加“校园卡”检索词。Web Search 支持 Tavily API，也提供 360 搜索与 Bing RSS 无密钥回退。
- 校园卡余额等个人业务数据保存在本地 `campus_card_account` 表；移动端“我的”页面和受控数据库工具都只能查询当前登录用户本人账户，普通用户不能查询他人余额，管理员也不能通过移动端工具查询学生余额。
- 实时网页检索结果会在后端保留引用记录用于追踪，但移动端回答正文不显示检索日期、页面日期、来源标题或链接，只保留简洁答案。`SEARCH_SITE_DOMAIN` 默认使用 `xaut.edu.cn`，用于限定西安理工大学校园卡官网搜索。

接入 OpenAI 兼容服务时配置：

```env
LLM_BASE_URL=https://your-provider/v1
LLM_API_KEY=...
LLM_MODEL=...
EMBEDDING_PROVIDER=hash or openai_compatible
EMBEDDING_BASE_URL=https://your-provider/v1
EMBEDDING_API_KEY=...
EMBEDDING_MODEL=...
SEARCH_PROVIDER=tavily
TAVILY_API_KEY=...
SEARCH_SITE_DOMAIN=your-school.edu.cn
DEMO_MODE=true
```

密钥只放在后端 `.env` 中，不进入前端构建产物。

## 测试

```powershell
cd backend-api
..\.venv\Scripts\python.exe -m pytest -q

cd ..\backend-ai
..\.venv\Scripts\python.exe -m pytest -q

npm --prefix admin-web run build
npm --prefix mobile-web run build
npm --prefix admin-web test
npm --prefix mobile-web test
```

## 安全与业务边界

- 密码使用 Scrypt 加盐摘要保存，接口永不回显。
- 业务接口使用 JWT，后台接口强制管理员角色，用户接口校验会话归属。
- 管理员账号不可封禁；封禁操作仅针对普通用户。
- 手机号、邮箱修改需要管理员在“资料审核”页面通过后才会写入账号资料；学号、昵称可直接修改。
- 文档管理不再暴露“同步任务”页面或接口，发布后的索引由后台自动完成。
- AI 服务与业务后端通过 `X-Internal-Token` 鉴权。
- 云端模型只接收必要的检索片段；本地数据库工具只允许白名单只读查询。
- 挂失、解挂、补办预约和充值在 `DEMO_MODE=true` 时只操作本地演示库；`DEMO_MODE=false` 时写操作返回未开放。退款和真实支付不在实现范围内。
- 写操作采用 prepare/commit 两阶段确认，确认令牌一次性、5 分钟有效并绑定当前用户、卡号、动作和参数摘要；重复提交按幂等键返回原工单。
- 演示资料不含学校真实金额、电话或经办时限，正式上线前应替换为学校正式文件。
