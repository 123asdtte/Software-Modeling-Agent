"""教案端到端复验（PPT 已通过，此脚本只跑教案）。"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.chains.generation_chain import generate_lesson_plan
from app.tools.docx_exporter import lesson_to_docx, lesson_to_markdown


def main() -> None:
    t = time.time()
    lesson = generate_lesson_plan("用例图教学设计", 45)
    elapsed = time.time() - t
    missing = lesson.missing_fields()
    data = lesson.model_dump()
    print(f"[教案] 总耗时 {elapsed:.1f}s | 流程环节数 {len(data['teaching_flow'])} | 缺失字段 {missing or '无'}")
    md = lesson_to_markdown(data)
    docx = lesson_to_docx(data, ROOT / "outputs" / "lesson" / "e2e_test.docx")
    (ROOT / "outputs" / "lesson" / "e2e_test.md").write_text(md, encoding="utf-8")
    print(f"文件: {docx} {docx.stat().st_size // 1024}KB | markdown {len(md)} 字")
    print("E2E DONE")


if __name__ == "__main__":
    main()
