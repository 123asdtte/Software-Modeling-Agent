"""UML Copilot 面板取证：样式截图 + chat-adjust 功能实测。"""

import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
SHOTS = Path("outputs") / "_copilot_debug"
SHOTS.mkdir(parents=True, exist_ok=True)

logs = []


def run() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("console", lambda m: logs.append(f"CONSOLE[{m.type}]: {m.text[:150]}"))
        page.on("pageerror", lambda e: logs.append(f"PAGEERROR: {str(e)[:200]}"))
        page.on("requestfailed", lambda r: logs.append(f"REQFAIL: {r.url} {r.failure}"))
        page.on(
            "response",
            lambda r: logs.append(f"RESP: {r.status} {r.url}") if "/v1/" in r.url else None,
        )

        # 1. 初始态：看 Copilot 面板样式
        page.goto(f"{BASE}/static/uml.html")
        page.wait_for_timeout(500)
        page.screenshot(path=str(SHOTS / "t1_initial.png"), full_page=True)

        # Copilot 面板初始可见性与计算样式
        panel_info = page.evaluate(
            """() => {
                const find = (sel) => document.querySelector(sel);
                const candidates = {};
                for (const sel of ['#uml-copilot-panel', '.copilot-panel', '#copilot-panel',
                                   '[class*="copilot"]', '[id*="copilot"]']) {
                    const el = find(sel);
                    if (el) {
                        const cs = getComputedStyle(el);
                        candidates[sel] = {
                            display: cs.display, position: cs.position,
                            width: cs.width, height: cs.height,
                            bg: cs.backgroundColor, z: cs.zIndex,
                            rect: el.getBoundingClientRect().toJSON(),
                        };
                    }
                }
                return candidates;
            }"""
        )
        print("=== Copilot 面板元素探测 ===")
        for k, v in panel_info.items():
            print(k, "=>", v)
        page.screenshot(path=str(SHOTS / "t2_copilot_initial.png"), full_page=True)

        # 2. 生成一个模型（真实 LLM）
        page.fill("#requirement-input", "学生可以发布商品，管理员审核商品，买家可以浏览商品")
        page.click("#generate-uml-btn")
        page.wait_for_selector("#uml-confirm-modal", state="visible", timeout=10000)
        page.click("#confirm-modal-submit-btn")
        deadline = time.time() + 180
        while time.time() < deadline:
            if not page.locator("#global-progress-container.is-active").count():
                break
            page.wait_for_timeout(2000)
        result_visible = page.locator("#uml-result-section").is_visible()
        print("生成完成:", result_visible)
        page.screenshot(path=str(SHOTS / "t3_generated.png"), full_page=True)

        # 3. 打开 Copilot 面板（AI 对话调整按钮）
        btn_count = page.locator("button[id*='copilot'], button[class*='copilot'], #btn-open-copilot").count()
        print("Copilot 打开按钮数量:", btn_count)
        if btn_count:
            page.locator("button[id*='copilot'], button[class*='copilot'], #btn-open-copilot").first.click()
            page.wait_for_timeout(500)
            page.screenshot(path=str(SHOTS / "t4_copilot_open.png"), full_page=True)

            # 面板打开后的样式取证
            panel_info2 = page.evaluate(
                """() => {
                    const out = {};
                    for (const sel of ['#uml-copilot-panel', '.copilot-panel', '#copilot-panel', '[id*="copilot"]']) {
                        const el = document.querySelector(sel);
                        if (el && el.offsetParent !== null || (el && getComputedStyle(el).position === 'fixed')) {
                            const cs = getComputedStyle(el);
                            out[sel] = {display: cs.display, pos: cs.position, w: cs.width, h: cs.height, z: cs.zIndex};
                        }
                    }
                    return out;
                }"""
            )
            print("打开后面板样式:", panel_info2)

        # 4. 输入重构指令并执行（真实 chat-adjust）
        instr_box = page.locator(
            "#copilot-input-text, [id*='copilot'] textarea, [id*='copilot'] input[type='text']"
        ).first
        if instr_box.count():
            instr_box.fill("把管理员改成审批专员")
            send = page.locator("#copilot-send-btn, [id*='copilot'] button[class*='send'], [id*='copilot'] button").last
            with page.expect_response(lambda r: "/v1/uml/chat-adjust" in r.url, timeout=120000) as ri:
                send.click()
            resp = ri.value
            print("chat-adjust 状态:", resp.status)
            try:
                body = resp.json()
                print("响应键:", sorted(body.keys()))
                print("success:", body.get("success"), "| reply:", (body.get("reply") or "")[:60])
                print("render:", body.get("render"))
            except Exception as e:
                print("响应非 JSON:", e, resp.text()[:200])
            page.wait_for_timeout(3000)
            page.screenshot(path=str(SHOTS / "t5_adjust_result.png"), full_page=True)
        else:
            print("未找到指令输入框")

        browser.close()


def main() -> None:
    try:
        run()
    except Exception as exc:
        print(f"执行中断: {str(exc)[:300]}")
    finally:
        print("\n=== 页面/网络日志 ===")
        for line in logs[-30:]:
            print(line)


if __name__ == "__main__":
    main()
