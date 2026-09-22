"""API 路由层（M4 起新功能一律用 APIRouter 拆分，main.py 只负责 include_router）。

当前状态：占位边界，尚未拆分旧路由（/health /v1/chat /v1/qa /v1/ppt /v1/lesson
暂留 main.py，不做大规模迁移）。
计划：UML 用例图 API（POST /v1/uml/usecase）落在本包 uml.py。
"""
