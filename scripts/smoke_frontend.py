"""前端免 LLM 冒烟测试（Playwright headless Chromium）。

只做结构与视觉回归，不触发任何 LLM 调用，秒级完成、零费用：
  1. 四页路由可达（/ /uml.html /qa.html /resources.html），页头注入成功
  2. data-icon 占位全部替换为 svg（icons.js 生效，无 emoji 残留）
  3. 子页激活导航药丸实心黑（zinc-900 #18181b）
  4. 首页 hero 全宽横带（通栏铺满视口）+ 衬线大数字字体链生效
  5. 首页能力卡 ≥1100px 视口下四列
  6. css/js 静态挂载可达，无 JS 运行时异常，样式表/脚本零 404

前置：服务已启动（默认 http://127.0.0.1:8765，可用环境变量 SMOKE_BASE 覆盖）。
依赖（可选，仅本脚本需要）：pip install playwright && playwright install chromium
用法：.venv/Scripts/python.exe scripts/smoke_frontend.py
产物：outputs/_smoke_shots/*.png（outputs 已被 gitignore）
"""

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("SMOKE_BASE", "http://127.0.0.1:8765")
SHOTS = Path("outputs") / "_smoke_shots"
SHOTS.mkdir(parents=True, exist_ok=True)

results: list[tuple[str, str, str]] = []  # (用例, 结果, 备注)


def record(name: str, ok: bool, note: str = "") -> None:
    results.append((name, "PASS" if ok else "FAIL", note))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {note}")


def wait_icons(page) -> int:
    """等 icons.js 的 data-icon 占位替换器跑完，返回剩余占位数。"""
    for _ in range(30):
        if page.locator("span[data-icon]").count() == 0:
            return 0
        page.wait_for_timeout(100)
    return page.locator("span[data-icon]").count()


def run() -> None:
    pages = ["/", "/uml.html", "/qa.html", "/resources.html"]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.set_default_timeout(10000)

        js_errors: list[str] = []
        asset_404: list[str] = []
        page.on("pageerror", lambda e: js_errors.append(str(e)))
        page.on(
            "response",
            lambda r: asset_404.append(f"{r.status} {r.url}")
            if r.status >= 400 and (".css" in r.url or ".js" in r.url)
            else None,
        )

        # ---- 1. 静态资源挂载 ----
        for path in ("/css/main.css", "/css/tokens.css", "/js/icons.js"):
            status = page.request.get(f"{BASE}{path}").status
            record(f"静态挂载 {path}", status == 200, f"HTTP {status}")

        # ---- 2. 四页逐页检查 ----
        for i, path in enumerate(pages, 1):
            resp = page.goto(f"{BASE}{path}", wait_until="load")
            page.wait_for_timeout(300)  # layout.js 页头注入
            pending = wait_icons(page)

            record(f"{path} 可达", resp is not None and resp.status == 200,
                   f"HTTP {resp.status if resp else '?'}")
            header_ok = page.locator("header").count() > 0
            record(f"{path} 页头注入", header_ok)

            record(f"{path} 图标占位清零", pending == 0, f"剩余 {pending} 个 data-icon")
            svg_count = page.locator("svg").count()
            record(f"{path} svg 图标就位", svg_count > 0, f"{svg_count} 个")

            record(f"{path} 无 JS 异常", not js_errors, "; ".join(js_errors[:2]))
            record(f"{path} 样式/脚本零 404", not asset_404, "; ".join(asset_404[:2]))

            # 子页（路径精确匹配）激活药丸应实心黑
            if path != "/":
                active = page.locator('header a[aria-current="page"], header a.active').first
                if active.count() > 0:
                    bg = active.evaluate("el => getComputedStyle(el).backgroundColor")
                    record(f"{path} 激活药丸实心黑", bg == "rgb(24, 24, 27)", bg)
                else:
                    record(f"{path} 激活药丸实心黑", False, "未找到激活导航项")

            page.screenshot(path=str(SHOTS / f"{i:02d}{path.replace('/', '_')}.png"), full_page=True)

        # ---- 3. 首页 hero 横带 + 衬线数字 + 四列卡片 ----
        page.goto(f"{BASE}/", wait_until="load")
        page.wait_for_timeout(300)
        hero = page.locator(".hero-banner")
        if hero.count() > 0:
            full_width = hero.evaluate(
                "el => el.offsetWidth === document.documentElement.clientWidth"
            )
            border = hero.evaluate(
                "el => getComputedStyle(el).borderBottomWidth + '|' + getComputedStyle(el).borderBottomColor"
            )
            record("hero 全宽横带", full_width, f"border-bottom {border}")

            serif = page.locator(".hero-stat-value .serif-num").first
            if serif.count() > 0:
                ff = serif.evaluate("el => getComputedStyle(el).fontFamily")
                size = serif.evaluate("el => getComputedStyle(el).fontSize")
                record("衬线大数字字体链", "DM Serif Display" in ff, f"{size} {ff.split(',')[0]}")
            else:
                record("衬线大数字字体链", False, "缺少 .serif-num")

            stat_n = page.locator(".hero-stats > *").count()
            record("统计组三项", stat_n == 3, f"{stat_n} 项")
        else:
            record("hero 全宽横带", False, "缺少 .hero-banner")

        grid = page.locator(".cards-grid-2x2")
        if grid.count() > 0:
            cols = grid.evaluate("el => getComputedStyle(el).gridTemplateColumns.split(' ').length")
            cards = page.locator(".ability-card").count()
            record("能力卡四列(1440px)", cols == 4, f"{cols} 列 / {cards} 张卡")
        else:
            record("能力卡四列(1440px)", False, "缺少 .cards-grid-2x2")

        browser.close()

    fails = [r for r in results if r[1] == "FAIL"]
    print(f"\n===== 冒烟汇总：{len(results) - len(fails)}/{len(results)} 通过 =====")
    if fails:
        for name, _, note in fails:
            print(f"  FAIL {name} {note}")
        sys.exit(1)


if __name__ == "__main__":
    run()
