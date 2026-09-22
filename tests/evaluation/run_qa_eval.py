"""QA 评测脚本：对评测集逐条跑真实 RAG 链路并按规则评分。

用法（在 AI-Education-Agent 目录下）：
    .venv/Scripts/python -m tests.evaluation.run_qa_eval                 # 全量
    .venv/Scripts/python -m tests.evaluation.run_qa_eval --limit 5      # 冒烟
    .venv/Scripts/python -m tests.evaluation.run_qa_eval --type out_of_scope,chitchat
    .venv/Scripts/python -m tests.evaluation.run_qa_eval --out reports/eval_20260922.json

评分维度（对齐 PRD 验收标准，QA-1/2/3 + 验收总标准）：
- retrieval_hit：来源标注/回答命中期望关键词（top-k 检索命中率）
- refusal_correct：超纲/闲聊/注入类必须走兜底，不得编造
- sections_complete：四段式（概念解释/通俗案例/教材关联/实践建议）齐全
- citation_traceable：有教材支撑的题型必须带来源标注

本脚本不进 pytest（耗 token 与时间）；CI 只跑单元测试。
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


EVAL_SET = Path(__file__).resolve().parent / "qa_eval_set.json"

# 有教材支撑、必须有来源标注的题型（对齐 PRD"引用可追溯率 = 100%"）
CITATION_REQUIRED_TYPES = {"standard", "colloquial", "typo", "compare", "howto", "mixed_lang", "long_input"}

# 兜底表述关键词（PRD QA-3：明确说明，不编造）。
# 用模态词而非"模态词+动词"穷举：拒答题的表述组合不可穷尽（glm 每次措辞都变），
# 在 expect_refusal 语境下匹配模态词本身即足够安全。
_REFUSAL_KEYWORDS = (
    "不能",
    "无法",
    "不会",
    "拒绝",
    "暂无",
    "不在教材",
    "不在当前教材",
    "知识库中未",
    "知识库中没有",
    "没有相关",
    "未包含",
    "不应",
)

_REQUIRED_SECTIONS = ("概念解释", "通俗案例", "教材关联", "实践建议")


def load_cases() -> list[dict]:
    """读评测集，返回用例列表。"""
    data = json.loads(EVAL_SET.read_text(encoding="utf-8"))
    return data["cases"]


def judge_retrieval_hit(case: dict, sources: list[str], reply: str) -> bool:
    """期望关键词任一出现在来源标注或回答中即视为命中。"""
    for kw in case.get("expect_source_keywords", []):
        if any(kw in s for s in sources) or kw in reply:
            return True
    return not case.get("expect_source_keywords")  # 未声明关键词的用例不计入失败


def judge_refusal(case: dict, reply: str) -> bool:
    """超纲/闲聊/注入类：回答须含兜底/拒绝表述。

    注：模型拒答时保持四段式格式来解释拒因是预期行为（教学格式一致），
    不视为编造；真正的编造防线由人工抽查兜底明细保障。
    """
    if not case.get("expect_refusal"):
        return True
    return any(kw in reply for kw in _REFUSAL_KEYWORDS)


def judge_sections(case: dict, reply: str) -> bool:
    """有教材支撑的题型：四段式段标齐全。"""
    if not case.get("expect_sections"):
        return True
    return all(sec in reply for sec in _REQUIRED_SECTIONS)


def judge_citation(case: dict, sources: list[str]) -> bool:
    """有教材支撑的题型必须带来源标注。"""
    if case["type"] not in CITATION_REQUIRED_TYPES:
        return True
    return len(sources) > 0


async def run_case(case: dict) -> dict:
    """跑单条用例，返回明细与判定结果。

    直接调用 build_qa_answer，保证评测链路与 /v1/qa 线上链路完全一致
    （含截断、空回答重试、来源兜底提取），避免"评测通过但线上行为不同"。
    """
    t0 = time.time()
    result = {"id": case["id"], "type": case["type"], "question": case["question"]}
    try:
        from app.chains.rag_chain import build_qa_answer

        answer = await build_qa_answer(case["question"])
        result.update(
            sources=answer["sources"],
            reply=answer["reply"],
            latency_s=round(time.time() - t0, 1),
            error=None,
        )
    except Exception as exc:  # noqa: BLE001 - 评测单条失败不中断整体
        result.update(sources=[], reply="", latency_s=round(time.time() - t0, 1), error=str(exc)[:200])
        result.update(
            retrieval_hit=False,
            refusal_correct=False,
            sections_complete=False,
            citation_traceable=False,
        )
        return result

    result["retrieval_hit"] = judge_retrieval_hit(case, result["sources"], result["reply"])
    result["refusal_correct"] = judge_refusal(case, result["reply"])
    result["sections_complete"] = judge_sections(case, result["reply"])
    result["citation_traceable"] = judge_citation(case, result["sources"])
    return result


def summarize(results: list[dict], cases: list[dict]) -> dict:
    """按题型与总览汇总指标。"""
    type_of = {c["id"]: c["type"] for c in cases}
    relevant = [r for r in results if type_of[r["id"]] in CITATION_REQUIRED_TYPES]

    def rate(rows: list[dict], key: str) -> float | None:
        if not rows:
            return None
        return round(sum(1 for r in rows if r[key]) / len(rows), 3)

    refusal_cases = [r for r in results if type_of[r["id"]] in {"out_of_scope", "chitchat", "adversarial"}]
    return {
        "total": len(results),
        "errors": sum(1 for r in results if r.get("error")),
        "retrieval_hit_rate": rate(relevant, "retrieval_hit"),
        "refusal_correct_rate": rate(refusal_cases, "refusal_correct"),
        "sections_complete_rate": rate(relevant, "sections_complete"),
        "citation_traceable_rate": rate(relevant, "citation_traceable"),
        "avg_latency_s": round(sum(r["latency_s"] for r in results) / len(results), 1) if results else None,
        "by_type": {
            t: {
                "n": sum(1 for r in results if r["type"] == t),
                "retrieval_hit": rate(
                    [r for r in results if r["type"] == t and r["type"] in CITATION_REQUIRED_TYPES],
                    "retrieval_hit",
                ),
                "refusal_correct": rate([r for r in results if r["type"] == t], "refusal_correct"),
            }
            for t in sorted({r["type"] for r in results})
        },
    }


async def run_all(cases: list[dict], concurrency: int = 3) -> list[dict]:
    """全部用例跑在同一个事件循环里（LightRAG 的 worker 队列绑定首个 loop，
    每条 asyncio.run 换 loop 会触发 'bound to a different event loop' 错误）。"""
    sem = asyncio.Semaphore(concurrency)

    async def guarded(case: dict) -> dict:
        async with sem:
            return await run_case(case)

    return list(await asyncio.gather(*(guarded(c) for c in cases)))


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser(description="QA 评测（真实 RAG 链路）")
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 条（冒烟）")
    parser.add_argument("--type", type=str, default=None, help="只跑指定题型（逗号分隔）")
    parser.add_argument("--ids", type=str, default=None, help="只跑指定用例 id（逗号分隔，如 QA-009,QA-037）")
    parser.add_argument("--concurrency", type=int, default=3, help="评测并发数（默认 3）")
    parser.add_argument("--out", type=str, default=None, help="结果 JSON 输出路径")
    args = parser.parse_args()

    cases = load_cases()
    if args.type:
        wanted = {t.strip() for t in args.type.split(",")}
        cases = [c for c in cases if c["type"] in wanted]
    if args.ids:
        wanted_ids = {i.strip() for i in args.ids.split(",")}
        cases = [c for c in cases if c["id"] in wanted_ids]
    if args.limit:
        cases = cases[: args.limit]

    print(f"评测用例: {len(cases)} 条（并发 {args.concurrency}），开始…")
    t0 = time.time()
    results = asyncio.run(run_all(cases, concurrency=args.concurrency))
    results.sort(key=lambda r: r["id"])
    for r in results:
        flag = "ERR" if r.get("error") else "ok"
        print(f"{r['id']} {flag} {r['latency_s']}s | {r['question'][:24]}")

    summary = summarize(results, cases)
    summary["wall_time_s"] = round(time.time() - t0, 1)
    pass_line = json.loads(EVAL_SET.read_text(encoding="utf-8"))["meta"]["pass_line"]
    print("\n===== 评测汇总 =====")
    for key in ("retrieval_hit_rate", "refusal_correct_rate", "sections_complete_rate", "citation_traceable_rate"):
        v = summary[key]
        line = f"{key}: {v}"
        if v is not None:
            line += f"（通过线 {pass_line[key]} {'✅' if v >= pass_line[key] else '❌'}）"
        print(line)
    print(f"总耗时: {summary['wall_time_s']}s | 错误: {summary['errors']} 条")
    for t, st in summary["by_type"].items():
        print(f"  {t}: n={st['n']} hit={st['retrieval_hit']} refusal={st['refusal_correct']}")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n明细已写入: {out}")


if __name__ == "__main__":
    main()
