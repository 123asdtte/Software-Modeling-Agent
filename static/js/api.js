/**
 * 统一 API 封装与全局加载进度条（js/api.js）
 * 严格按照 M5 前端页面设计文档 5.7 节规范实现
 */

/**
 * 全局加载进度条控制模块（GlobalProgressBar）
 * 位于视口最顶层，提供高科技感光效与长耗时任务（如 PPT、教案、UML）动态耗时反馈
 */
const GlobalProgressBar = (function () {
  let container = null;
  let bar = null;
  let pill = null;
  let pillText = null;
  let pillTimer = null;
  let currentProgress = 0;
  let trickler = null;
  let secondCounter = null;
  let activeRequests = 0;
  let elapsedSeconds = 0;

  function ensureElements() {
    if (!container && document.body) {
      container = document.getElementById("global-progress-container");
      if (!container) {
        container = document.createElement("div");
        container.id = "global-progress-container";
        container.className = "global-progress-container";
        container.innerHTML = `
          <div id="global-progress-bar" class="global-progress-bar"></div>
          <div id="global-progress-pill" class="global-progress-pill">
            <span class="progress-spinner"></span>
            <span id="global-progress-text" class="progress-text">AI 正在深度运算中…</span>
            <span id="global-progress-timer" class="progress-timer">0s</span>
          </div>
        `;
        document.body.appendChild(container);
      }
      bar = container.querySelector("#global-progress-bar");
      pill = container.querySelector("#global-progress-pill");
      pillText = container.querySelector("#global-progress-text");
      pillTimer = container.querySelector("#global-progress-timer");
    }
  }

  // 页面加载完成后预置 DOM
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ensureElements);
  } else {
    ensureElements();
  }

  function start(customLabel) {
    ensureElements();
    activeRequests++;

    if (customLabel && pillText) {
      pillText.textContent = customLabel;
    }

    if (activeRequests > 1) {
      return;
    }

    clearInterval(trickler);
    clearInterval(secondCounter);

    if (container) {
      container.classList.remove("is-error", "is-finished");
      container.classList.add("is-active");
    }

    elapsedSeconds = 0;
    if (pillTimer) pillTimer.textContent = "0s";
    if (pillText && !customLabel) {
      pillText.textContent = "AI 正在深度运算中…";
    }

    currentProgress = 14;
    update(currentProgress);

    // 运行耗时秒数递增器
    secondCounter = setInterval(() => {
      elapsedSeconds++;
      if (pillTimer) {
        pillTimer.textContent = `${elapsedSeconds}s`;
      }
    }, 1000);

    // 渐进式逼近模拟：在长任务（如 30~60s 的 PPT/教案生成）中平滑缓慢递增至 93%
    trickler = setInterval(() => {
      if (currentProgress < 30) {
        currentProgress += Math.random() * 6 + 3;
      } else if (currentProgress < 55) {
        currentProgress += Math.random() * 3 + 1.5;
      } else if (currentProgress < 75) {
        currentProgress += Math.random() * 1.5 + 0.8;
      } else if (currentProgress < 92) {
        currentProgress += Math.random() * 0.5 + 0.2;
      }
      if (currentProgress > 93) {
        currentProgress = 93;
      }
      update(currentProgress);
    }, 400);
  }

  function update(percent) {
    if (bar) {
      bar.style.width = `${percent}%`;
    }
  }

  function done() {
    activeRequests = Math.max(0, activeRequests - 1);
    if (activeRequests > 0) return;

    clearInterval(trickler);
    clearInterval(secondCounter);
    ensureElements();

    if (pillText) {
      pillText.textContent = "生成完成";
    }

    currentProgress = 100;
    update(100);

    setTimeout(() => {
      if (container) {
        container.classList.add("is-finished");
        container.classList.remove("is-active");
      }
      setTimeout(() => {
        currentProgress = 0;
        update(0);
        if (container) {
          container.classList.remove("is-error", "is-finished");
        }
      }, 300);
    }, 350);
  }

  function error(errMsg) {
    activeRequests = Math.max(0, activeRequests - 1);
    if (activeRequests > 0) return;

    clearInterval(trickler);
    clearInterval(secondCounter);
    ensureElements();

    if (container) {
      container.classList.add("is-error");
    }
    if (pillText) {
      pillText.textContent = errMsg ? `请求失败: ${errMsg}` : "服务异常";
    }

    currentProgress = 100;
    update(100);

    setTimeout(() => {
      if (container) {
        container.classList.add("is-finished");
        container.classList.remove("is-active");
      }
      setTimeout(() => {
        currentProgress = 0;
        update(0);
        if (container) {
          container.classList.remove("is-error", "is-finished");
        }
      }, 400);
    }, 600);
  }

  return {
    start,
    done,
    error,
  };
})();

// 挂载到全局
window.GlobalProgressBar = GlobalProgressBar;

async function apiPost(path, body, { timeoutMs = 60000, showProgress = true, label } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let taskLabel = label;
  if (!taskLabel) {
    if (path.includes("/ppt")) {
      taskLabel = "PPT 课件大纲生成中…";
    } else if (path.includes("/lesson")) {
      taskLabel = "高职规范教案生成中…";
    } else if (path.includes("/uml")) {
      taskLabel = "UML 用例图建模与质检中…";
    } else if (path.includes("/qa")) {
      taskLabel = "教材知识检索与生成中…";
    } else {
      taskLabel = "任务处理中…";
    }
  }

  if (showProgress) {
    GlobalProgressBar.start(taskLabel);
  }

  try {
    const response = await fetch(path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    clearTimeout(timer);

    if (!response.ok) {
      const status = response.status;
      if (status === 422) {
        throw new Error("请求参数有误，请检查输入");
      }
      if (status === 502) {
        let detail = "模型失败，请稍后重试";
        try {
          const errorData = await response.json();
          if (errorData && errorData.detail) {
            detail = typeof errorData.detail === "string" ? errorData.detail : JSON.stringify(errorData.detail);
          }
        } catch (_) {}
        throw new Error(detail);
      }
      if (status === 504) {
        throw new Error("请求超时，请稍后重试");
      }
      throw new Error("服务异常，请稍后重试");
    }

    const data = await response.json();
    if (showProgress) {
      GlobalProgressBar.done();
    }
    return data;
  } catch (error) {
    clearTimeout(timer);
    let userMsg = error.message;
    if (error.name === "AbortError") {
      userMsg = "请求超时，请稍后重试";
    } else if (error instanceof TypeError && error.message.toLowerCase().includes("fetch")) {
      userMsg = "无法连接服务，请确认后端已启动";
    }
    if (showProgress) {
      GlobalProgressBar.error(userMsg);
    }
    throw new Error(userMsg);
  }
}

async function apiGet(path, { timeoutMs = 10000, showProgress = true, label } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  if (showProgress) {
    GlobalProgressBar.start(label || "加载中…");
  }

  try {
    const response = await fetch(path, {
      method: "GET",
      signal: controller.signal,
    });

    clearTimeout(timer);

    if (!response.ok) {
      throw new Error(`HTTP Error ${response.status}`);
    }

    const data = await response.json();
    if (showProgress) {
      GlobalProgressBar.done();
    }
    return data;
  } catch (error) {
    clearTimeout(timer);
    let userMsg = error.message;
    if (error.name === "AbortError") {
      userMsg = "请求超时，请稍后重试";
    }
    if (showProgress) {
      GlobalProgressBar.error(userMsg);
    }
    throw new Error(userMsg);
  }
}

// 转义函数防止 XSS（满足第 7 节规范）
function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
