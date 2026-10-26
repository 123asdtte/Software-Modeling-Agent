r"""演示前全链路预演：真实 LLM 跑一遍老师会看到的每个入口。

覆盖：六种 UML 图型（含 PNG / draw.io 可达性）→ 类图转 Java → 教材问答 → PPT / 教案。
每项打印耗时与关键产物大小，失败项汇总在末尾，并落盘 JSON 便于留档。

用法（服务需已启动；默认 8100，可用 DEMO_BASE 覆盖）：
    python scripts/demo_regression.py

    # 换端口（Windows cmd）
    set DEMO_BASE=http://127.0.0.1:8000 && python scripts/demo_regression.py

退出码：0 = 全部通过；1 = 存在失败项（便于演示前判定）。
"""

import json
import os
import time
import urllib.error
import urllib.request

BASE = os.environ.get("DEMO_BASE", "http://127.0.0.1:8100").rstrip("/")
results = []


def post(path, payload, timeout=300):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + path, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read().decode("utf-8"))
            return r.status, body, time.time() - t0, None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        return e.code, raw[:300], time.time() - t0, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return 0, "", time.time() - t0, str(e)


def head(url, timeout=20):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, len(r.read())
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def record(name, ok, detail, secs=None):
    results.append({"name": name, "ok": ok, "detail": detail, "secs": round(secs, 1) if secs else None})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}" + (f"  ({secs:.1f}s)" if secs else ""))


# ---------------------------------------------------------------- 1. 六种图型
CASES = [
    (
        "usecase",
        "校园报修系统：学生提交报修，管理员审核报修，维修人员处理报修，管理员统计报表。",
    ),
    (
        "activity",
        "学生登录系统后查询课程，若有余量则选课成功并生成订单，否则提示名额已满并返回课程列表。",
    ),
    (
        "statemachine",
        "订单状态流转：创建后待支付，支付成功进入已支付，超时未支付自动取消，"
        "已支付可发货，发货后完成，任意未完成状态可退款。",
    ),
    (
        "class",
        "校园选课系统：学生(学号/姓名)与课程(课程号/名称/学分)是多对多关系，"
        "学生可继承自用户基类，选课接口 Enrollable 由学生实现；教师可发布课程。",
    ),
    (
        "sequence",
        "学生选课交互：学生向选课服务提交选课请求，选课服务查询课程余量，"
        "有余量则调用数据库保存选课记录并返回成功，否则返回名额已满。",
    ),
    (
        "deployment",
        "校园图书管理系统部署：Nginx 作为入口网关，前端静态资源部署在 Web 服务器，"
        "图书服务与借阅服务部署在 K8s 集群各 2 副本，MySQL 主从数据库部署在独立数据库服务器，"
        "服务间通过 HTTP 通信，数据库访问通过 TCP。",
    ),
]

print("=" * 70)
print("阶段一：六种 UML 图型（真实 LLM）")
print("=" * 70)

models = {}
for dtype, req in CASES:
    code, body, secs, err = post("/v1/uml/generate", {"requirement": req, "diagram_type": dtype, "render": True})
    if code != 200:
        record(f"{dtype} 生成", False, f"{err} {body}", secs)
        continue
    models[dtype] = body
    passed = body["review_report"]["passed"]
    issues = len(body["review_report"]["issues"])
    png_status = body.get("render", {}).get("status")
    png_ok, png_size = (
        head(BASE + body["render"]["download_url"]) if body.get("render", {}).get("download_url") else (0, 0)
    )
    dio_ok, dio_size = head(BASE + body["drawio_download_url"]) if body.get("drawio_download_url") else (0, 0)
    ok = passed and png_ok == 200 and dio_ok == 200 and png_size > 5000
    record(
        f"{dtype} 生成",
        ok,
        f"质检{'通过' if passed else '未通过'} {issues}项 | PNG {png_status}({png_size}B) | drawio {dio_size}B",
        secs,
    )

# ------------------------------------------------------- 2. 类图 → Java 骨架
print()
print("=" * 70)
print("阶段二：类图 → Java 骨架代码")
print("=" * 70)

if "class" in models:
    code, body, secs, err = post(
        "/v1/uml/class-code", {"model": models["class"]["model"], "package": "com.campus.enroll"}
    )
    if code == 200:
        files = body["files"]
        src = "\n".join(files.values())
        checks = {
            "文件数": len(files),
            "package": "package com.campus.enroll;" in src,
            "extends": "extends" in src,
            "implements": "implements" in src,
        }
        record(
            "Java 骨架生成",
            len(files) > 0 and checks["package"] and checks["implements"],
            f"{len(files)} 文件 | " + " ".join(f"{k}={'✓' if v else '✗'}" for k, v in checks.items()),
            secs,
        )
    else:
        record("Java 骨架生成", False, f"{err} {body}", secs)

# --------------------------------------------------------------- 3. 教材问答
print()
print("=" * 70)
print("阶段三：教材知识库问答（RAG）")
print("=" * 70)

code, body, secs, err = post("/v1/qa", {"question": "解释什么是类图，以及类之间的关系有哪些"})
if code == 200:
    answer = body.get("reply", "")
    sources = body.get("sources") or []
    record(
        "教材问答",
        len(answer) > 80,
        f"{len(answer)}字 | 来源 {len(sources)} 条 | {answer[:40].replace(chr(10), ' ')}...",
        secs,
    )
else:
    record("教材问答", False, f"{err} {body}", secs)

# ------------------------------------------------------------ 4. PPT / 教案
print()
print("=" * 70)
print("阶段四：教学资源生成")
print("=" * 70)

for path, payload, label in [
    ("/v1/ppt", {"topic": "UML 类图基础", "minutes": 45}, "PPT 生成"),
    ("/v1/lesson", {"topic": "UML 时序图", "minutes": 45}, "教案生成"),
]:
    code, body, secs, err = post(path, payload, timeout=420)
    if code == 200:
        url = body.get("download_url") or body.get("file_url") or ""
        fsize = head(BASE + url)[1] if url else 0
        record(label, fsize > 10000, f"{url} ({fsize}B)", secs)
    else:
        record(label, False, f"{err} {str(body)[:120]}", secs)

# ---------------------------------------------------------------- 汇总
print()
print("=" * 70)
total = len(results)
ok_count = sum(1 for r in results if r["ok"])
print(f"总计 {total} 项，通过 {ok_count} 项，失败 {total - ok_count} 项")
if total - ok_count:
    print("失败明细：")
    for r in results:
        if not r["ok"]:
            print("  -", r["name"], r["detail"])
print("=" * 70)

os.makedirs("outputs", exist_ok=True)
out = os.path.join("outputs", "demo_regression_result.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("结果已写入", out)
raise SystemExit(0 if (total - ok_count) == 0 else 1)
