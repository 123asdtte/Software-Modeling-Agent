/**
 * 教材智能问答交互逻辑（js/qa.js）
 * 严格按照 M5 前端页面设计文档 6.4 节规范实现
 */

document.addEventListener("DOMContentLoaded", () => {
  const qaInput = document.getElementById("qa-input");
  const qaSubmitBtn = document.getElementById("qa-submit-btn");
  const qaInputError = document.getElementById("qa-input-error");
  const qaErrorBar = document.getElementById("qa-error-bar");
  const chatStream = document.getElementById("chat-stream");

  // 前端内存保存会话轮数（最多 10 轮）
  const historyRounds = [];

  // 点击示例问题填入输入框
  const chips = document.querySelectorAll(".chip-item");
  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      const q = chip.getAttribute("data-question");
      if (q) {
        qaInput.value = q;
        qaInput.focus();
        hideInputError();
      }
    });
  });

  qaInput.addEventListener("input", () => {
    if (qaInput.value.trim()) {
      hideInputError();
    }
  });

  qaInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSendQuestion();
    }
  });

  qaSubmitBtn.addEventListener("click", () => {
    handleSendQuestion();
  });

  function showInputError(msg) {
    qaInputError.textContent = msg;
    qaInputError.style.display = "block";
    qaInput.classList.add("error");
  }

  function hideInputError() {
    qaInputError.style.display = "none";
    qaInput.classList.remove("error");
  }

  function showErrorBar(msg) {
    qaErrorBar.textContent = msg;
    qaErrorBar.style.display = "flex";
  }

  function hideErrorBar() {
    qaErrorBar.style.display = "none";
    qaErrorBar.textContent = "";
  }

  async function handleSendQuestion() {
    const question = qaInput.value.trim();
    if (!question) {
      showInputError("请先输入问题内容");
      qaInput.focus();
      return;
    }
    if (question.length > 1000) {
      showInputError("问题内容不能超过 1000 字");
      return;
    }

    hideInputError();
    hideErrorBar();

    // 清空输入框并禁用提交
    qaInput.value = "";
    qaInput.disabled = true;
    qaSubmitBtn.disabled = true;
    qaSubmitBtn.textContent = "回答中…";

    // 1. 追加用户气泡
    appendUserBubble(question);

    // 2. 追加助手跳动加载点
    const loadingCard = appendLoadingCard();

    try {
      const data = await apiPost("/v1/qa", { question }, { timeoutMs: 60000 });
      // 移除加载卡片，替换为正式回答卡片
      loadingCard.remove();
      appendAssistantCard(data);

      // 记录轮数并在超过 10 轮时剔除最老一轮
      historyRounds.push({ question, reply: data.reply, sources: data.sources });
      if (historyRounds.length > 10) {
        historyRounds.shift();
        // 移除最老一轮 DOM（前 2 个元素：1 个用户气泡 + 1 个助手卡片）
        if (chatStream.children.length > 20) {
          chatStream.removeChild(chatStream.firstElementChild);
          chatStream.removeChild(chatStream.firstElementChild);
        }
      }
    } catch (err) {
      loadingCard.remove();
      showErrorBar(err.message || "服务异常，请稍后重试");
      // 保留用户输入以便重试
      qaInput.value = question;
    } finally {
      qaInput.disabled = false;
      qaSubmitBtn.disabled = false;
      qaSubmitBtn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="22" y1="2" x2="11" y2="13"></line>
          <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
        </svg>
        提问
      `;
      qaInput.focus();
    }
  }

  function appendUserBubble(text) {
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble-user fade-in";
    bubble.textContent = text;
    chatStream.appendChild(bubble);
    bubble.scrollIntoView({ behavior: "smooth", block: "end" });
  }

  function appendLoadingCard() {
    const card = document.createElement("div");
    card.className = "chat-card-assistant fade-in";
    card.innerHTML = `
      <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
        <div style="width: 24px; height: 24px; border-radius: 4px; background: var(--color-primary-light); color: var(--color-primary); display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700;">AI</div>
        <div style="font-size: 13px; color: var(--color-text-secondary);">教材智能体正在检索知识库大纲与关联章节…</div>
      </div>
      <div class="loading-dots">
        <span class="loading-dot"></span>
        <span class="loading-dot"></span>
        <span class="loading-dot"></span>
      </div>
    `;
    chatStream.appendChild(card);
    card.scrollIntoView({ behavior: "smooth", block: "end" });
    return card;
  }

  function appendAssistantCard(data) {
    const card = document.createElement("div");
    card.className = "chat-card-assistant fade-in";

    // 格式化四段式回答：按换行分段，【xxx】 开头的段落首行加粗
    const replyRaw = data.reply || "";
    const paragraphs = replyRaw.split("\n").filter((p) => p.trim().length > 0);

    let htmlContent = `
      <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 14px; padding-bottom: 8px; border-bottom: 1px solid var(--color-border-subtle);">
        <div style="width: 24px; height: 24px; border-radius: 4px; background: var(--color-primary-light); color: var(--color-primary); display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700;">AI</div>
        <span style="font-weight: 600; font-size: 13px;">教材答疑智能体</span>
        <span class="badge badge-primary" style="margin-left: auto;">四段式答疑</span>
      </div>
      <div class="chat-reply-body">`;

    paragraphs.forEach((p) => {
      const trimmed = p.trim();
      if (trimmed.startsWith("【") && trimmed.includes("】")) {
        const titleEnd = trimmed.indexOf("】") + 1;
        const title = trimmed.substring(0, titleEnd);
        const rest = trimmed.substring(titleEnd);
        htmlContent += `<p class="chat-reply-paragraph"><strong class="chat-reply-heading">${escapeHtml(title)}</strong> ${escapeHtml(rest)}</p>`;
      } else {
        htmlContent += `<p class="chat-reply-paragraph">${escapeHtml(trimmed)}</p>`;
      }
    });
    htmlContent += `</div>`;

    // 底部教材来源折叠区
    const sources = data.sources || [];
    if (sources.length > 0) {
      htmlContent += `
        <details class="sources-details">
          <summary>${IconLib.svg("book-open", 14)}  教材来源引用（${sources.length} 条关联）</summary>
          <div class="sources-list">
            ${sources
              .map(
                (s) => `
              <div class="source-item">
                <div class="source-filename">${IconLib.svg("file-text", 14)} ${escapeHtml(s.source || "软件工程建模教材")}</div>
                <div class="source-snippet">${escapeHtml(s.snippet || "")}</div>
              </div>
            `
              )
              .join("")}
          </div>
        </details>
      `;
    }

    card.innerHTML = htmlContent;
    chatStream.appendChild(card);
    card.scrollIntoView({ behavior: "smooth", block: "end" });
  }
});
