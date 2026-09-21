# AI-Education-Agent（v13 开发代码库）

面向「AI 教学智能体平台 v13」的开发代码仓库。文档体系（PRD / 技术方案 / 规范）见上级目录 `AI教学智能体平台-v13/`，本仓库只承载代码与本地配置。

## 当前进度（W1：环境 + 骨架 + 模型接入）

- [x] 项目骨架（app/ 目录结构、FastAPI 入口）
- [x] 配置层（pydantic-settings，密钥走 .env）
- [x] 模型工厂（DeepSeek V4.1，OpenAI 兼容接口）
- [x] /health 健康检查 + /v1/chat 一句话问答连通验证
- [ ] 后续：W2 智能问答 + 教材知识库（LightRAG）→ W3 PPT/教案 → W4 UML Agent

## 快速开始

```bash
# 1. 创建虚拟环境并安装依赖
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# 2. 配置密钥
copy .env.example .env        # 填入 DEEPSEEK_API_KEY（已配置则跳过）

# 3. 启动服务
uvicorn app.main:app --reload

# 4. 验证
#    健康检查：   GET  http://127.0.0.1:8000/health
#    一句话问答： POST http://127.0.0.1:8000/v1/chat  {"message": "你好"}
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
| langgraph | W2+ 多 Agent 编排 |
| pytest / ruff | 测试与静态检查 |

## 开发规范

所有开发遵循上级 `01-规范与流程/`：编码与命名规范、代码质量红线（禁止硬编码密钥、禁止提交 .env）、AI 辅助代码必须人工 review。
