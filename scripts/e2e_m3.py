"""M3 端到端真实验证脚本：真实调 LLM 生成 PPT + 教案并落盘。

用法：.venv/Scripts/python scripts/e2e_m3.py
"""

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.chains.generation_chain import (
    generate_lesson_plan,
    generate_ppt_deck_async,
)
from app.tools.docx_exporter import lesson_to_docx, lesson_to_markdown
from app.tools.ppt_generator import deck_to_pptx


def check_ppt() -> None:
    t = time.time()
    deck = asyncio.run(generate_ppt_deck_async("用例图建模入门", 45))
    elapsed = time.time() - t
    outline, pages = deck["outline"], deck["pages"]
    names = [f"{s['name']}({s['page_count']})" for s in outline["sections"]]
    print(f"[PPT] 总耗时 {elapsed:.1f}s | 大纲 {len(outline['sections'])} 节 | 共 {len(pages)} 页")
    print("大纲:", names)
    out = deck_to_pptx(deck, ROOT / "outputs" / "ppt" / "e2e_test.pptx")
    print(f"文件: {out} {out.stat().st_size // 1024}KB")
    first = pages[0]
    print(f"样例页: {first['title']} | bullets={first['bullets'][:2]} | note={first['note'][:30]}")
    with_note = sum(1 for p in pages if p.get("note"))
    print(f"备注覆盖: {with_note}/{len(pages)}")


def check_lesson() -> None:
    t = time.time()
    lesson = generate_lesson_plan("用例图教学设计", 45)
    elapsed = time.time() - t
    missing = lesson.missing_fields()
    data = lesson.model_dump()
    print(f"[教案] 总耗时 {elapsed:.1f}s | 流程环节数 {len(data['teaching_flow'])} | 缺失字段 {missing or '无'}")
    md = lesson_to_markdown(data)
    docx = lesson_to_docx(data, ROOT / "outputs" / "lesson" / "e2e_test.docx")
    md_path = ROOT / "outputs" / "lesson" / "e2e_test.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"文件: {docx} {docx.stat().st_size // 1024}KB | markdown {len(md)} 字")


if __name__ == "__main__":
    check_ppt()
    check_lesson()
    print("E2E DONE")
