# 校园一卡通使用智能咨询工具

基于概要设计实现的四项目单仓库应用，包含两个纯 Python 后端和两个 Vue 3 前端。

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

演示用户绑定信息：手机号 `13800000000`，学号 `20230001`，演示校园卡余额 `128.50` 元。另有一个学号为 `01` 的查询演示用户 `student01 / Student123`，其校园卡余额为 `66.80` 元。

移动端打开根网址后固定先进入登录页；首次注册只需填写用户名、昵称、密码和隐私协议，首次登录后会引导绑定手机号与学号，绑定完成再进入业务首页。之后可使用用户名、手机号或学号登录。游客可从登录/注册页进入只读预览，不能查询文档或使用问答功能。

首次启动会自动创建 SQLite 开发数据库、五个分类、五份标注为演示用途的资料和默认配置。正式部署请修改管理员密码，并使用 MySQL。

## 数据库

开发环境默认使用 `backend-api/data/campus_card.db`。MySQL 8.0 初始化脚本位于 `database/database_schema_v1.3.sql`。

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
- 问答来源按问题自动选择：文档问题查 Chroma 知识库，账户问题查本地数据库，混合问题同时查询；只有本地无依据或明确要求最新信息时才调用 Web Search。Web Search 支持 Tavily API，也提供 360 搜索与 Bing RSS 无密钥回退。
- 校园卡余额等个人业务数据保存在本地 `campus_card_account` 表，由受控数据库工具按学号或当前登录用户查询；普通用户只能查询本人账户，管理员可查询演示范围内的其他账户。

接入 OpenAI 兼容服务时配置：

```env
LLM_BASE_URL=https://your-provider/v1
LLM_API_KEY=...
LLM_MODEL=...
EMBEDDING_PROVIDER=hash or openai_compatible
EMBEDDING_BASE_URL=https://your-provider/v1
EMBEDDING_API_KEY=...
EMBEDDING_MODEL=...
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
- AI 服务与业务后端通过 `X-Internal-Token` 鉴权。
- 云端模型只接收必要的检索片段；本地数据库工具只允许白名单只读查询。
- 充值、挂失、退款等账户操作不会被执行，系统仅提供办理指引。
- 演示资料不含学校真实金额、电话或经办时限，正式上线前应替换为学校正式文件。
