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
  const downloadDrawioBtn = document.getElementById("download-drawio-btn");
  const exportFormatSelect = document.getElementById("export-format-select");
  const btnOpenCopilot = document.getElementById("btn-open-copilot");

  // 标签页控制 (AI 对话调优、质检报告、要素清单)
  const tabBtnCopilot = document.getElementById("tab-btn-copilot");
  const tabBtnReview = document.getElementById("tab-btn-review");
  const tabBtnElements = document.getElementById("tab-btn-elements");
  const viewAiCopilot = document.getElementById("view-ai-copilot");
  const viewReviewReport = document.getElementById("view-review-report");
  const viewModelElements = document.getElementById("view-model-elements");

  // AI Copilot 在线调优要素
  const copilotChatHistory = document.getElementById("copilot-chat-history");
  const copilotInputForm = document.getElementById("copilot-input-form");
  const copilotInputText = document.getElementById("copilot-input-text");
  const copilotSendBtn = document.getElementById("copilot-send-btn");
  const copilotUndoBtn = document.getElementById("copilot-undo-btn");
  const copilotClearBtn = document.getElementById("copilot-clear-btn");
  const copilotQuickChips = document.getElementById("copilot-quick-chips");
  let previousUmlState = null;

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
  const plantumlEditor = document.getElementById("plantuml-editor");
  const toggleEditorBtn = document.getElementById("toggle-editor-btn");
  const reRenderPumlBtn = document.getElementById("re-render-puml-btn");
  const resetPumlBtn = document.getElementById("reset-puml-btn");
  const copySourceBtn = document.getElementById("copy-source-btn");
  const downloadPumlBtn = document.getElementById("download-puml-btn");

  // 全案协同与快速直连
  const skipConfirmCheckbox = document.getElementById("skip-confirm-checkbox");
  const btnExportToPackage = document.getElementById("btn-export-to-teaching-package");
  const kpiRelationsCard = document.getElementById("kpi-relations-card");
  const kpiRelationsCount = document.getElementById("kpi-relations-count");
  const kpiRelationsDetail = document.getElementById("kpi-relations-detail");
  let originalPumlSource = "";

  if (skipConfirmCheckbox) {
    try {
      const savedPref = localStorage.getItem("uml_skip_confirm");
      if (savedPref === "true") {
        skipConfirmCheckbox.checked = true;
      }
    } catch (_) {}
    skipConfirmCheckbox.addEventListener("change", () => {
      try {
        localStorage.setItem("uml_skip_confirm", skipConfirmCheckbox.checked ? "true" : "false");
      } catch (_) {}
    });
  }

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

  // 4. 三标签页切换逻辑 (AI 对话调优 / 规范质检报告 / 模型要素清单)
  function switchReviewTab(tabName) {
    // 隐藏所有标签视图
    if (viewAiCopilot) viewAiCopilot.style.display = "none";
    if (viewReviewReport) viewReviewReport.style.display = "none";
    if (viewModelElements) viewModelElements.style.display = "none";

    // 取消所有标签高亮
    if (tabBtnCopilot) {
      tabBtnCopilot.classList.remove("active");
      tabBtnCopilot.setAttribute("aria-selected", "false");
    }
    if (tabBtnReview) {
      tabBtnReview.classList.remove("active");
      tabBtnReview.setAttribute("aria-selected", "false");
    }
    if (tabBtnElements) {
      tabBtnElements.classList.remove("active");
      tabBtnElements.setAttribute("aria-selected", "false");
    }

    if (tabName === "copilot" && viewAiCopilot && tabBtnCopilot) {
      tabBtnCopilot.classList.add("active");
      tabBtnCopilot.setAttribute("aria-selected", "true");
      viewAiCopilot.style.display = "flex";
      if (copilotInputText) setTimeout(() => copilotInputText.focus(), 80);
    } else if (tabName === "elements" && viewModelElements && tabBtnElements) {
      tabBtnElements.classList.add("active");
      tabBtnElements.setAttribute("aria-selected", "true");
      viewModelElements.style.display = "flex";
    } else if (viewReviewReport && tabBtnReview) {
      tabBtnReview.classList.add("active");
      tabBtnReview.setAttribute("aria-selected", "true");
      viewReviewReport.style.display = "block";
    }
  }

  if (tabBtnCopilot) {
    tabBtnCopilot.addEventListener("click", () => switchReviewTab("copilot"));
  }
  if (tabBtnReview) {
    tabBtnReview.addEventListener("click", () => switchReviewTab("review"));
  }
  if (tabBtnElements) {
    tabBtnElements.addEventListener("click", () => switchReviewTab("elements"));
  }

  if (btnOpenCopilot) {
    btnOpenCopilot.addEventListener("click", () => {
      switchReviewTab("copilot");
      const reviewCard = document.getElementById("uml-review-card");
      if (reviewCard) reviewCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  }

  // 5. 复制代码与下载源码功能
  copySourceBtn.addEventListener("click", async () => {
    const code = (plantumlEditor && plantumlEditor.style.display === "block")
      ? plantumlEditor.value
      : (plantumlCode ? plantumlCode.textContent : "");
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
      const code = (plantumlEditor && plantumlEditor.style.display === "block")
        ? plantumlEditor.value
        : (plantumlCode ? plantumlCode.textContent : "");
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

    // 若用户勾选了跳过确认弹窗，直接发起生成
    if (skipConfirmCheckbox && skipConfirmCheckbox.checked) {
      executeGenerateUml();
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
    window.__lastDrawioUrl = data.drawio_download_url || null;
    window.__lastExportPref = (exportFormatSelect && exportFormatSelect.value) || "both";
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

    // 8.5 底部 PlantUML 源码展示与缓存
    originalPumlSource = data.plantuml || "";
    plantumlCode.textContent = originalPumlSource;
    if (plantumlEditor) {
      plantumlEditor.value = originalPumlSource;
    }

    // 8.6 激活画布右上角「AI 对话调整」快捷按钮
    if (btnOpenCopilot) {
      btnOpenCopilot.style.display = "inline-flex";
    }
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

    // 高级规约关系统计
    const puml = data.plantuml || "";
    const includes = (puml.match(/<<include>>/gi) || []).length;
    const extendsCnt = (puml.match(/<<extend>>/gi) || []).length;
    if (kpiRelationsCount) {
      kpiRelationsCount.textContent = `${includes + extendsCnt} 条关系`;
    }
    if (kpiRelationsDetail) {
      kpiRelationsDetail.textContent = `${includes} include · ${extendsCnt} extend`;
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
        if (downloadDrawioBtn) downloadDrawioBtn.style.display = "none";
        if (downloadPumlBtn) downloadPumlBtn.style.display = "none";
        if (canvasToolbar) canvasToolbar.style.display = "none";
        sourceOnlyBox.style.display = "block";
        sourceOnlyReason.textContent = "图形加载遇到异常，请直接查看或复制下方 PlantUML 源码。";
      };

      const fmt = (renderInfo.format || "png").toUpperCase();
      downloadBtn.href = renderInfo.download_url;
      downloadBtn.download = `usecase_${Date.now()}.${(renderInfo.format || "png").toLowerCase()}`;
      downloadBtn.textContent = `下载 ${fmt}`;
      downloadBtn.style.display = "inline-flex";

      // 可编辑源码导出（按「可编辑源码导出」偏好显示 draw.io / PlantUML 下载）
      const exportPref = (exportFormatSelect && exportFormatSelect.value) || "both";
      if (downloadDrawioBtn) {
        const drawioUrl = window.__lastDrawioUrl || null;
        if (drawioUrl && (exportPref === "both" || exportPref === "drawio")) {
          downloadDrawioBtn.href = drawioUrl;
          downloadDrawioBtn.download = `usecase_${Date.now()}.drawio`;
          downloadDrawioBtn.style.display = "inline-flex";
        } else {
          downloadDrawioBtn.style.display = "none";
        }
      }
      if (downloadPumlBtn) {
        if (exportPref === "both" || exportPref === "plantuml") {
          const blob = new Blob([originalPumlSource || ""], { type: "text/plain;charset=utf-8" });
          downloadPumlBtn.href = URL.createObjectURL(blob);
          downloadPumlBtn.download = `usecase_${Date.now()}.puml`;
          downloadPumlBtn.style.display = "inline-flex";
        } else {
          downloadPumlBtn.style.display = "none";
        }
      }

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

  // 8.5 点击 KPI 卡片快速联动切换选项卡
  const kpiScoreCard = document.getElementById("kpi-score-card");
  if (kpiScoreCard && tabBtnReview) {
    kpiScoreCard.addEventListener("click", () => {
      tabBtnReview.click();
      const reviewCard = document.getElementById("uml-review-card");
      if (reviewCard) reviewCard.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  const kpiActorsCard = document.getElementById("kpi-actors-card");
  const kpiUsecasesCard = document.getElementById("kpi-usecases-card");
  if (kpiActorsCard && tabBtnElements) {
    kpiActorsCard.addEventListener("click", () => {
      tabBtnElements.click();
      const reviewCard = document.getElementById("uml-review-card");
      if (reviewCard) reviewCard.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }
  if (kpiUsecasesCard && tabBtnElements) {
    kpiUsecasesCard.addEventListener("click", () => {
      tabBtnElements.click();
      const reviewCard = document.getElementById("uml-review-card");
      if (reviewCard) reviewCard.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }
  if (kpiRelationsCard && tabBtnElements) {
    kpiRelationsCard.addEventListener("click", () => {
      tabBtnElements.click();
      const reviewCard = document.getElementById("uml-review-card");
      if (reviewCard) reviewCard.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  // 8.6 跨页联动：一键联产教学全案（课件·教案·工单）
  if (btnExportToPackage) {
    btnExportToPackage.addEventListener("click", () => {
      const sys = currentModelData?.system || "软件工程业务系统";
      const topic = `${sys}设计与建模`;
      try {
        localStorage.setItem("pending_package_topic", topic);
        window.location.href = "/resources.html?tab=package";
      } catch (e) {
        window.location.href = "/resources.html?tab=package";
      }
    });
  }

  // 8.7 在线编辑与实时重绘 PlantUML
  if (toggleEditorBtn && plantumlEditor && plantumlCode) {
    toggleEditorBtn.addEventListener("click", () => {
      const isEditing = plantumlEditor.style.display === "block";
      if (isEditing) {
        plantumlEditor.style.display = "none";
        plantumlCode.style.display = "block";
        if (reRenderPumlBtn) reRenderPumlBtn.style.display = "none";
        if (resetPumlBtn) resetPumlBtn.style.display = "none";
        toggleEditorBtn.textContent = "✏️ 开启在线编辑";
      } else {
        plantumlEditor.value = plantumlCode.textContent || "";
        plantumlEditor.style.display = "block";
        plantumlCode.style.display = "none";
        if (reRenderPumlBtn) reRenderPumlBtn.style.display = "inline-flex";
        if (resetPumlBtn) resetPumlBtn.style.display = "inline-flex";
        toggleEditorBtn.textContent = "👁️ 退出编辑视图";
        plantumlEditor.focus();
      }
    });
  }

  if (resetPumlBtn && plantumlEditor && plantumlCode) {
    resetPumlBtn.addEventListener("click", () => {
      if (originalPumlSource) {
        plantumlEditor.value = originalPumlSource;
        plantumlCode.textContent = originalPumlSource;
      }
    });
  }

  if (reRenderPumlBtn && plantumlEditor) {
    reRenderPumlBtn.addEventListener("click", async () => {
      const editedCode = plantumlEditor.value.trim();
      if (!editedCode) {
        showError("PlantUML 源码不能为空");
        return;
      }
      plantumlCode.textContent = editedCode;

      reRenderPumlBtn.disabled = true;
      reRenderPumlBtn.textContent = "重绘中…";
      hideError();

      const formatVal = formatSelect.value;
      const isSourceOnly = formatVal === "source_only";
      const payload = {
        requirement: textarea.value.trim() || "自定模型重绘",
        plantuml_override: editedCode,
        render: !isSourceOnly,
        format: isSourceOnly ? "png" : formatVal,
      };

      try {
        const data = await apiPost("/v1/uml/usecase", payload, { timeoutMs: 120000 });
        renderResults(data);
      } catch (err) {
        showError("重绘失败：" + (err.message || "服务异常"));
      } finally {
        reRenderPumlBtn.disabled = false;
        reRenderPumlBtn.textContent = "🔄 立即重绘当前代码";
      }
    });
  }

  // 8.8 架构增量重构控制台日志流 (Model Refactoring Audit Stream)
  function appendRefactorLog(type, text, diffSummary) {
    if (!copilotChatHistory) return;
    const entryDiv = document.createElement("div");
    entryDiv.className = "refactor-entry";

    if (type === "directive") {
      entryDiv.innerHTML = `
        <div class="refactor-directive-bar">
          <span class="refactor-directive-prefix">> 重构指令</span>
          <span>${escapeHtml(text)}</span>
        </div>
      `;
    } else if (type === "success") {
      let diffHtml = "";
      if (diffSummary) {
        diffHtml = `<div class="refactor-diff-tag">变更：${escapeHtml(diffSummary)}</div>`;
      }
      entryDiv.innerHTML = `
        <div class="refactor-result-card">
          <div style="font-weight: 600; color: #0f172a; margin-bottom: 4px; display: flex; align-items: center; gap: 6px;">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#16a34a" stroke-width="2.5">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            重构执行完成
          </div>
          <div>${escapeHtml(text)}</div>
          ${diffHtml}
        </div>
      `;
    } else if (type === "undo") {
      entryDiv.innerHTML = `
        <div class="refactor-result-card" style="border-color: #bae6fd; background: #f0f9ff;">
          <div style="font-weight: 600; color: #0284c7; margin-bottom: 3px; display: flex; align-items: center; gap: 6px;">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#0284c7" stroke-width="2">
              <polyline points="1 4 1 10 7 10"></polyline>
              <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path>
            </svg>
            版本已回滚
          </div>
          <div style="color: #0369a1;">${escapeHtml(text)}</div>
        </div>
      `;
    } else {
      entryDiv.innerHTML = `
        <div class="refactor-result-card" style="border-color: #fca5a5; background: #fffaf0;">
          <div style="font-weight: 600; color: #dc2626; margin-bottom: 3px;">重构未完成</div>
          <div style="color: #991b1b;">${escapeHtml(text)}</div>
        </div>
      `;
    }

    copilotChatHistory.appendChild(entryDiv);
    copilotChatHistory.scrollTop = copilotChatHistory.scrollHeight;
  }

  async function handleCopilotAdjust(instruction) {
    const instr = (instruction || "").trim();
    if (!instr) return;

    if (!currentModelData || !plantumlCode || !plantumlCode.textContent) {
      appendRefactorLog("error", "请先在上方输入业务需求并点击「生成用例图」，再执行架构重构。");
      return;
    }

    // 保存上一个版本以便一键回滚
    previousUmlState = {
      model: JSON.parse(JSON.stringify(currentModelData)),
      plantuml: plantumlCode.textContent,
      issues: cachedIssues ? JSON.parse(JSON.stringify(cachedIssues)) : [],
      imageUrl: downloadBtn ? downloadBtn.href : "",
    };
    if (copilotUndoBtn) copilotUndoBtn.style.display = "inline-flex";

    // 记录重构指令
    appendRefactorLog("directive", instr);

    if (copilotSendBtn) {
      copilotSendBtn.disabled = true;
      copilotSendBtn.innerHTML = `<span>重构中…</span>`;
    }
    if (copilotInputText) {
      copilotInputText.disabled = true;
    }

    try {
      const formatVal = formatSelect ? formatSelect.value : "svg";
      const payload = {
        instruction: instr,
        current_plantuml: plantumlCode.textContent,
        current_model: currentModelData,
        format: formatVal === "source_only" ? "png" : formatVal,
      };

      const res = await apiPost("/v1/uml/chat-adjust", payload, { timeoutMs: 90000 });
      if (res && res.success) {
        appendRefactorLog("success", res.reply || "已完成模型重构演进。", res.diff_summary);

        // 更新并重绘全界面视图
        const updatedData = {
          diagram_type: "usecase",
          model: res.model || currentModelData,
          plantuml: res.plantuml,
          review_report: {
            issues: res.issues || [],
          },
          render: res.render,
        };

        renderResults(updatedData);
      } else {
        appendRefactorLog("error", "模型重构未成功，请检查指令后重试。");
      }
    } catch (err) {
      appendRefactorLog("error", `重构遇到异常：${err.message || "服务繁忙，请稍后重试"}`);
    } finally {
      if (copilotSendBtn) {
        copilotSendBtn.disabled = false;
        copilotSendBtn.innerHTML = `
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
          <span>执行重构</span>
        `;
      }
      if (copilotInputText) {
        copilotInputText.disabled = false;
        copilotInputText.focus();
      }
    }
  }

  // 表单与快捷微调事件绑定
  if (copilotInputForm && copilotInputText) {
    copilotInputForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const val = copilotInputText.value.trim();
      if (!val) return;
      copilotInputText.value = "";
      handleCopilotAdjust(val);
    });

    copilotInputText.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const val = copilotInputText.value.trim();
        if (!val) return;
        copilotInputText.value = "";
        handleCopilotAdjust(val);
      }
    });
  }

  if (copilotQuickChips) {
    copilotQuickChips.addEventListener("click", (e) => {
      const chip = e.target.closest(".copilot-chip");
      if (chip) {
        const prompt = chip.getAttribute("data-prompt") || chip.textContent.trim();
        handleCopilotAdjust(prompt);
      }
    });
  }

  if (copilotUndoBtn) {
    copilotUndoBtn.addEventListener("click", () => {
      if (!previousUmlState) return;
      const restored = {
        diagram_type: "usecase",
        model: previousUmlState.model,
        plantuml: previousUmlState.plantuml,
        review_report: {
          issues: previousUmlState.issues,
        },
        render: {
          status: "rendered",
          image_url: previousUmlState.imageUrl,
          download_url: previousUmlState.imageUrl,
          format: formatSelect ? formatSelect.value : "svg",
        },
      };
      renderResults(restored);
      appendRefactorLog("undo", "已回滚至重构前的历史架构快照，模型拓扑与要素清单已同步恢复。");
      previousUmlState = null;
      copilotUndoBtn.style.display = "none";
    });
  }

  if (copilotClearBtn && copilotChatHistory) {
    copilotClearBtn.addEventListener("click", () => {
      copilotChatHistory.innerHTML = `
        <div class="refactor-guide-card">
          <div class="refactor-guide-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#2563eb" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="16" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
            增量重构指令说明
          </div>
          <div>支持通过自然语言指令对当前模型进行边界演进与拓扑重组，操作将同步刷新画布与规范质检报告：</div>
          <ul class="refactor-guide-list">
            <li><strong>用例解耦或移除</strong>：如“去掉用户注册功能”，自动解耦所有通信连线并移出边界</li>
            <li><strong>增补业务用例</strong>：如“增加第三方在线支付功能，建立 extend 扩展关系”，自动分配唯一 UC-ID</li>
            <li><strong>参与者聚合与边界重组</strong>：如“将买家与卖家合并为统一的在校学生角色”</li>
            <li><strong>动宾命名规范化</strong>：依据 ISO/IEC 19505 规范统一用例粒度为规范动宾短语</li>
          </ul>
        </div>
      `;
    });
  }

  // 辅助别名定义，防止拼写差异
  const modelUseCasesCountText = document.getElementById("model-usecases-count-text");

  // 跨页联动：检测是否从实训任务工单带入了待质检的业务需求或参考模型
  try {
    const pendingReq = localStorage.getItem("pending_uml_requirement");
    if (pendingReq && textarea) {
      textarea.value = pendingReq;
      updateCharCount();
      localStorage.removeItem("pending_uml_requirement");
      setTimeout(() => {
        if (generateBtn) generateBtn.click();
      }, 350);
    }
  } catch (e) {
    console.warn("读取跨页建模任务失败", e);
  }
});
