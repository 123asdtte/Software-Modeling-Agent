/**
 * 顶栏导航渲染与健康检查（js/layout.js）
 * 严格按照 M5 前端页面设计文档 6.1 节规范实现
 */

(function () {
  function renderLayout() {
    const currentPath = window.location.pathname;
    let activeKey = "index";
    if (currentPath.endsWith("uml.html") || currentPath.endsWith("/uml")) {
      activeKey = "uml";
    } else if (currentPath.endsWith("qa.html") || currentPath.endsWith("/qa")) {
      activeKey = "qa";
    } else if (currentPath.endsWith("resources.html") || currentPath.endsWith("/resources")) {
      activeKey = "resources";
    }

    const header = document.createElement("header");
    header.className = "app-header";
    header.id = "app-header";

    header.innerHTML = `
      <div class="header-container">
        <a href="index.html" class="brand-section" id="nav-brand">
          <div class="brand-logo-badge">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M16 16v1a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h11a2 2 0 0 1 2 2v1"></path>
              <path d="M18 8h4a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-4"></path>
              <circle cx="8" cy="12" r="2"></circle>
            </svg>
          </div>
          <div class="brand-title-wrap">
            <span class="brand-title">AI 教学智能体平台</span>
            <span class="brand-subtitle">高职软件建模教学 Copilot</span>
          </div>
        </a>
        <nav class="nav-tabs" id="main-nav-tabs">
          <a href="index.html" class="nav-tab-item ${activeKey === 'index' ? 'active' : ''}" id="tab-home">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
              <polyline points="9 22 9 12 15 12 15 22"></polyline>
            </svg>
            首页
          </a>
          <a href="uml.html" class="nav-tab-item ${activeKey === 'uml' ? 'active' : ''}" id="tab-uml">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="3" width="7" height="7"></rect>
              <rect x="14" y="3" width="7" height="7"></rect>
              <rect x="14" y="14" width="7" height="7"></rect>
              <rect x="3" y="14" width="7" height="7"></rect>
            </svg>
            UML 建模
          </a>
          <a href="qa.html" class="nav-tab-item ${activeKey === 'qa' ? 'active' : ''}" id="tab-qa">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
            </svg>
            教材问答
          </a>
          <a href="resources.html" class="nav-tab-item ${activeKey === 'resources' ? 'active' : ''}" id="tab-resources">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
            </svg>
            课件与教案
          </a>
        </nav>
        <div class="health-status-container" id="health-indicator" title="每 30 秒轮询后端健康状态">
          <div class="health-dot-wrap">
            <span class="health-dot healthy" id="health-dot"></span>
          </div>
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
