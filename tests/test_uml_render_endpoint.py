"""在线源码重绘端点 /v1/uml/render 测试（三图型统一，jar 本地渲染降级安全）。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

VALID_ACTIVITY_PUML = """@startuml
|考生|
start
:登录系统;
|系统|
:自动判分;
stop
@enduml"""

VALID_STATEMACHINE_PUML = """@startuml
[*] --> st_1
state "待支付" as st_1
st_1 --> [*]
@enduml"""


def test_render_activity_ok():
    """合法活动图源码 → RENDERED + download_url（.png）。"""
    resp = client.post(
        "/v1/uml/render",
        json={"plantuml": VALID_ACTIVITY_PUML, "diagram_type": "activity", "format": "png"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rendered"
    assert body["download_url"].startswith("/files/uml/")
    assert body["download_url"].endswith(".png")


def test_render_statemachine_svg_ok():
    """状态机 SVG 渲染。"""
    resp = client.post(
        "/v1/uml/render",
        json={"plantuml": VALID_STATEMACHINE_PUML, "diagram_type": "statemachine", "format": "svg"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("rendered", "source_only")  # svg 渲染依赖 jar，允许降级
    if body["status"] == "rendered":
        assert body["download_url"].endswith(".svg")


def test_render_rejects_include_directive():
    """!include 指令（可读本地文件）→ 422 拒绝。"""
    resp = client.post(
        "/v1/uml/render",
        json={"plantuml": "@startuml\n!include secret.iuml\n@enduml", "diagram_type": "activity"},
    )
    assert resp.status_code == 422


def test_render_too_short_422():
    """过短源码 → 422。"""
    resp = client.post(
        "/v1/uml/render",
        json={"plantuml": "abc", "diagram_type": "activity"},
    )
    assert resp.status_code == 422


def test_render_invalid_syntax_degrades():
    """非法 PlantUML 语法 → 降级 source_only（不 500）。"""
    resp = client.post(
        "/v1/uml/render",
        json={"plantuml": "@startuml\nthis is not valid plantuml !!! ???\n@enduml", "diagram_type": "activity"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "source_only"


def test_render_skin_injected():
    """渲染时注入教学配色，但请求体源码本身不受影响（无副作用可断言：端点不回显）。"""
    resp = client.post(
        "/v1/uml/render",
        json={"plantuml": VALID_ACTIVITY_PUML, "diagram_type": "activity", "format": "png"},
    )
    assert resp.status_code == 200


# ============================================================================
# C 任务新增三图型：在线重绘必须真实渲染（不能静默降级）
# ============================================================================

VALID_CLASS_PUML = """@startuml
abstract class "Person" as class_1 {
  + name: String
  + {abstract} getName(): String
}
interface "Enrollable" as class_2 {
  + enroll(): void
}
class "Student" as class_3
class_1 <|-- class_3
class_2 <|.. class_3
class_3 "1" -- "0..*" class_1 : 关注
@enduml"""

VALID_SEQUENCE_PUML = """@startuml
actor "学生" as l_1
participant "选课服务" as l_2
database "选课库" as l_3
l_1 -> l_2 : 提交选课
alt 容量充足
  l_2 -> l_3 : 写入选课记录
  l_3 --> l_2 : OK
else 容量不足
  l_2 --> l_1 : 返回失败
end
@enduml"""

VALID_DEPLOYMENT_PUML = """@startuml
node "ingress" as n_1 <<ingress>>
node "选课服务" as n_2 <<deployment>>
node "MySQL" as n_3 <<device>> <<database>>
artifact "course.jar" as a_1
n_2 -- a_1
n_1 <--> n_2 : HTTP
n_2 ..> n_3 : TCP
@enduml"""


def test_render_class_ok():
    resp = client.post(
        "/v1/uml/render",
        json={"plantuml": VALID_CLASS_PUML, "diagram_type": "class", "format": "png"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rendered", body.get("reason")
    assert body["download_url"].endswith(".png")


def test_render_sequence_ok():
    resp = client.post(
        "/v1/uml/render",
        json={"plantuml": VALID_SEQUENCE_PUML, "diagram_type": "sequence", "format": "png"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rendered", body.get("reason")
    assert body["download_url"].endswith(".png")


def test_render_deployment_ok():
    """回归防线：设备节点必须用 node + <<device>>，不能出现 device 关键字。"""
    resp = client.post(
        "/v1/uml/render",
        json={"plantuml": VALID_DEPLOYMENT_PUML, "diagram_type": "deployment", "format": "png"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rendered", body.get("reason")
    assert body["download_url"].endswith(".png")


def test_render_unsupported_diagram_type_422():
    """未支持图型（组件图）→ 422。"""
    resp = client.post(
        "/v1/uml/render",
        json={"plantuml": VALID_CLASS_PUML, "diagram_type": "component"},
    )
    assert resp.status_code == 422
