# AI-Education-Agent（v13 开发代码库）

面向「AI 教学智能体平台 v13」的开发仓库。文档体系（规范 / PRD / 技术方案 / 项目管理）在 `docs/` 目录，与代码同库管理。

> 教材源稿（`docs/02-需求文档PRD/_教材源稿提取/`，docx 提取稿）自 2026-09-22 起随仓库分发；docx/pdf 原件仍不进 Git。授权事宜请联系文档提供方确认。

## 当前进度（W2：教材知识库 + 智能问答 Agent）

### W1（已完成）
- [x] 项目骨架（app/ 目录结构、FastAPI 入口）
- [x] 配置层（pydantic-settings，密钥走 .env）
- [x] 模型工厂（DeepSeek V4.1，OpenAI 兼容接口）
- [x] /health 健康检查 + /v1/chat 一句话问答连通验证

### W2（已完成，真实演示跑通）
- [x] 教材源稿提取（4 份 docx → markdown，落盘于 `docs/02-需求文档PRD/_教材源稿提取/`）
- [x] 知识库构建脚本（`python -m app.knowledge_base.build [--force]`）
  - LightRAG 1.5.7 + fastembed（bge-small-zh-v1.5，512 维，离线 ONNX）
  - 已入库 14 块 / 24 分块向量，图谱 597 节点 / 954 边（实体抽取已用真实 LLM 补齐）
- [x] 智能问答链路（chains/rag_chain）：hybrid 三路召回 → 来源标注提取 → 四段式回答
- [x] POST /v1/qa 接口（503 未建索引 / 502 兜底 / 504 超时），端到端实测通过（2026-09-21）
- [x] 演示安全加固（2026-09-22）
  - `/v1/qa` 并发限流（Semaphore，默认 3）+ 整体墙钟 60s 超时（LightRAG 内部单次 LLM 超时 240s，必须整体兜底）
  - 检索预算收紧：chunk_top_k=6、max_total_tokens=8000（LightRAG 默认 20/30000 会返回 2 万字符上下文）+ 应用层 12000 字符兜底截断
  - `enable_rerank=False` 消除未配置重排模型的重复告警
  - `max_tokens` 2048→4096（deepseek-flash 为推理模型，reasoning 与回答共用预算）+ 空 content 自动重试 1 次
  - 测试 2 → 20 个：document_reader / rag_chain（截断与空回答重试）/ /v1/qa 全路径（200/503/504/502/422/并发上限）
- [x] QA 评测集（42 条，真人提问模式：口语/错别字/超纲/闲聊/注入/超长/中英混合）
  - 基线（glm-5.3-flash）：检索命中 97% ✅ / 兜底 100% ✅ / 四段式 97% ✅ / 引用 97%（1 条平台 504）
  - 复现：`python -m tests.evaluation.run_qa_eval --out <path>.json`；报告见 `tests/evaluation/baseline_report.md`
- [x] M3 PPT 生成 Agent（W3）：大纲 7 要素 → 分节并发生成 → python-pptx 出 .pptx + 讲课备注；`POST /v1/ppt`
  - 端到端实测（45 分钟课题）：7 要素全中 / 9 页 / 备注 9/9 / 53KB；耗时 211s（超 PRD 60s，见 issue）
- [x] M3 教案生成 Agent（W3）：9 字段结构化（三维目标/重难点/流程/师生活动/练习/作业）→ Markdown + docx 导出；`POST /v1/lesson`
  - 端到端实测：9 字段无缺失 / 流程 6 环节 / docx 39KB；耗时 219s（同上）
- [x] 大模型切换 TokenRhythm 平台（glm-5.3-flash，OpenAI 兼容；原 DeepSeek 余额耗尽）
- [x] M4 UML 用例图 Agent（W4-W5）：领域模型（契约冻结）→ 规则引擎 7 条 → PlantUML 源码渲染 → PNG/SVG 本地渲染（真实 Java v1.2026.8）→ `POST /v1/uml/usecase`（render/format + 质检报告 + 下载链接）；158 项测试
- [x] M5 Web 展示（W5）：四页静态前端（首页/UML 建模/教材问答/课件教案）真实接口对接 + Playwright 浏览器端到端验证 8 项 PASS；Docker 单容器部署配置（Python 3.12 + JRE 17 + 预构建索引）

## 性能与成本预期（演示须知）

| 项 | 实测值 | 说明 |
|---|---|---|
| hybrid 检索 | ~1.1s | 每问多一次 LLM 关键词抽取调用（有 llm_response_cache 缓存时更快）；纯 naive 模式 ~0.7s |
| QA 生成 | ~10s | deepseek-flash 推理模型，reasoning 占用生成时间 |
| 端到端 /v1/qa | ~12s | 演示时提前预热（首问触发索引加载 + 模型下载校验会更慢） |
| 上下文预算 | ≤12000 字符 | 检索层 token 预算 + 应用层截断双保险 |
| 并发 | 3 路 | 超出被 Semaphore 串行化；超 60s 返回 504 |

## 快速开始

```bash
# 1. 创建虚拟环境并安装依赖
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# 2. 配置密钥
copy .env.example .env        # 填入 DEEPSEEK_API_KEY（已配置则跳过）

# 3. 构建知识库（首次会下载 Embedding 模型；需 DeepSeek 余额做实体抽取）
python -m app.knowledge_base.build

# 4. 启动服务
uvicorn app.main:app --reload

# 5. 验证
#    健康检查：   GET  http://127.0.0.1:8000/health
#    一句话问答： POST http://127.0.0.1:8000/v1/chat  {"message": "你好"}
#    教材问答：   POST http://127.0.0.1:8000/v1/qa    {"question": "什么是用例图？"}
```

### PlantUML 环境准备（本地部署必读）

PlantUML 经典引擎出图依赖本地 `tools/plantuml.jar`（二进制不进 Git，需手工下载；
另需 JRE 17+）。**缺失时 API 不会报错，而是降级为「仅生成源码模式」**——注意排查。
另外，无需 Java 的替代方案：前端「绘图引擎」选 draw.io，走纯 Python SVG 渲染器。

```bash
mkdir -p tools
# GitHub 直连慢/被墙时，可用镜像 + 断点续传（-C -）多试几次直到 java -jar 校验通过：
curl -L -C - -o tools/plantuml.jar \
  "https://ghfast.top/https://github.com/plantuml/plantuml/releases/download/v1.2025.7/plantuml-1.2025.7.jar"
# 校验（应输出版本号而非 "Invalid or corrupt jarfile"）：
java -jar tools/plantuml.jar -version
```

## 目录结构

```
app/
├── main.py              # FastAPI 入口（/health、/v1/chat）
├── config/settings.py   # 配置（.env + 默认值）
├── models/llm.py        # 模型工厂（DeepSeek V4.1）
├── chains/              # W2+：rag_chain / uml_chain / generation_chain
├── agents/              # W2+：qa / ppt / lesson / uml
├── tools/               # W2+：plantuml_tool / ppt_generator / document_reader
├── prompts/             # W2+：qa_prompt / uml_prompt / teacher_prompt
└── knowledge_base/      # W2+：教材源稿 / 索引（gitignore）
tests/                   # 与 app 对应的测试
```

## 依赖说明

| 依赖 | 用途 |
|---|---|
| fastapi / uvicorn | API 服务与启动 |
| pydantic / pydantic-settings | 请求校验与配置管理 |
| python-dotenv | 读取 .env |
| langchain / langchain-openai | LLM 调用（OpenAI 兼容接口接 DeepSeek） |
| langgraph | W3+ 多 Agent 编排 |
| lightrag-hku | 知识库索引与检索（RAG 引擎） |
| fastembed / numpy | 中文向量化（bge-small-zh-v1.5，离线 ONNX） |
| python-docx / pypdf | 教材 docx/pdf 解析 |
| pytest / ruff | 测试与静态检查 |

## 能力状态表（防止误判项目进度，AI/新人开发前必读）

| 能力 | 状态 | 代码位置 |
|---|---|---|
| 教材 QA（RAG） | ✅ 已实现 | `app/chains/rag_chain.py` |
| PPT 生成 | ✅ 已实现 | `app/chains/generation_chain.py` + `app/tools/ppt_generator.py` |
| 教案生成 | ✅ 已实现 | `app/chains/generation_chain.py` + `app/tools/docx_exporter.py` |
| 结构化输出工具 | ✅ 已实现 | `app/core/structured_output.py`（PPT/教案已接入，UML 复用） |
| UML 用例图·领域模型 | ✅ 契约已冻结 | `app/models/uml.py` / `app/models/review.py` |
| UML 用例图·规则引擎 | ✅ 已实现 | `app/rules/usecase_rules.py`（UC-B1/G1/R3/C1/R-DUP/R-GEN/R-REF 7 条） |
| UML 用例图·源码渲染 | ✅ 已实现 | `app/renderers/plantuml.py`（确定性 alias + 显示文本转义） |
| UML 用例图·PNG/SVG 渲染 | ✅ 已实现 | `app/renderers/diagram_renderer.py`（真实 Java，环境缺失自动降级源码） |
| UML 用例图·API + Web 页 | ✅ 已实现 | `app/api/uml.py` + `static/uml.html`（质检报告 + 图片下载） |
| UML 活动图 / 状态机图 | ❌ 未实现 | 仅有设计文档 |
| 多 Agent Supervisor（LangGraph） | ❌ 未实现 | 仅有架构设计 |
| 数据库 / FAISS·Milvus | ❌ 未实现 | RAG 用 LightRAG 内置存储 |

## Docker 部署（可选，服务器/演示机推荐）

单容器包含：应用 + 前端页面 + PlantUML 渲染（JRE 17）+ 预构建教材知识库索引。

### 前置条件

1. Docker Desktop（Windows）或 Docker Engine（Linux）
2. `tools/plantuml.jar` 已放置（见「PlantUML 环境准备」，jar 不进 Git，需手工下载）
3. `.env` 已配置（`cp .env.example .env` 并填入 DEEPSEEK_API_KEY）

### 构建与启动

```bash
docker compose up -d --build
```

首次启动说明：
- 容器内 fastembed 会从国内镜像（HF_ENDPOINT=hf-mirror.com）自动下载 embedding 模型（约 90MB，一次性）
- 教材知识库索引已预构建打进镜像（无需调 LLM 重建）；也可通过 compose 卷挂载外部索引

### 访问

- 前端页面：http://localhost:8000/
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

### 镜像内容说明

| 内容 | 来源 | 说明 |
|---|---|---|
| 教材知识库索引 | `app/knowledge_base/lightrag_index/`（预构建，9.9MB） | 容器启动**不需要**调用 LLM 重建 |

> ⚠️ 干净 clone 注意：`lightrag_index/` 不进 Git（见 .gitignore）。新机器上先运行
> `python -m app.knowledge_base.build`（需真实 LLM Key，一次性）生成索引，或从已有部署
> 复制该目录，否则 `docker build` 的 COPY 步骤会因目录缺失失败。
| PlantUML 渲染 | `tools/plantuml.jar`（v1.2026.8） | JRE 17 已装入镜像 |
| embedding 模型 | 首次启动下载 | ~90MB，可通过卷挂载宿主机缓存跳过 |

### 无 Docker 的传统部署

```bash
pip install -r requirements.txt        # Python 3.11+ 与 JRE 17 需预先安装
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 开发规范

所有开发遵循 `docs/01-规范与流程/`：编码与命名规范、代码质量红线（禁止硬编码密钥、禁止提交 .env）、AI 辅助代码必须人工 review。
