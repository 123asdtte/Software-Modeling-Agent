/**
 * 顶栏导航渲染与健康检查（js/layout.js）
 * 视觉对齐 m5-teaching-platform 参考稿：
 *   品牌区 = 黑色圆角方块图标 + 平台名 + " / " + 当前模块名
 *   导航   = 药丸分段器（纯文字，激活项实心黑块）
 *   右侧   = 细边框健康胶囊
 * 健康检查/导航激活逻辑与原实现保持一致。
 */

(function () {
  // 各页面的模块名（品牌区分隔符右侧），与参考稿 current-module-label 对应
  const MODULE_LABEL = {
    index: "平台总览",
    uml: "UML 建模",
    qa: "教材问答",
    resources: "课件教案",
  };

  function detectActiveKey() {
    const currentPath = window.location.pathname;
    if (currentPath.endsWith("uml.html") || currentPath.endsWith("/uml")) {
      return "uml";
    } else if (currentPath.endsWith("qa.html") || currentPath.endsWith("/qa")) {
      return "qa";
    } else if (currentPath.endsWith("resources.html") || currentPath.endsWith("/resources")) {
      return "resources";
    }
    return "index";
  }

  function renderLayout() {
    const activeKey = detectActiveKey();

    const header = document.createElement("header");
    header.className = "app-header";
    header.id = "app-header";

    header.innerHTML = `
      <div class="header-container">
        <a href="index.html" class="brand-section" id="nav-brand">
          <span class="brand-logo-badge" aria-hidden="true">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M16 16v1a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h11a2 2 0 0 1 2 2v1"></path>
              <path d="M18 8h4a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-4"></path>
              <circle cx="8" cy="12" r="2"></circle>
            </svg>
          </span>
          <span class="brand-title">AI 教学智能体平台</span>
          <span class="brand-sep" aria-hidden="true">/</span>
          <span class="brand-module" id="current-module-label">${MODULE_LABEL[activeKey]}</span>
        </a>
        <nav class="nav-tabs" id="main-nav-tabs" aria-label="主导航">
          <a href="index.html" class="nav-tab-item ${activeKey === 'index' ? 'active' : ''}" id="tab-home" ${activeKey === 'index' ? 'aria-current="page"' : ''}>首页</a>
          <a href="uml.html" class="nav-tab-item ${activeKey === 'uml' ? 'active' : ''}" id="tab-uml" ${activeKey === 'uml' ? 'aria-current="page"' : ''}>UML 建模</a>
          <a href="qa.html" class="nav-tab-item ${activeKey === 'qa' ? 'active' : ''}" id="tab-qa" ${activeKey === 'qa' ? 'aria-current="page"' : ''}>教材问答</a>
          <a href="resources.html" class="nav-tab-item ${activeKey === 'resources' ? 'active' : ''}" id="tab-resources" ${activeKey === 'resources' ? 'aria-current="page"' : ''}>课件教案</a>
        </nav>
        <div class="health-status-container" id="health-indicator" title="每 30 秒轮询后端健康状态">
          <span class="health-dot healthy" id="health-dot" aria-hidden="true"></span>
          <span class="health-text" id="health-text">服务正常</span>
        </div>
      </div>
    `;

    document.body.insertAdjacentElement("afterbegin", header);

    // Render footer
    const footer = document.createElement("footer");
    footer.className = "app-footer";
    footer.id = "app-footer";
    footer.innerHTML = `
      <div>AI 教学智能体平台 v1.0 · 高职软件技术专业课程教学辅助系统</div>
      <div style="margin-top: 4px; font-size: 11px; opacity: 0.8;">生成内容仅供备课与实训教学参考，请教师审核后使用</div>
    `;
    document.body.insertAdjacentElement("beforeend", footer);

    // Health check polling
    initHealthCheck();
  }

  async function checkHealth() {
    const dot = document.getElementById("health-dot");
    const text = document.getElementById("health-text");
    if (!dot || !text) return;

    try {
      const data = await apiGet("/health", { timeoutMs: 5000, showProgress: false });
      if (data && data.status === "ok") {
        dot.className = "health-dot healthy";
        text.textContent = "服务正常";
      } else {
        dot.className = "health-dot unhealthy";
        text.textContent = "服务异常";
      }
    } catch (e) {
      dot.className = "health-dot unhealthy";
      text.textContent = "服务异常";
    }
  }

  function initHealthCheck() {
    checkHealth();
    setInterval(checkHealth, 30000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", renderLayout);
  } else {
    renderLayout();
  }
})();
