"""支持 `python -m app` 启动服务（对齐开发任务拆解 W1 交付项）。"""

import uvicorn

from app.config.settings import get_settings

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=settings.debug,
    )
