# API 接口与 Web 展示方案（v13）

> 定义对外接口契约与演示 Web 页。接口先行，前端与 Agent 可并行开发。

---

## 1. API 总览（FastAPI）

| 方法 | 路径 | 功能 | 对应 Agent |
|---|---|---|---|
| POST | `/api/chat` | 智能问答 | QA Agent |
| POST | `/api/ppt/generate` | 生成 PPT | PPT Agent |
| POST | `/api/lesson/generate` | 生成教案 | 教案 Agent |
| POST | `/api/uml/generate` | UML 建模（生成图+审查） | UML Agent |
| POST | `/api/uml/review` | 仅审查（批改模式） | UML Agent |
| GET | `/api/files/{token}` | 获取生成文件（PNG/PPTX） | — |
| GET | `/health` | 健康检查 | — |

## 2. 接口契约（示例：UML 建模）

**POST /api/uml/generate**

请求：
```json
{
  "query": "设计校园二手交易系统。学生可以发布商品，管理员审核商品，买家购买商品。",
  "mode": "normal"   // normal | practice(练习模式) | review(批改模式)
}
```

响应：
```json
{
  "code": 0,
  "data": {
    "analysis": {
      "actors": ["学生", "管理员", "买家"],
      "usecases": ["发布商品", "审核商品", "购买商品"]
    },
    "image_url": "/api/files/f_xxx.png",
    "plantuml_source": "@startuml ...",
    "review_report": {
      "passed": false,
      "checks": [{"type": "boundary", "level": "error", "message": "...", "suggestion": "..."}],
      "llm_review": {"passed": true, "comment": "..."}
    }
  }
}
```

**错误约定**：`code != 0` 时带 `message`；统一错误格式：
```json
{"code": 40001, "message": "需求信息不完整，请补充：还有哪些参与者？"}
```

## 3. 通用约定

- 鉴权：v13 演示期使用简单 Token（Header `X-Api-Token`），正式接入统一认证；
- 限流：按 IP/Token 限流（如 60 req/min），防止滥用与费用失控；
- 参数校验：pydantic 模型校验请求体，非法参数返回 400 + 说明；
- 超时：模型调用设超时（问答 10s / 生成 60s / UML 30s），超时返回友好错误；
- 幂等与重试：生成类接口支持 `request_id` 幂等，失败可重试；
- 日志：每个请求记录 `request_id → 模型 → 耗时 → 结果码`，便于复盘。

## 4. Web 展示页

### 4.1 页面结构（演示版）

```
AI教学智能体平台 v13
├─ 首页：三大能力入口（辅助教学 / 辅助设计 / 辅助实践）
├─ 智能问答页：输入问题 → 回答 + 教材来源
├─ 教学资源页：输入课题 → 生成 PPT / 教案（大纲预览 + 下载）
├─ UML 建模页：输入需求 → 参与者/用例 → 图 + 审查报告
└─ 演示页：一键跑通 4 环节 Demo
```

### 4.2 技术实现

- v13 演示期：FastAPI 静态页（HTML + JS + CSS），调 `/api/*`；
- 或 Streamlit 快速原型（最快出效果，适合给老师看）；
- UML 图/PPT 用 `<img>` / 下载链接展示；
- 教学平台对接：预留 iframe 嵌入与 API 对接两种方式。

### 4.3 演示页（领导展示版）交互

1. 智能问答：输入"什么是用例图？" → 展示概念+案例+教材来源；
2. 资源生成：输入"生成 90 分钟用例图教学 PPT" → 展示大纲 + 下载；
3. UML 生成（重点）：输入"设计校园报修系统…" → 展示参与者/用例 → 点击"生成 UML 图" → 出图；
4. AI 质检：故意输入"数据库作为参与者" → AI 拦截并讲解。

## 5. 文件管理

- 生成文件（PNG / PPTX / 教案 docx）统一存 `app/static/generated/`，按日期/request_id 命名；
- 提供访问 URL：`/api/files/{token}`，带时效（演示期 24h）；
- 定期清理过期文件（定时任务或懒清理）。

## 6. 后续升级

- 接入学校统一登录（SSO）；
- 教学平台深度集成（作业提交、成绩记录）；
- 移动端自适应页面（Web 优先，不做原生 App）。
