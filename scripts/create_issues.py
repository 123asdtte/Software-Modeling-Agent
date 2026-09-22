"""通过 git credential 的 GitHub token 创建 issue（凭据不落盘、不回显）。"""

import subprocess

REPO = "123asdtte/Software-Modeling-Agent"

ISSUES = [
    {
        "title": "[P1] PPT/教案生成耗时 210s+，超 PRD 验收（≤60s）",
        "labels": ["P1", "performance"],
        "body": """## 现象

2026-09-22 端到端实测（45 分钟课题，glm-5.3-flash）：

| 项 | 实测 | PRD 验收 |
|---|---|---|
| PPT 生成 | 211s | ≤60s ❌ |
| 教案生成 | 219s | ≤60s ❌ |

质量指标全部达标（PPT 7 要素全中、备注 9/9；教案 9 字段无缺失、流程 6 环节）。

## 根因

glm-5.3-flash 为推理模型，单次调用 26s+（reasoning 占大头）；当前实现：大纲 1 次 + 分节 7 次并发（Semaphore 3）≈ 3 波。

## 候选方案

1. **减少调用次数**：分页合并为 2~3 批生成（输出 token 变大，需防 max_tokens 截断）；
2. **换更快模型**：平台有 glm-5.3-flashx 等候选，需实测质量；
3. **演示预热 + 固定用例**：演示前预生成（LightRAG llm_response_cache 已部分生效）；
4. **与任老师对齐验收预期**：60s 是否为硬指标。

## 相关

- 评测明细：`tests/evaluation/baseline_report.md`
- PRD：`docs/02-需求文档PRD/02_PPT生成Agent_PRD.md` 第 7 节""",
    },
    {
        "title": "[P1] TokenRhythm 平台对长输出请求不稳定（504/5xx）",
        "labels": ["P1", "bug"],
        "body": """## 现象

- QA 评测 QA-009（include/extend 长对比回答）触发网关 504（alb）；
- 教案 9 字段单次大 JSON 生成连续 2 次 `InternalServerError`（HTML 错误页）；
- 短输出请求（QA 四段式、PPT 分节小 JSON）稳定。

## 已做缓解

- `generation_chain._invoke_json` 重试已覆盖 API 层异常（教案靠它跑通）；
- QA 链路 `request_timeout`/`qa_timeout` 已放宽到 90s。

## 待办

1. 教案生成拆分为 2~3 次小调用（降单次输出长度）；
2. 演示前全流程预热 2 遍（验收清单要求）；
3. 若持续不稳定，评估备用通道（OpenAI 兼容的 fallback 工厂已预留）。""",
    },
    {
        "title": "[P2] QA 评测后续：LLM judge 评分 + QA-009 复跑 + 多轮追问评测",
        "labels": ["P2", "evaluation"],
        "body": """## 背景

42 条评测基线（glm-5.3-flash）：检索命中 97% ✅ / 兜底 100% ✅ / 四段式 97% ✅ / 引用 97%。

PRD 验收还有一项「回答正确率（人工评分）≥85%」未自动化。

## 待办

1. `--llm-judge` 开关：用 LLM 按 PRD 四段式/正确性/无编造打 1-5 分（人工评分前置初筛）；
2. QA-009 复跑（本次因平台 504 计为失败，非逻辑缺陷）；
3. PRD QA-4 多轮追问（3 轮上下文）暂未实现，评测集也未覆盖多轮用例；
4. top-3 命中率口径细化（当前为"任一来源/回答关键词命中"）。""",
    },
]


def get_token() -> str:
    """从 git credential 管理器读取 GitHub token。"""
    out = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    for line in out.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("git credential 中未找到 GitHub token")


def main() -> None:
    token = get_token()
    import httpx

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    created = 0
    with httpx.Client(timeout=30) as client:
        for issue in ISSUES:
            resp = client.post(
                f"https://api.github.com/repos/{REPO}/issues",
                headers=headers,
                json={"title": issue["title"], "body": issue["body"], "labels": issue["labels"]},
            )
            if resp.status_code == 201:
                data = resp.json()
                print(f"已创建 #{data['number']}: {issue['title']}")
                created += 1
            else:
                print(f"创建失败 HTTP {resp.status_code}: {issue['title']} -> {resp.text[:200]}")
    print(f"完成：{created}/{len(ISSUES)}")


if __name__ == "__main__":
    main()
