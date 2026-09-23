# AI 教学智能体平台 v13 —— 生产/演示部署镜像
# 运行时包含：Python 3.12 + JRE 17（PlantUML）+ 教材知识库索引（预构建）
# 密钥不进镜像：运行时通过 --env-file / compose 注入（见 .env.example）

FROM python:3.12-slim

# PlantUML 渲染需要 JRE；libxml 运行库供 lxml 使用
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（利用层缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码与前端页面
COPY app/ app/
COPY static/ static/
COPY scripts/ scripts/

# PlantUML jar（手工放置于 tools/，见 README；不随 Git 分发）
COPY tools/plantuml.jar tools/plantuml.jar

# 预构建的知识库索引（9.9MB，本地已用真实模型建好——容器启动无需调 LLM 重建）
COPY app/knowledge_base/lightrag_index app/knowledge_base/lightrag_index/

ENV PYTHONUNBUFFERED=1 \
    JAVA_TOOL_OPTIONS="-Dfile.encoding=UTF-8" \
    # 首次启动 fastembed 从国内镜像下载 embedding 模型（约 90MB）
    HF_ENDPOINT=https://hf-mirror.com

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
