"""PPT 渲染封装：以 luobo-ppt（第三方 Agent Skill）为渲染引擎，替代手工蓝图。

设计意图（方案 A：整体接入为新渲染引擎）
- 我们的生成链 produce 出结构化 deck（outline + pages），与之前一致；
- 本模块把 deck 映射成 luobo-ppt 的 deck.json / style.json，调用其确定性脚本
  plan_deck.py（自动选版式 + 容量防溢出）与 build_deck.py（拼装可编辑 .pptx），
  全程不需要 LLM、不需要 AI 生图（--level light 走程序化图标兜底）。
- 失败时回退到原 ppt_generator.deck_to_pptx（Academic Blueprint），保证 /v1/ppt 契约不破。

luobo-ppt 已 vendored 在 <project>/third_party/luobo-ppt（MIT）。
"""

import json
import logging
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from app.tools.ppt_generator import deck_to_pptx, classify_layout, _parse_metric

logger = logging.getLogger(__name__)

# 路径（相对本文件 app/tools/luobo_renderer.py）
_HERE = Path(__file__).resolve().parent
_PROJECT = _HERE.parent.parent
LUOBO_SCRIPTS = _PROJECT / "third_party" / "luobo-ppt" / "scripts"
STYLE_PATH = _HERE / "styles" / "academic_blue.json"
VENV_PY = _PROJECT / ".venv" / "Scripts" / "python.exe"


# --------------------------------------------------------------------------
# 1) 我们的 deck → luobo-ppt 的 deck.json
# --------------------------------------------------------------------------
def _split(bullet: str):
    """按首个『：/ :』拆出标题与正文（前 20 字内才算）。"""
    b = str(bullet).strip()
    for sep in ("：", ":"):
        if sep in b[:20]:
            h, r = b.split(sep, 1)
            return h.strip(), r.strip()
    return "", b


def _page_to_luobo(pg: dict, n: int, layout: str) -> dict:
    """把一页（title/bullets/note）映射成 luobo 的 slide。

    layout 来自 classify_layout：statement / two_column / card_grid /
    timeline / big_number / bullet_body。统一映射到 luobo 的 type：
        statement→statement, two_column→rows_side, card_grid→grid,
        timeline→process, big_number→stats, bullet_body→list。
    """
    title = pg.get("title", "")
    bullets = pg.get("bullets", []) or []
    note = pg.get("note", "")

    items = []
    for b in bullets:
        h, r = _split(b)
        items.append({"title": h, "text": r} if h else {"text": r})

    if layout == "statement":
        head = bullets[0] if bullets else title
        body = " ".join(str(b) for b in bullets[1:]) if len(bullets) > 1 else ""
        return {"n": n, "type": "statement", "headline": head, "body": body, "notes": note}

    if layout == "two_column":
        side: dict[str, Any] = {}
        if bullets:
            h, r = _split(bullets[0])
            side = {"title": h or str(bullets[0]), "body": r}
        rest = []
        for b in bullets[1:]:
            hh, rr = _split(b)
            rest.append({"title": hh, "text": rr} if hh else {"text": rr})
        return {"n": n, "type": "rows_side", "title": title, "side": side, "items": rest, "notes": note}

    if layout == "big_number":
        stats = [{"value": v, "label": l} for v, l in (_parse_metric(b) for b in bullets) if v]
        if stats:
            return {"n": n, "type": "stats", "title": title, "items": stats, "notes": note}
        # 没解析出数字 → 退回普通列表，避免空白页
        return {"n": n, "type": "list", "title": title, "items": items, "notes": note}

    if layout == "timeline":
        return {"n": n, "type": "process", "title": title, "items": items, "notes": note}

    if layout == "card_grid":
        return {"n": n, "type": "grid", "title": title, "items": items, "notes": note}

    # bullet_body 或其它
    return {"n": n, "type": "list", "title": title, "items": items, "notes": note}


def to_luobo_deck(deck: dict) -> dict:
    """把生成链产出的 deck 转成 luobo-ppt 的 deck.json 结构。"""
    outline = deck.get("outline", {}) or {}
    title = outline.get("title") or deck.get("title") or "课程课件"
    subtitle = outline.get("subtitle", "")
    pages = deck.get("pages", []) or []

    slides: list[dict] = []
    n = 0

    # 封面
    n += 1
    slides.append({
        "n": n, "type": "cover",
        "kicker": "软件建模课程",
        "title": title,
        "subtitle": subtitle,
    })

    prev_section = None
    sec_num = 0
    for pg in pages:
        sec = str(pg.get("section", "") or "")
        if sec and sec != prev_section:
            sec_num += 1
            n += 1
            slides.append({"n": n, "type": "section", "number": f"{sec_num:02d}", "title": sec})
            prev_section = sec
        n += 1
        layout = pg.get("layout") or classify_layout(pg)
        slides.append(_page_to_luobo(pg, n, layout))

    meta = {
        "title": title,
        "footer": "AI 教学智能体平台 · 软件建模课程",
        "series": "",
        "total": n,
        "auto_page": True,
        "auto_number": True,
    }
    return {"meta": meta, "slides": slides}


# --------------------------------------------------------------------------
# 2) 调用 luobo-ppt 确定性脚本
# --------------------------------------------------------------------------
def _run(script: str, work: Path, *args: str) -> subprocess.CompletedProcess:
    if not VENV_PY.exists():
        raise RuntimeError(f"venv python 不存在：{VENV_PY}")
    if not (LUOBO_SCRIPTS / script).exists():
        raise RuntimeError(f"luobo 脚本不存在：{LUOBO_SCRIPTS / script}")
    cmd = [str(VENV_PY), str(LUOBO_SCRIPTS / script), str(work), *[str(a) for a in args]]
    # 渲染完全离线（无 AI 图、无 soffice），去掉代理避免误连
    env = dict(os.environ)
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "NO_PROXY"):
        env.pop(k, None)
    logger.info("luobo run: %s", " ".join(cmd))
    return subprocess.run(cmd, cwd=str(LUOBO_SCRIPTS), capture_output=True, text=True, timeout=300, env=env)


def _render_luobo(deck: dict, out_path: str | Path) -> Path:
    # luobo 脚本以 LUOBO_SCRIPTS 为 cwd 解析路径，必须传绝对路径，否则会找错目录
    out = Path(out_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    # 每个请求独立工作目录，避免并发互相覆盖
    work = (out.parent / f"_luobo_{uuid.uuid4().hex[:8]}").resolve()
    work.mkdir(parents=True, exist_ok=True)
    try:
        ldeck = to_luobo_deck(deck)
        (work / "deck.json").write_text(
            json.dumps(ldeck, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        shutil.copyfile(str(STYLE_PATH), str(work / "style.json"))

        # ① 规划版式（确定性：自动选版式 + 容量防溢出），--level light 不出 AI 插画
        r = _run("plan_deck.py", work, "--level", "light")
        if r.returncode != 0:
            raise RuntimeError(f"plan_deck 失败：{r.stderr[-1500:]}")
        # ② 拼装可编辑 .pptx
        r = _run("build_deck.py", work, "--out", str(out))
        if r.returncode != 0:
            raise RuntimeError(f"build_deck 失败：{r.stderr[-1500:]}")

        # build_deck 把 layout_dump.json 写在 out 同级目录；render_lite 需要它在 work/out/
        dump_src = out.parent / "layout_dump.json"
        if dump_src.exists():
            (work / "out").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(dump_src), str(work / "out" / "layout_dump.json"))
            dump_src.unlink(missing_ok=True)  # 不污染 outputs 目录

        # ③ 近似预览 PNG（无 LibreOffice 也能出），失败不阻断交付
        try:
            _run("render_lite.py", work, "--dpi", "80")
        except Exception as e:  # noqa: BLE001
            logger.warning("luobo 预览生成跳过：%s", e)
        return out
    finally:
        # 保留 work 目录（含 deck/plan/style/layout_dump/png）便于排查与预览
        pass


def render_pptx(deck: dict, out_path: str | Path) -> Path:
    """渲染入口：优先 luobo-ppt，失败回退到原蓝图渲染器。

    返回生成的 .pptx 路径；契约与 deck_to_pptx 一致。
    """
    try:
        return _render_luobo(deck, out_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("luobo-ppt 渲染失败，回退到蓝图渲染器：%s", e)
        return deck_to_pptx(deck, out_path)
