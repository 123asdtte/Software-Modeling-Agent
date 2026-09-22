/**
 * UML 建模页交互逻辑（js/uml.js）
 * 严格按照 M5 前端页面设计文档 6.3 节与 5.3 节 API 契约规范实现
 * 集成：架构指标条、画布缩放与全屏灯箱、质检/要素双标签页、实时筛选与文件导出
 */

document.addEventListener("DOMContentLoaded", () => {
  // 1. DOM 元素引用
  const textarea = document.getElementById("requirement-input");
  const clearBtn = document.getElementById("textarea-clear-btn");
  const charCounter = document.getElementById("char-counter");
  const errorMsg = document.getElementById("input-error-msg");
  const formatSelect = document.getElementById("format-select");
  const generateBtn = document.getElementById("generate-uml-btn");
  const errorBar = document.getElementById("uml-error-bar");
  const skeletonBox = document.getElementById("uml-skeleton-box");
  const resultSection = document.getElementById("uml-result-section");

  // KPI 概览条
  const kpiSystemName = document.getElementById("kpi-system-name");
  const kpiActorsCount = document.getElementById("kpi-actors-count");
  const kpiActorsDetail = document.getElementById("kpi-actors-detail");
  const kpiUsecasesCount = document.getElementById("kpi-usecases-count");
  const kpiQualityScore = document.getElementById("kpi-quality-score");
  const kpiQualityLevel = document.getElementById("kpi-quality-level");
  const kpiScoreIcon = document.getElementById("kpi-score-icon");

  // 画布与缩放控制
  const umlImage = document.getElementById("uml-image");
  const canvasViewport = document.getElementById("canvas-viewport");
  const canvasToolbar = document.getElementById("canvas-toolbar");
  const zoomInBtn = document.getElementById("zoom-in-btn");
  const zoomOutBtn = document.getElementById("zoom-out-btn");
  const zoomResetBtn = document.getElementById("zoom-reset-btn");
  const zoomBadge = document.getElementById("zoom-badge");
  const fullscreenBtn = document.getElementById("fullscreen-btn");
  const imageDisplayArea = document.getElementById("image-display-area");
  const sourceOnlyBox = document.getElementById("source-only-box");
  const sourceOnlyReason = document.getElementById("source-only-reason");
  const downloadBtn = document.getElementById("download-btn");

  // 标签页控制
  const tabBtnReview = document.getElementById("tab-btn-review");
  const tabBtnElements = document.getElementById("tab-btn-elements");
  const viewReviewReport = document.getElementById("view-review-report");
  const viewModelElements = document.getElementById("view-model-elements");

  // 质检报告与筛选
  const reviewBadgeContainer = document.getElementById("review-badge-container");
  const issuesTbody = document.getElementById("issues-tbody");
  const filterPills = document.querySelectorAll(".review-level-pills .filter-pill");
  const reviewSearchInput = document.getElementById("review-search-input");
  const countAll = document.getElementById("count-all");
  const countError = document.getElementById("count-error");
  const countWarning = document.getElementById("count-warning");
  const countInfo = document.getElementById("count-info");

  // 要素清单
  const modelActorsContainer = document.getElementById("model-actors-container");
  const modelActorsCountText = document.getElementById("model-actors-count-text");
  const modelUsecasesTbody = document.getElementById("model-usecases-tbody");
  const modelUsecasesCountText = document.getElementById("model-usecases-count-text");

  // PlantUML 源码与导出
  const plantumlCode = document.getElementById("plantuml-code");
  const copySourceBtn = document.getElementById("copy-source-btn");
  const downloadPumlBtn = document.getElementById("download-puml-btn");

  // 二次确认弹窗 DOM
  const confirmModal = document.getElementById("uml-confirm-modal");
  const confirmReqPreview = document.getElementById("confirm-requirement-preview");
  const confirmCharCount = document.getElementById("confirm-char-count");
  const confirmFormatBadge = document.getElementById("confirm-format-badge");
  const confirmModalCloseBtn = document.getElementById("confirm-modal-close-btn");
  const confirmModalCancelBtn = document.getElementById("confirm-modal-cancel-btn");
  const confirmModalSubmitBtn = document.getElementById("confirm-modal-submit-btn");

  // 全屏灯箱 Modal DOM
  const lightboxModal = document.getElementById("uml-lightbox-modal");
  const lightboxImg = document.getElementById("lightbox-img");
  const lightboxCloseBtn = document.getElementById("lightbox-close-btn");
  const lightboxDownloadLink = document.getElementById("lightbox-download-link");
  const lightboxFormatBadge = document.getElementById("lightbox-format-badge");

  // 状态控制
  let isProcessing = false;
  let debounceTimer = null;
  let currentZoom = 1;
  let cachedIssues = [];
  let currentFilter = "all";
  let currentSearchQuery = "";
  let currentModelData = null;

  // 2. 需求输入处理与实时清空
  function updateCharCount() {
    const val = textarea.value;
    const len = val.length;
    charCounter.textContent = `${len} / 3000`;
    if (len > 3000) {
      charCounter.classList.add("limit-exceeded");
    } else {
      charCounter.classList.remove("limit-exceeded");
    }

    if (len > 0) {
      textarea.classList.remove("error");
      errorMsg.style.display = "none";
      if (clearBtn) clearBtn.style.display = "inline-flex";
    } else {
      if (clearBtn) clearBtn.style.display = "none";
    }
  }

  textarea.addEventListener("input", updateCharCount);

  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      textarea.value = "";
      updateCharCount();
      textarea.focus();
      hideError();
    });
  }

  // 支持 Ctrl + Enter 或 Cmd + Enter 快速提交
  textarea.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      requestUmlGeneration();
    }
  });

  // 示例需求 Chips 快捷填入
  const chips = document.querySelectorAll(".chip-item");
  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      const exampleText = chip.getAttribute("data-example");
      if (exampleText) {
        textarea.value = exampleText;
        updateCharCount();
        textarea.focus();
        hideError();
      }
    });
  });

  // 3. 画布缩放与全屏灯箱交互
  function applyZoom(zoom) {
    currentZoom = Math.min(Math.max(zoom, 0.4), 2.5);
    umlImage.style.transform = `scale(${currentZoom})`;
    if (zoomBadge) {
      zoomBadge.textContent = `${Math.round(currentZoom * 100)}%`;
    }
  }

  if (zoomInBtn) {
    zoomInBtn.addEventListener("click", () => applyZoom(currentZoom + 0.15));
  }
  if (zoomOutBtn) {
    zoomOutBtn.addEventListener("click", () => applyZoom(currentZoom - 0.15));
  }
  if (zoomResetBtn) {
    zoomResetBtn.addEventListener("click", () => applyZoom(1.0));
  }

  // 鼠标滚轮缩放画布（配合 Ctrl 或直接在画布上操作）
  if (canvasViewport) {
    canvasViewport.addEventListener("wheel", (e) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        const delta = e.deltaY < 0 ? 0.1 : -0.1;
        applyZoom(currentZoom + delta);
      }
    }, { passive: false });
  }

  // 全屏沉浸灯箱打开/关闭
  function openLightbox() {
    if (!umlImage.src || umlImage.style.display === "none") return;
    lightboxImg.src = umlImage.src;
    lightboxDownloadLink.href = umlImage.src;
    const format = (formatSelect.value || "png").toUpperCase();
    lightboxFormatBadge.textContent = format;
    lightboxModal.style.display = "flex";
    document.body.style.overflow = "hidden";
  }

  function closeLightbox() {
    lightboxModal.style.display = "none";
    document.body.style.overflow = "";
  }

  if (fullscreenBtn) fullscreenBtn.addEventListener("click", openLightbox);
  if (umlImage) umlImage.addEventListener("click", openLightbox);
  if (lightboxCloseBtn) lightboxCloseBtn.addEventListener("click", closeLightbox);
  if (lightboxModal) {
    lightboxModal.addEventListener("click", (e) => {
      if (e.target === lightboxModal || e.target.classList.contains("lightbox-body")) {
        closeLightbox();
      }
    });
  }

  // 4. 双标签页切换逻辑
  if (tabBtnReview && tabBtnElements) {
    tabBtnReview.addEventListener("click", () => {
      tabBtnReview.classList.add("active");
      tabBtnReview.setAttribute("aria-selected", "true");
      tabBtnElements.classList.remove("active");
      tabBtnElements.setAttribute("aria-selected", "false");
      viewReviewReport.style.display = "block";
      viewModelElements.style.display = "none";
    });

    tabBtnElements.addEventListener("click", () => {
      tabBtnElements.classList.add("active");
      tabBtnElements.setAttribute("aria-selected", "true");
      tabBtnReview.classList.remove("active");
      tabBtnReview.setAttribute("aria-selected", "false");
      viewReviewReport.style.display = "none";
      viewModelElements.style.display = "flex";
    });
  }

  // 5. 复制代码与下载源码功能
  copySourceBtn.addEventListener("click", async () => {
    const code = plantumlCode.textContent;
    if (!code) return;

    let success = false;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      try {
        await navigator.clipboard.writeText(code);
        success = true;
      } catch (_) {
        success = false;
      }
    }

    if (!success) {
      try {
        const tempArea = document.createElement("textarea");
        tempArea.value = code;
        tempArea.style.position = "fixed";
        tempArea.style.opacity = "0";
        document.body.appendChild(tempArea);
        tempArea.select();
        document.execCommand("copy");
        document.body.removeChild(tempArea);
        success = true;
      } catch (_) {
        success = false;
      }
    }

    const originalText = copySourceBtn.textContent;
    if (success) {
      copySourceBtn.textContent = "已复制！";
      copySourceBtn.classList.remove("btn-secondary");
      copySourceBtn.classList.add("btn-primary");
    } else {
      copySourceBtn.textContent = "复制失败，请手动选择";
    }

    setTimeout(() => {
      copySourceBtn.textContent = originalText;
      copySourceBtn.classList.remove("btn-primary");
      copySourceBtn.classList.add("btn-secondary");
    }, 2000);
  });

  if (downloadPumlBtn) {
    downloadPumlBtn.addEventListener("click", () => {
      const code = plantumlCode.textContent;
      if (!code) return;
      const blob = new Blob([code], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `model_${Date.now()}.puml`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    });
  }

  // 6. 提交生成逻辑（防抖 + 二次确认机制）
  generateBtn.addEventListener("click", requestUmlGeneration);

  function requestUmlGeneration() {
    if (isProcessing) return;

    if (debounceTimer) {
      clearTimeout(debounceTimer);
    }

    debounceTimer = setTimeout(() => {
      handlePreValidationAndConfirm();
    }, 200);
  }

  function handlePreValidationAndConfirm() {
    const rawVal = textarea.value.trim();

    if (!rawVal) {
      textarea.classList.add("error");
      errorMsg.textContent = "请先输入建模需求";
      errorMsg.style.display = "block";
      textarea.focus();
      return;
    }

    if (rawVal.length > 3000) {
      showError("需求内容不能超过 3000 字");
      textarea.focus();
      return;
    }

    openConfirmModal(rawVal, formatSelect.value);
  }

  // 二次确认弹窗交互
  function openConfirmModal(rawVal, formatVal) {
    const previewText = rawVal.length > 200 ? rawVal.slice(0, 200) + "……" : rawVal;
    confirmReqPreview.textContent = previewText;
    confirmCharCount.textContent = `${rawVal.length} 字`;

    let formatLabel = "PNG 高清位图";
    if (formatVal === "svg") {
      formatLabel = "SVG 矢量图";
    } else if (formatVal === "source_only") {
      formatLabel = "仅源码模式 (PlantUML)";
    }
    confirmFormatBadge.textContent = formatLabel;

    confirmModal.style.display = "flex";
    confirmModalSubmitBtn.focus();
  }

  function closeConfirmModal() {
    confirmModal.style.display = "none";
  }

  confirmModalCloseBtn.addEventListener("click", closeConfirmModal);
  confirmModalCancelBtn.addEventListener("click", closeConfirmModal);
  confirmModal.addEventListener("click", (e) => {
    if (e.target === confirmModal) {
      closeConfirmModal();
    }
  });

  // 全局键盘快捷响应：Esc 关闭弹窗/灯箱，Enter 确认
  document.addEventListener("keydown", (e) => {
    if (confirmModal.style.display === "flex") {
      if (e.key === "Escape") {
        e.preventDefault();
        closeConfirmModal();
      } else if (e.key === "Enter" && document.activeElement !== confirmModalCancelBtn) {
        e.preventDefault();
        closeConfirmModal();
        executeGenerateUml();
      }
    } else if (lightboxModal.style.display === "flex" && e.key === "Escape") {
      e.preventDefault();
      closeLightbox();
    }
  });

  confirmModalSubmitBtn.addEventListener("click", () => {
    closeConfirmModal();
    executeGenerateUml();
  });

  // 7. 正式调用后端建模 API
  async function executeGenerateUml() {
    if (isProcessing) return;
    const rawVal = textarea.value.trim();
    if (!rawVal) return;

    isProcessing = true;

    // 重置并进入加载态（骨架屏脉冲）
    hideError();
    resultSection.style.display = "none";
    skeletonBox.style.display = "block";
    generateBtn.disabled = true;
    generateBtn.textContent = "生成中…（约 30 秒）";

    const formatVal = formatSelect.value;
    const isSourceOnly = formatVal === "source_only";
    const payload = {
      requirement: rawVal,
      render: !isSourceOnly,
      format: isSourceOnly ? "png" : formatVal,
    };

    try {
      const data = await apiPost("/v1/uml/usecase", payload, { timeoutMs: 180000 });
      renderResults(data);
    } catch (err) {
      showError(err.message || "服务异常，请稍后重试");
    } finally {
      skeletonBox.style.display = "none";
      generateBtn.disabled = false;
      generateBtn.textContent = "生成用例图";
      isProcessing = false;
    }
  }

  function showError(msg) {
    errorBar.textContent = msg;
    errorBar.style.display = "flex";
    errorBar.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function hideError() {
    errorBar.style.display = "none";
    errorBar.textContent = "";
  }

  // 8. 结果渲染主逻辑
  function renderResults(data) {
    resultSection.style.display = "block";
    resultSection.scrollIntoView({ behavior: "smooth", block: "start" });

    currentModelData = data.model || {};
    const issues = (data.review_report && data.review_report.issues) || [];
    cachedIssues = issues;

    // 8.1 渲染 KPI 指标条
    renderKpiBanner(data);

    // 8.2 左列：用例图渲染与画布初始化
    renderCanvasDiagram(data);

    // 8.3 右列：质检报告表格渲染与筛选绑定
    renderReviewTable();

    // 8.4 渲染模型要素清单（参与者与用例表格）
    renderModelElements(currentModelData);

    // 8.5 底部 PlantUML 源码展示
    plantumlCode.textContent = data.plantuml || "";
  }

  // 8.1 KPI 指标条计算与渲染
  function renderKpiBanner(data) {
    const model = data.model || {};
    const actors = model.actors || [];
    const usecases = model.usecases || [];
    const report = data.review_report || {};
    const issues = report.issues || [];

    // 系统名称
    if (kpiSystemName) {
      kpiSystemName.textContent = model.system || "教学业务系统";
    }

    // 参与者
    if (kpiActorsCount) {
      kpiActorsCount.textContent = `${actors.length} 位`;
    }
    if (kpiActorsDetail) {
      const primaryCount = actors.filter((a) => a.role === "primary").length;
      const secondaryCount = actors.length - primaryCount;
      kpiActorsDetail.textContent = `${primaryCount} 主角色 · ${secondaryCount} 辅角色`;
    }

    // 核心用例
    if (kpiUsecasesCount) {
      kpiUsecasesCount.textContent = `${usecases.length} 个`;
    }

    // 规范达标率
    const errorCount = issues.filter((i) => i.level === "error").length;
    const warnCount = issues.filter((i) => i.level === "warning").length;
    let score = 100 - errorCount * 25 - warnCount * 10;
    score = Math.max(score, 50);

    if (kpiQualityScore) {
      kpiQualityScore.textContent = `${score}%`;
    }
    if (kpiQualityLevel && kpiScoreIcon) {
      if (score >= 90) {
        kpiQualityLevel.textContent = "优秀·全部达标";
        kpiQualityLevel.style.color = "var(--color-success)";
        kpiScoreIcon.className = "kpi-icon-wrap kpi-icon-emerald";
        kpiScoreIcon.textContent = "🛡️";
      } else if (score >= 70) {
        kpiQualityLevel.textContent = "良好·轻微瑕疵";
        kpiQualityLevel.style.color = "var(--color-warning)";
        kpiScoreIcon.className = "kpi-icon-wrap kpi-icon-blue";
        kpiScoreIcon.textContent = "⚠️";
      } else {
        kpiQualityLevel.textContent = "需优化·存在错误";
        kpiQualityLevel.style.color = "var(--color-error)";
        kpiScoreIcon.className = "kpi-icon-wrap kpi-icon-purple";
        kpiScoreIcon.textContent = "❌";
      }
    }
  }

  // 8.2 画布图片与缩放工具条
  function renderCanvasDiagram(data) {
    const renderInfo = data.render || {};
    applyZoom(1.0); // 重置为 100%

    if (renderInfo.status === "rendered" && renderInfo.download_url) {
      umlImage.src = renderInfo.download_url;
      umlImage.alt = `${data.model?.system || "UML"} 用例图`;
      umlImage.style.display = "block";
      imageDisplayArea.style.display = "flex";
      sourceOnlyBox.style.display = "none";
      if (canvasToolbar) canvasToolbar.style.display = "flex";

      umlImage.onerror = () => {
        umlImage.style.display = "none";
        downloadBtn.style.display = "none";
        if (canvasToolbar) canvasToolbar.style.display = "none";
        sourceOnlyBox.style.display = "block";
        sourceOnlyReason.textContent = "图形加载遇到异常，请直接查看或复制下方 PlantUML 源码。";
      };

      const fmt = (renderInfo.format || "png").toUpperCase();
      downloadBtn.href = renderInfo.download_url;
      downloadBtn.download = `usecase_${Date.now()}.${(renderInfo.format || "png").toLowerCase()}`;
      downloadBtn.textContent = `下载 ${fmt}`;
      downloadBtn.style.display = "inline-flex";
    } else {
      umlImage.style.display = "none";
      downloadBtn.style.display = "none";
      if (canvasToolbar) canvasToolbar.style.display = "none";
      sourceOnlyBox.style.display = "block";
      sourceOnlyReason.textContent = renderInfo.reason || "当前为仅生成源码模式，未调用图形渲染引擎。";
    }
  }

  // 8.3 质检报告表格与筛选逻辑
  function renderReviewTable() {
    // 统计各级别数量
    const totalCount = cachedIssues.length;
    const errorCount = cachedIssues.filter((i) => i.level === "error").length;
    const warnCount = cachedIssues.filter((i) => i.level === "warning").length;
    const infoCount = cachedIssues.filter((i) => i.level === "info").length;

    if (countAll) countAll.textContent = totalCount;
    if (countError) countError.textContent = errorCount;
    if (countWarning) countWarning.textContent = warnCount;
    if (countInfo) countInfo.textContent = infoCount;

    // 状态胶囊更新
    if (reviewBadgeContainer) {
      if (errorCount > 0) {
        reviewBadgeContainer.innerHTML = `<span class="badge badge-error">❌ ${errorCount} 项严重违规</span>`;
      } else if (warnCount > 0) {
        reviewBadgeContainer.innerHTML = `<span class="badge badge-warning">⚠️ ${warnCount} 项教学预警</span>`;
      } else {
        reviewBadgeContainer.innerHTML = `<span class="badge badge-success">✅ 规范质检通过</span>`;
      }
    }

    applyFilterAndSearch();
  }

  function applyFilterAndSearch() {
    const query = currentSearchQuery.toLowerCase().trim();

    const filtered = cachedIssues.filter((item) => {
      // 级别过滤
      if (currentFilter !== "all" && item.level !== currentFilter) {
        return false;
      }
      // 关键字搜索匹配
      if (query) {
        const textToMatch = [
          item.rule_id || "",
          item.rule_group || "",
          item.target || "",
          item.message || "",
          item.suggestion || "",
        ].join(" ").toLowerCase();
        if (!textToMatch.includes(query)) {
          return false;
        }
      }
      return true;
    });

    // 排序：error -> warning -> info
    const levelWeight = { error: 0, warning: 1, info: 2 };
    filtered.sort((a, b) => {
      const wA = levelWeight[a.level] !== undefined ? levelWeight[a.level] : 3;
      const wB = levelWeight[b.level] !== undefined ? levelWeight[b.level] : 3;
      return wA - wB;
    });

    issuesTbody.innerHTML = "";
    if (filtered.length === 0) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="4" style="text-align: center; color: var(--color-text-secondary); padding: 32px 0;">
        <div style="font-size: 24px; margin-bottom: 6px;">🔍</div>
        <div>未找到符合筛选条件的质检规则或项</div>
      </td>`;
      issuesTbody.appendChild(tr);
      return;
    }

    filtered.forEach((item) => {
      const tr = document.createElement("tr");
      const level = item.level || "info";
      tr.className = `issue-row issue-row-${level}`;
      tr.setAttribute("title", `规则 [${item.rule_id || ""}]：${item.message || ""}`);

      let levelClass = "badge-info";
      let levelText = "建议";
      if (item.level === "error") {
        levelClass = "badge-error";
        levelText = "错误";
      } else if (item.level === "warning") {
        levelClass = "badge-warning";
        levelText = "警告";
      }

      tr.innerHTML = `
        <td><span class="badge ${levelClass}">${levelText}</span></td>
        <td>
          <div style="font-weight: 600; color: var(--color-text);">${escapeHtml(item.rule_id || "-")}</div>
          <div style="font-size: 11px; color: var(--color-text-secondary); margin-top: 2px;">${escapeHtml(item.rule_group || "")}</div>
        </td>
        <td><code style="font-family: var(--font-mono); font-size: 12px; background: var(--color-bg); padding: 2px 6px; border-radius: 4px; border: 1px solid var(--color-border);">${escapeHtml(item.target || "-")}</code></td>
        <td>
          <div style="line-height: 1.5;">${escapeHtml(item.message || "-")}</div>
          ${item.suggestion ? `<div style="font-size: 12px; color: var(--color-primary); margin-top: 4px; background: rgba(59, 130, 246, 0.08); padding: 4px 8px; border-radius: 4px; display: inline-block;">💡 教学提示：${escapeHtml(item.suggestion)}</div>` : ""}
        </td>
      `;
      issuesTbody.appendChild(tr);
    });
  }

  // 绑定质检级别筛选胶囊点击
  filterPills.forEach((pill) => {
    pill.addEventListener("click", () => {
      filterPills.forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      currentFilter = pill.getAttribute("data-filter") || "all";
      applyFilterAndSearch();
    });
  });

  // 绑定搜索输入框
  if (reviewSearchInput) {
    reviewSearchInput.addEventListener("input", (e) => {
      currentSearchQuery = e.target.value;
      applyFilterAndSearch();
    });
  }

  // 8.4 渲染模型要素清单（参与者 + 业务用例清单）
  function renderModelElements(model) {
    const actors = model.actors || [];
    const usecases = model.usecases || [];

    if (modelActorsCountText) {
      modelActorsCountText.textContent = `共 ${actors.length} 位角色`;
    }
    if (modelUseCasesCountText) {
      modelUseCasesCountText.textContent = `共 ${usecases.length} 个用例`;
    }

    // 渲染参与者
    if (modelActorsContainer) {
      modelActorsContainer.innerHTML = "";
      if (actors.length === 0) {
        modelActorsContainer.innerHTML = `<span style="font-size: 13px; color: var(--color-text-secondary);">未提取到明确参与者</span>`;
      } else {
        actors.forEach((act) => {
          const chip = document.createElement("div");
          chip.className = "actor-chip";
          const isPrimary = act.role === "primary";
          const roleBadgeClass = isPrimary ? "actor-role-primary" : "actor-role-secondary";
          const roleBadgeText = isPrimary ? "主角色" : "次角色";

          chip.innerHTML = `
            <span class="actor-icon">${isPrimary ? "👤" : "⚙️"}</span>
            <span class="actor-name">${escapeHtml(act.name)}</span>
            <span class="actor-role-badge ${roleBadgeClass}">${roleBadgeText}</span>
          `;
          modelActorsContainer.appendChild(chip);
        });
      }
    }

    // 渲染用例列表表格
    if (modelUsecasesTbody) {
      modelUsecasesTbody.innerHTML = "";
      if (usecases.length === 0) {
        modelUsecasesTbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--color-text-secondary); padding: 24px 0;">未提取到具体业务用例</td></tr>`;
      } else {
        usecases.forEach((uc) => {
          const tr = document.createElement("tr");
          const actorTags = (uc.actors || [])
            .map((a) => `<span class="badge badge-info" style="font-size: 11px;">${escapeHtml(a)}</span>`)
            .join(" ");

          tr.innerHTML = `
            <td><code style="font-family: var(--font-mono); font-weight: 600; color: var(--color-primary); font-size: 12px;">${escapeHtml(uc.id || "-")}</code></td>
            <td style="font-weight: 600; color: var(--color-text);">${escapeHtml(uc.name || "-")}</td>
            <td><div style="display: flex; gap: 4px; flex-wrap: wrap;">${actorTags || "-"}</div></td>
            <td style="color: var(--color-text-secondary); font-size: 13px;">${escapeHtml(uc.goal || "完成对应业务流程")}</td>
          `;
          modelUsecasesTbody.appendChild(tr);
        });
      }
    }
  }

  // 辅助别名定义，防止拼写差异
  const modelUseCasesCountText = document.getElementById("model-usecases-count-text");
});
