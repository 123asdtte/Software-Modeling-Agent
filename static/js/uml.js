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
  const engineSelect = document.getElementById("engine-select");
  const diagramTypeSelect = document.getElementById("diagram-type-select");
  const generateBtn = document.getElementById("generate-uml-btn");
  // 原始按钮内容（含图标 SVG）：加载态会改写 textContent 丢图标，结束后必须整体还原
  const generateBtnDefaultHtml = generateBtn ? generateBtn.innerHTML : "";
  const errorBar = document.getElementById("uml-error-bar");
  const skeletonBox = document.getElementById("uml-skeleton-box");
  const resultSection = document.getElementById("uml-result-section");

  // KPI 概览条
  const kpiSystemName = document.getElementById("kpi-system-name");
  const kpiActorsCount = document.getElementById("kpi-actors-count");
  const kpiActorsDetail = document.getElementById("kpi-actors-detail");
  const kpiUsecasesCount = document.getElementById("kpi-usecases-count");
  const kpiUsecasesDetail = document.getElementById("kpi-usecases-detail");
  const kpiQualityScore = document.getElementById("kpi-quality-score");
  const kpiQualityLevel = document.getElementById("kpi-quality-level");
  const kpiScoreIcon = document.getElementById("kpi-score-icon");
  const kpiSystemLabel = document.getElementById("kpi-system-label");
  const kpiActorsLabel = document.getElementById("kpi-actors-label");
  const kpiUsecasesLabel = document.getElementById("kpi-usecases-label");
  const kpiRelationsLabel = document.getElementById("kpi-relations-label");
  const previewColTitleText = document.getElementById("preview-col-title-text");

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
  const drawioViewerEl = document.getElementById("uml-drawio-viewer");
  let workspaceMode = "plantuml"; // 跟随绘图引擎：plantuml | drawio
  let drawioSrcOriginal = "";     // 服务端导出的 drawio XML
  let drawioSrcCurrent = "";      // 当前生效（可能被编辑）的 drawio XML
  const downloadSvgBtn = document.getElementById("download-svg-btn");
  const downloadDrawioPngBtn = document.getElementById("download-drawio-png-btn");
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

  // 要素清单（按图型动态渲染至 #model-elements-body）

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
  // 类图正向工程面板
  const classCodePanel = document.getElementById("class-code-panel");
  const genClassCodeBtn = document.getElementById("gen-class-code-btn");
  const classCodeStatus = document.getElementById("class-code-status");
  const classCodeOutput = document.getElementById("class-code-output");
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

    // 按图型给预期耗时（真实实测：用例/部署 ~25-35s，活动/时序 ~40-80s，类图 ~90-110s）。
    // 只显示"已用 / 约需"而不是固定"约 30 秒"，避免类图等 100 秒时看起来像卡死。
    const EXPECTED_SECONDS = {
      usecase: 30,
      activity: 45,
      statemachine: 45,
      class: 100,
      sequence: 80,
      deployment: 35,
      auto: 60,
    };
    const typeVal = (diagramTypeSelect && diagramTypeSelect.value) || "auto";
    const expected = EXPECTED_SECONDS[typeVal] || 60;
    const startedAt = Date.now();
    const tick = () => {
      const elapsed = Math.round((Date.now() - startedAt) / 1000);
      generateBtn.textContent = `生成中… ${elapsed}s / 约 ${expected}s`;
    };
    tick();
    const elapsedTimer = setInterval(tick, 1000);

    const formatVal = formatSelect.value;
    const isSourceOnly = formatVal === "source_only";
    const payload = {
      requirement: rawVal,
      diagram_type: typeVal,
      render: !isSourceOnly,
      format: isSourceOnly ? "png" : formatVal,
      engine: (engineSelect && engineSelect.value) || "plantuml",
    };

    try {
      const data = await apiPost("/v1/uml/generate", payload, { timeoutMs: 260000 });
      renderResults(data);
    } catch (err) {
      showError(err.message || "服务异常，请稍后重试");
    } finally {
      clearInterval(elapsedTimer);
      skeletonBox.style.display = "none";
      generateBtn.disabled = false;
      // 还原完整按钮内容（文案 + 图标），不要只写纯文本
      generateBtn.innerHTML = generateBtnDefaultHtml;
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
    window.__lastImgAvailable = !!(data.render && data.render.status === "rendered");
    if (window.__lastDrawioUrl) {
      fetch(window.__lastDrawioUrl)
        .then((r) => r.text())
        .then((t) => {
          window.__lastDrawioSrc = t;
          drawioSrcOriginal = t;
          drawioSrcCurrent = t;
          if (workspaceMode === "drawio" && plantumlCode) {
            plantumlCode.textContent = t;
            if (plantumlEditor && plantumlEditor.style.display === "block") plantumlEditor.value = t;
          }
          refreshDrawioDownloadBtn(t, currentModelData.type);
          showCanvasForMode();
        })
        .catch(() => {});
    }
    const issues = (data.review_report && data.review_report.issues) || [];
    cachedIssues = issues;

    // 8.1 渲染 KPI 指标条
    renderKpiBanner(data);

    // 8.2 左列：用例图渲染与画布初始化
    renderCanvasDiagram(data);

    // 8.3 右列：质检报告表格渲染与筛选绑定
    renderReviewTable();
    showCanvasForMode();

    // 8.4 渲染模型要素清单（参与者与用例表格）
    renderModelElements(currentModelData);

    // 8.5 底部 PlantUML 源码展示与缓存
    originalPumlSource = data.plantuml || "";
    plantumlCode.textContent = originalPumlSource;
    if (plantumlEditor) {
      plantumlEditor.value = originalPumlSource;
    }

    // 8.6 按图型适配标题 / 对话重构入口等 UI
    applyTypeUI(data);
  }

  // 8.0 按图型适配画布标题与对话重构入口（活动图/状态机图暂不支持对话式增量重构）
  function applyTypeUI(data) {
    const dtype = data.diagram_type || "usecase";
    const titles = {
      usecase: "用例模型画布",
      activity: "活动模型画布",
      statemachine: "状态机模型画布",
      class: "类模型画布",
      sequence: "时序模型画布",
      deployment: "部署模型画布",
    };
    if (previewColTitleText) {
      previewColTitleText.textContent = titles[dtype] || "UML 模型画布";
    }
    // 三图型均启用对话式修正（架构增量重构 Copilot）
    if (tabBtnCopilot) tabBtnCopilot.style.display = "";
    if (btnOpenCopilot) btnOpenCopilot.style.display = "inline-flex";
    if (copilotQuickChips) copilotQuickChips.style.opacity = "1";
    // 快捷重构指令随图型切换，避免用例图话术出现在类图/部署图场景
    renderCopilotChips(dtype);
    // 类图专属：显示/重置 Java 正向工程面板
    resetClassCodePanel(dtype);
  }

  // 8.1 KPI 指标条计算与渲染
  function renderKpiBanner(data) {
    const model = data.model || {};
    const dtype = data.diagram_type || "usecase";
    const report = data.review_report || {};
    const issues = report.issues || [];

    // 按图型设置前 4 张卡片的标签与指标
    if (dtype === "activity") {
      const nodes = model.nodes || [];
      const actions = nodes.filter((n) => n.kind === "action").length;
      const decisions = nodes.filter((n) => n.kind === "decision").length;
      const parallel = nodes.filter((n) => n.kind === "fork" || n.kind === "join").length;
      const swimlanes = model.swimlanes || [];
      if (kpiSystemLabel) kpiSystemLabel.textContent = "业务模块边界";
      if (kpiSystemName) kpiSystemName.textContent = model.module || "未命名业务模块";
      if (kpiActorsLabel) kpiActorsLabel.textContent = "泳道分区 (Lanes)";
      if (kpiActorsCount) kpiActorsCount.textContent = `${swimlanes.length} 个`;
      if (kpiActorsDetail) kpiActorsDetail.textContent = (swimlanes.map((s) => s.name).join("、") || "未划分泳道").slice(0, 40);
      if (kpiUsecasesLabel) kpiUsecasesLabel.textContent = "活动/动作节点";
      if (kpiUsecasesCount) kpiUsecasesCount.textContent = `${actions} 个`;
      if (kpiUsecasesDetail) kpiUsecasesDetail.textContent = `${nodes.length} 节点 · ${decisions} 决策`;
      if (kpiRelationsLabel) kpiRelationsLabel.textContent = "决策 / 并行";
      if (kpiRelationsCount) kpiRelationsCount.textContent = `${decisions} 决策`;
      if (kpiRelationsDetail) kpiRelationsDetail.textContent = `${parallel} 处并行分叉/汇合`;
    } else if (dtype === "statemachine") {
      const states = model.states || [];
      const transitions = model.transitions || [];
      const initials = states.filter((s) => s.kind === "initial").length;
      const finals = states.filter((s) => s.kind === "final").length;
      const paused = states.filter((s) => s.kind === "paused").length;
      if (kpiSystemLabel) kpiSystemLabel.textContent = "建模对象 (Object)";
      if (kpiSystemName) kpiSystemName.textContent = model.object || "未命名对象";
      if (kpiActorsLabel) kpiActorsLabel.textContent = "状态总数 (States)";
      if (kpiActorsCount) kpiActorsCount.textContent = `${states.length} 个`;
      if (kpiActorsDetail) kpiActorsDetail.textContent = `${paused} 个挂起态`;
      if (kpiUsecasesLabel) kpiUsecasesLabel.textContent = "状态转换 (Transitions)";
      if (kpiUsecasesCount) kpiUsecasesCount.textContent = `${transitions.length} 条`;
      if (kpiUsecasesDetail) kpiUsecasesDetail.textContent = `${initials} 初始 · ${finals} 终态`;
      if (kpiRelationsLabel) kpiRelationsLabel.textContent = "初 / 终态";
      if (kpiRelationsCount) kpiRelationsCount.textContent = `${initials} 初 · ${finals} 终`;
      if (kpiRelationsDetail) kpiRelationsDetail.textContent = `${paused} 挂起态`;
    } else if (dtype === "class") {
      const classes = model.classes || [];
      const relations = model.relations || [];
      const ifaces = classes.filter((c) => c.is_interface).length;
      const abstracts = classes.filter((c) => c.is_abstract && !c.is_interface).length;
      const concretes = classes.length - ifaces - abstracts;
      const attrTotal = classes.reduce((sum, c) => sum + (c.attributes || []).length, 0);
      const methodTotal = classes.reduce((sum, c) => sum + (c.methods || []).length, 0);
      const countRel = (t) => relations.filter((r) => r.type === t).length;
      if (kpiSystemLabel) kpiSystemLabel.textContent = "建模主题 (Model)";
      if (kpiSystemName) kpiSystemName.textContent = model.title || "类图模型";
      if (kpiActorsLabel) kpiActorsLabel.textContent = "类 / 接口 (Classes)";
      if (kpiActorsCount) kpiActorsCount.textContent = `${classes.length} 个`;
      if (kpiActorsDetail) {
        kpiActorsDetail.textContent = `${concretes} 具体类 · ${abstracts} 抽象类 · ${ifaces} 接口`;
      }
      if (kpiUsecasesLabel) kpiUsecasesLabel.textContent = "成员要素 (Members)";
      if (kpiUsecasesCount) kpiUsecasesCount.textContent = `${attrTotal + methodTotal} 项`;
      if (kpiUsecasesDetail) kpiUsecasesDetail.textContent = `${attrTotal} 属性 · ${methodTotal} 方法`;
      if (kpiRelationsLabel) kpiRelationsLabel.textContent = "类间关系 (Relations)";
      if (kpiRelationsCount) kpiRelationsCount.textContent = `${relations.length} 条`;
      if (kpiRelationsDetail) {
        const structCnt = countRel("aggregation") + countRel("composition");
        kpiRelationsDetail.textContent = `${countRel("generalization")} 泛化 · ${countRel("realization")} 实现 · ${structCnt} 聚合组合`;
      }
    } else if (dtype === "sequence") {
      const lifelines = model.lifelines || [];
      const messages = model.messages || [];
      const fragments = model.fragments || [];
      const kindOf = (k) => lifelines.filter((l) => (l.kind || "object") === k).length;
      const msgOf = (k) => messages.filter((m) => (m.kind || "sync") === k).length;
      const fragOf = (k) => fragments.filter((f) => (f.kind || "alt") === k).length;
      if (kpiSystemLabel) kpiSystemLabel.textContent = "交互场景 (Scenario)";
      if (kpiSystemName) kpiSystemName.textContent = model.title || "时序交互模型";
      if (kpiActorsLabel) kpiActorsLabel.textContent = "生命线 (Lifelines)";
      if (kpiActorsCount) kpiActorsCount.textContent = `${lifelines.length} 条`;
      if (kpiActorsDetail) {
        const datasourceCnt = kindOf("database") + kindOf("entity");
        kpiActorsDetail.textContent = `${kindOf("actor")} 角色 · ${lifelines.length - kindOf("actor") - datasourceCnt} 控制对象 · ${datasourceCnt} 数据源`;
      }
      if (kpiUsecasesLabel) kpiUsecasesLabel.textContent = "消息 (Messages)";
      if (kpiUsecasesCount) kpiUsecasesCount.textContent = `${messages.length} 条`;
      if (kpiUsecasesDetail) {
        kpiUsecasesDetail.textContent = `${msgOf("sync")} 同步 · ${msgOf("async")} 异步 · ${msgOf("return")} 返回`;
      }
      if (kpiRelationsLabel) kpiRelationsLabel.textContent = "交互片段 (Fragments)";
      if (kpiRelationsCount) kpiRelationsCount.textContent = `${fragments.length} 个`;
      if (kpiRelationsDetail) {
        const parts = ["alt", "loop", "opt", "par"].filter((k) => fragOf(k) > 0).map((k) => `${k} ${fragOf(k)}`);
        kpiRelationsDetail.textContent = parts.length ? parts.join(" · ") : "无组合片段";
      }
    } else if (dtype === "deployment") {
      const nodes = model.nodes || [];
      const artifacts = model.artifacts || [];
      const associations = model.associations || [];
      const devices = nodes.filter((n) => n.kind === "device").length;
      const envs = nodes.length - devices;
      const deployed = artifacts.filter((a) => a.deployed_on).length;
      const commCnt = associations.filter((a) => (a.kind || "communication") === "communication").length;
      if (kpiSystemLabel) kpiSystemLabel.textContent = "部署视图 (View)";
      if (kpiSystemName) kpiSystemName.textContent = model.title || "部署架构模型";
      if (kpiActorsLabel) kpiActorsLabel.textContent = "节点 (Nodes)";
      if (kpiActorsCount) kpiActorsCount.textContent = `${nodes.length} 个`;
      if (kpiActorsDetail) kpiActorsDetail.textContent = `${devices} 物理设备 · ${envs} 执行环境`;
      if (kpiUsecasesLabel) kpiUsecasesLabel.textContent = "部署构件 (Artifacts)";
      if (kpiUsecasesCount) kpiUsecasesCount.textContent = `${artifacts.length} 个`;
      if (kpiUsecasesDetail) {
        kpiUsecasesDetail.textContent = artifacts.length
          ? `${deployed} 已定位宿主 · ${artifacts.length - deployed} 待定`
          : "未声明部署构件";
      }
      if (kpiRelationsLabel) kpiRelationsLabel.textContent = "部署 / 通信关系";
      if (kpiRelationsCount) kpiRelationsCount.textContent = `${associations.length} 条`;
      if (kpiRelationsDetail) {
        kpiRelationsDetail.textContent = `${commCnt} 通信 · ${associations.length - commCnt} 依赖/关联`;
      }
    } else {
      const actors = model.actors || [];
      const usecases = model.usecases || [];
      if (kpiSystemLabel) kpiSystemLabel.textContent = "目标系统边界";
      if (kpiSystemName) kpiSystemName.textContent = model.system || "教学业务系统";
      if (kpiActorsLabel) kpiActorsLabel.textContent = "识别参与者 (Actors)";
      if (kpiActorsCount) kpiActorsCount.textContent = `${actors.length} 位`;
      if (kpiActorsDetail) {
        const primaryCount = actors.filter((a) => a.role === "primary").length;
        const secondaryCount = actors.length - primaryCount;
        kpiActorsDetail.textContent = `${primaryCount} 主角色 · ${secondaryCount} 辅角色`;
      }
      if (kpiUsecasesLabel) kpiUsecasesLabel.textContent = "核心用例 (Use Cases)";
      if (kpiUsecasesCount) kpiUsecasesCount.textContent = `${usecases.length} 个`;
      if (kpiUsecasesDetail) kpiUsecasesDetail.textContent = "单意图粒度建模";
      if (kpiRelationsLabel) kpiRelationsLabel.textContent = "规约高级关系";
      const puml = data.plantuml || "";
      const includes = (puml.match(/<<include>>/gi) || []).length;
      const extendsCnt = (puml.match(/<<extend>>/gi) || []).length;
      if (kpiRelationsCount) kpiRelationsCount.textContent = `${includes + extendsCnt} 条关系`;
      if (kpiRelationsDetail) kpiRelationsDetail.textContent = `${includes} include · ${extendsCnt} extend`;
    }

    // 规范达标率（通用）
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
        kpiScoreIcon.innerHTML = IconLib.svg("shield-check", 14);
      } else if (score >= 70) {
        kpiQualityLevel.textContent = "良好·轻微瑕疵";
        kpiQualityLevel.style.color = "var(--color-warning)";
        kpiScoreIcon.className = "kpi-icon-wrap kpi-icon-blue";
        kpiScoreIcon.innerHTML = IconLib.svg("triangle-alert", 14);
      } else {
        kpiQualityLevel.textContent = "需优化·存在错误";
        kpiQualityLevel.style.color = "var(--color-error)";
        kpiScoreIcon.className = "kpi-icon-wrap kpi-icon-purple";
        kpiScoreIcon.innerHTML = IconLib.svg("circle-x", 14);
      }
    }
  }

  // 8.2 画布图片与缩放工具条
  function renderCanvasDiagram(data) {
    const renderInfo = data.render || {};
    const dtype = data.diagram_type || "usecase";
    const titleName =
      data.model?.module || data.model?.object || data.model?.system || data.model?.title || "UML";
    applyZoom(1.0); // 重置为 100%

    if (renderInfo.status === "rendered" && renderInfo.download_url) {
      umlImage.src = renderInfo.download_url;
      const typeCnNames = {
        usecase: "用例图",
        activity: "活动图",
        statemachine: "状态机图",
        class: "类图",
        sequence: "时序图",
        deployment: "部署图",
      };
      umlImage.alt = `${titleName} ${typeCnNames[dtype] || "UML 图"}`;
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
      downloadBtn.download = `${dtype}_${Date.now()}.${(renderInfo.format || "png").toLowerCase()}`;
      downloadBtn.textContent = `下载 ${fmt}`;
      downloadBtn.style.display = "inline-flex";

      // 可编辑源码导出（按「可编辑源码导出」偏好显示 draw.io / PlantUML 下载）

      if (downloadDrawioBtn) {
        const drawioUrl = window.__lastDrawioUrl || null;
        if (workspaceMode !== "drawio" && drawioUrl) {
          downloadDrawioBtn.href = drawioUrl;
          downloadDrawioBtn.download = `${dtype}_${Date.now()}.xml`;
          downloadDrawioBtn.style.display = "inline-flex";
        } else if (workspaceMode === "drawio") {
          downloadDrawioBtn.style.display = "none"; // 编辑版由「下载 .xml」按钮接管
        } else {
          downloadDrawioBtn.style.display = "none";
        }
      }
      if (downloadPumlBtn) {
        const isDrawioMode = workspaceMode === "drawio";
        if (isDrawioMode) {
          // draw.io 工作区模式：此按钮变为「下载 .xml」（编辑版优先）
          refreshDrawioDownloadBtn(drawioSrcCurrent || window.__lastDrawioSrc || "", dtype);
        } else if (workspaceMode === "plantuml") {
          const blob = new Blob([originalPumlSource || ""], { type: "text/plain;charset=utf-8" });
          downloadPumlBtn.href = URL.createObjectURL(blob);
          downloadPumlBtn.download = `${dtype}_${Date.now()}.puml`;
          downloadPumlBtn.style.display = "inline-flex";
        } else {
          downloadPumlBtn.style.display = "none";
        }
      }
      const svgUrl = (window.__lastSvgUrl = data.svg_download_url || null);
      if (downloadSvgBtn) {
        if (svgUrl) {
          downloadSvgBtn.href = svgUrl;
          downloadSvgBtn.download = `${dtype}_${Date.now()}.svg`;
          downloadSvgBtn.style.display = "inline-flex";
        } else {
          downloadSvgBtn.style.display = "none";
        }
      }
      if (downloadDrawioPngBtn) {
        if (svgUrl) {
          // 惰性转换：点击时 SVG → canvas → PNG（drawio 版式位图，2x 高清）
          downloadDrawioPngBtn.onclick = async () => {
            const svgText = await (await fetch(svgUrl)).text();
            const img = new Image();
            const dataUrl = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svgText);
            await new Promise((res, rej) => {
              img.onload = res;
              img.onerror = rej;
              img.src = dataUrl;
            });
            const canvas = document.createElement("canvas");
            canvas.width = img.naturalWidth * 2;
            canvas.height = img.naturalHeight * 2;
            const ctx = canvas.getContext("2d");
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            canvas.toBlob((blob) => {
              const a = document.createElement("a");
              a.href = URL.createObjectURL(blob);
              a.download = `${dtype}_${Date.now()}.png`;
              a.click();
              URL.revokeObjectURL(a.href);
            }, "image/png");
          };
          downloadDrawioPngBtn.style.display = "inline-flex";
        } else {
          downloadDrawioPngBtn.style.display = "none";
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
        reviewBadgeContainer.innerHTML = `<span class="badge badge-error">${IconLib.svg("circle-x", 14)} ${errorCount} 项严重违规</span>`;
      } else if (warnCount > 0) {
        reviewBadgeContainer.innerHTML = `<span class="badge badge-warning">${IconLib.svg("triangle-alert", 14)} ${warnCount} 项教学预警</span>`;
      } else {
        reviewBadgeContainer.innerHTML = `<span class="badge badge-success">${IconLib.svg("check", 14)} 规范质检通过</span>`;
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
        <div style="font-size: 24px; margin-bottom: 6px;">${IconLib.svg("search", 14)}</div>
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
          ${item.suggestion ? `<div style="font-size: 12px; color: var(--color-primary); margin-top: 4px; background: rgba(59, 130, 246, 0.08); padding: 4px 8px; border-radius: 4px; display: inline-block;">${IconLib.svg("lightbulb", 14)} 教学提示：${escapeHtml(item.suggestion)}</div>` : ""}
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
    const body = document.getElementById("model-elements-body");
    if (!body) return;
    const dtype = model.type || "usecase";
    if (dtype === "activity") {
      body.innerHTML = buildActivityElements(model);
    } else if (dtype === "statemachine") {
      body.innerHTML = buildStateMachineElements(model);
    } else if (dtype === "class") {
      body.innerHTML = buildClassElements(model);
    } else if (dtype === "sequence") {
      body.innerHTML = buildSequenceElements(model);
    } else if (dtype === "deployment") {
      body.innerHTML = buildDeploymentElements(model);
    } else {
      body.innerHTML = buildUseCaseElements(model);
    }
  }

  // 用例图要素清单
  function buildUseCaseElements(model) {
    const actors = model.actors || [];
    const usecases = model.usecases || [];
    const actorChips = actors.length
      ? actors.map((act) => {
          const isPrimary = act.role === "primary";
          const roleBadgeClass = isPrimary ? "actor-role-primary" : "actor-role-secondary";
          const roleBadgeText = isPrimary ? "主角色" : "次角色";
          return `<div class="actor-chip">
            <span class="actor-icon">${isPrimary ? IconLib.svg("user", 14) : IconLib.svg("settings", 14)}</span>
            <span class="actor-name">${escapeHtml(act.name)}</span>
            <span class="actor-role-badge ${roleBadgeClass}">${roleBadgeText}</span>
          </div>`;
        }).join("")
      : `<span style="font-size: 13px; color: var(--color-text-secondary);">未提取到明确参与者</span>`;

    const ucRows = usecases.length
      ? usecases.map((uc) => {
          const actorTags = (uc.actors || []).map((a) => `<span class="badge badge-info" style="font-size: 11px;">${escapeHtml(a)}</span>`).join(" ");
          return `<tr>
            <td><code style="font-family: var(--font-mono); font-weight: 600; color: var(--color-primary); font-size: 12px;">${escapeHtml(uc.id || "-")}</code></td>
            <td style="font-weight: 600; color: var(--color-text);">${escapeHtml(uc.name || "-")}</td>
            <td><div style="display: flex; gap: 4px; flex-wrap: wrap;">${actorTags || "-"}</div></td>
            <td style="color: var(--color-text-secondary); font-size: 13px;">${escapeHtml(uc.goal || "完成对应业务流程")}</td>
          </tr>`;
        }).join("")
      : `<tr><td colspan="4" style="text-align: center; color: var(--color-text-secondary); padding: 24px 0;">未提取到具体业务用例</td></tr>`;

    return `
      <div>
        <div class="elements-section-header">
          <span><i data-icon="users"></i> 识别的参与者 (Actors)</span>
          <span style="font-size: 11px; color: var(--color-text-secondary);">共 ${actors.length} 位角色</span>
        </div>
        <div class="actors-chip-group">${actorChips}</div>
      </div>
      <div>
        <div class="elements-section-header">
          <span><i data-icon="package"></i> 用例业务清单 (Use Cases)</span>
          <span style="font-size: 11px; color: var(--color-text-secondary);">共 ${usecases.length} 个用例</span>
        </div>
        <div style="overflow-x: auto;">
          <table class="usecase-element-table">
            <thead><tr><th style="width: 75px;">用例 ID</th><th style="width: 130px;">用例名称</th><th style="width: 100px;">关联参与者</th><th>业务目标 (Goal)</th></tr></thead>
            <tbody>${ucRows}</tbody>
          </table>
        </div>
      </div>`;
  }

  // 活动图要素清单：泳道分区 + 活动节点（动作/决策/分叉/汇合/起止）
  function buildActivityElements(model) {
    const swimlanes = model.swimlanes || [];
    const nodes = model.nodes || [];
    const actions = nodes.filter((n) => n.kind === "action");
    const decisions = nodes.filter((n) => n.kind === "decision");
    const laneChips = swimlanes.length
      ? swimlanes.map((s) => `<div class="actor-chip"><span class="actor-icon">${IconLib.svg("link", 14)}</span><span class="actor-name">${escapeHtml(s.name)}</span></div>`).join("")
      : `<span style="font-size: 13px; color: var(--color-text-secondary);">未划分泳道</span>`;

    const kindLabelMap = { action: "动作", decision: "决策", fork: "分叉", join: "汇合", initial: "起始", final: "结束", merge: "合并" };
    const nodeRows = nodes.length
      ? nodes.map((n) => {
          const kindLabel = kindLabelMap[n.kind] || n.kind;
          const laneTag = n.lane ? `<span class="badge badge-info" style="font-size: 11px;">${escapeHtml(n.lane)}</span>` : `<span style="color: var(--color-text-secondary);">—</span>`;
          return `<tr>
            <td><code style="font-family: var(--font-mono); font-weight: 600; color: var(--color-primary); font-size: 12px;">${escapeHtml(n.id || "-")}</code></td>
            <td style="font-weight: 600; color: var(--color-text);">${escapeHtml(n.name || kindLabel)}</td>
            <td>${laneTag}</td>
            <td><span class="badge badge-secondary" style="font-size: 11px;">${kindLabel}</span></td>
          </tr>`;
        }).join("")
      : `<tr><td colspan="4" style="text-align: center; color: var(--color-text-secondary); padding: 24px 0;">未提取到活动节点</td></tr>`;

    return `
      <div>
        <div class="elements-section-header">
          <span><i data-icon="link"></i> 泳道分区 (Swimlanes)</span>
          <span style="font-size: 11px; color: var(--color-text-secondary);">共 ${swimlanes.length} 个责任分区</span>
        </div>
        <div class="actors-chip-group">${laneChips}</div>
      </div>
      <div>
        <div class="elements-section-header">
          <span><i data-icon="package"></i> 活动节点清单 (Nodes)</span>
          <span style="font-size: 11px; color: var(--color-text-secondary);">${actions.length} 动作 · ${decisions.length} 决策</span>
        </div>
        <div style="overflow-x: auto;">
          <table class="usecase-element-table">
            <thead><tr><th style="width: 75px;">节点 ID</th><th style="width: 150px;">节点名称</th><th style="width: 120px;">归属泳道</th><th>类型</th></tr></thead>
            <tbody>${nodeRows}</tbody>
          </table>
        </div>
      </div>`;
  }

  // 状态机图要素清单：状态 + 状态转换
  function buildStateMachineElements(model) {
    const states = model.states || [];
    const transitions = model.transitions || [];
    const stateKindMap = { initial: "初始", normal: "普通", final: "终态", paused: "挂起" };

    const stateRows = states.length
      ? states.map((s) => {
          const kindLabel = stateKindMap[s.kind] || s.kind;
          const kindBadge = s.kind === "initial" ? "actor-role-primary" : s.kind === "final" ? "actor-role-secondary" : "";
          const historyTag = s.kind === "paused" && s.history ? `<span class="badge badge-secondary" style="font-size: 11px; margin-left: 4px;">${escapeHtml(s.history)} 历史</span>` : "";
          return `<tr>
            <td><code style="font-family: var(--font-mono); font-weight: 600; color: var(--color-primary); font-size: 12px;">${escapeHtml(s.id || "-")}</code></td>
            <td style="font-weight: 600; color: var(--color-text);">${escapeHtml(s.name || kindLabel)}</td>
            <td><span class="badge ${kindBadge || "badge-secondary"}" style="font-size: 11px;">${kindLabel}</span>${historyTag}</td>
          </tr>`;
        }).join("")
      : `<tr><td colspan="3" style="text-align: center; color: var(--color-text-secondary); padding: 24px 0;">未提取到状态</td></tr>`;

    const transRows = transitions.length
      ? transitions.map((t) => {
          const evt = escapeHtml(t.event || "（任意事件）");
          const guard = t.guard ? ` [${escapeHtml(t.guard)}]` : "";
          const from = t.any_state ? "任意状态" : escapeHtml(t.from || "-");
          return `<tr>
            <td><code style="font-family: var(--font-mono); font-size: 12px;">${from}</code></td>
            <td><code style="font-family: var(--font-mono); font-size: 12px;">${escapeHtml(t.to || "-")}</code></td>
            <td style="color: var(--color-text-secondary); font-size: 13px;">${evt}${guard}</td>
          </tr>`;
        }).join("")
      : `<tr><td colspan="3" style="text-align: center; color: var(--color-text-secondary); padding: 24px 0;">未提取到状态转换</td></tr>`;

    return `
      <div>
        <div class="elements-section-header">
          <span><i data-icon="package"></i> 状态清单 (States)</span>
          <span style="font-size: 11px; color: var(--color-text-secondary);">共 ${states.length} 个状态</span>
        </div>
        <div style="overflow-x: auto;">
          <table class="usecase-element-table">
            <thead><tr><th style="width: 75px;">状态 ID</th><th style="width: 150px;">状态名称</th><th>类型</th></tr></thead>
            <tbody>${stateRows}</tbody>
          </table>
        </div>
      </div>
      <div>
        <div class="elements-section-header">
          <span><i data-icon="link"></i> 状态转换清单 (Transitions)</span>
          <span style="font-size: 11px; color: var(--color-text-secondary);">共 ${transitions.length} 条转换</span>
        </div>
        <div style="overflow-x: auto;">
          <table class="usecase-element-table">
            <thead><tr><th style="width: 140px;">源状态</th><th style="width: 140px;">目标状态</th><th>触发事件 [监护条件]</th></tr></thead>
            <tbody>${transRows}</tbody>
          </table>
        </div>
      </div>`;
  }

  // 按图型提供贴合的 Copilot 快捷重构指令（委托绑定，替换 innerHTML 不影响事件）
  const COPILOT_CHIPS = {
    usecase: [
      ["解耦认证用例", "去掉身份安全鉴权用例，移除 include 依赖"],
      ["移除注册分支", "去掉用户注册功能，简化业务流程"],
      ["扩展支付用例", "增加一个「第三方在线支付」用例，并建立 extend 扩展关系"],
      ["合并参与者边界", "把系统参与者买家与卖家合并为统一的「在校学生」角色"],
      ["规范动宾短语", "将所有用例名称优化为规范动宾短语结构"],
    ],
    activity: [
      ["合并重复动作", "合并重复的动作节点，保持流程主干清晰"],
      ["补异常分支", "为主要动作补充异常处理分支与对应决策节点"],
      ["补监护条件", "为每个决策节点补充明确的监护条件说明"],
      ["重划泳道", "按角色职责重新划分泳道，使每个动作归属唯一责任方"],
    ],
    statemachine: [
      ["补异常态", "补充异常状态及其恢复转换，保证系统可自愈"],
      ["补触发事件", "为每条状态转换补齐触发事件名称"],
      ["清理不可达", "删除不可达状态并保证从初始态可达所有状态"],
      ["收敛终态", "补充通向终态的收敛路径，避免流程悬空"],
    ],
    class: [
      ["补接口实现", "抽取公共行为为接口，并让相关类建立 realization 实现关系"],
      ["标可见性", "为所有属性和方法补充规范的可见性标注"],
      ["拆分大类", "把职责过多的类拆分为多个高内聚的类，并用组合关系连接"],
      ["补多重性", "为关联关系两端补充多重性标注（如 1、0..*、1..*）"],
    ],
    sequence: [
      ["补异常分支", "补充一个 alt 片段描述校验失败时的异常返回流程"],
      ["改异步消息", "把非阻塞的通知类调用改为异步消息（async）"],
      ["补返回消息", "为每次同步调用补充对应的 return 返回消息"],
      ["拆长流程", "把过长的交互拆分为主流程与 loop 片段循环处理"],
    ],
    deployment: [
      ["补 K8s 入口", "补充 Ingress 与 Service 节点，并建立到后端服务的通信关系"],
      ["独立数据库节点", "把数据库拆分到独立的数据库节点，并标注主从规格"],
      ["标注副本数", "为无状态服务节点标注副本数量等部署规格"],
      ["补通信路径", "补充服务之间的通信关系并标注协议"],
    ],
  };

  function renderCopilotChips(dtype) {
    if (!copilotQuickChips) return;
    const chips = COPILOT_CHIPS[dtype] || COPILOT_CHIPS.usecase;
    copilotQuickChips.innerHTML = chips
      .map(
        ([label, prompt]) =>
          `<button type="button" class="copilot-chip" data-prompt="${escapeHtml(prompt)}">${escapeHtml(label)}</button>`
      )
      .join("");
  }

  // 类图正向工程：按当前类图生成 Java 骨架代码（仅 class 图型可见）
  const CLASS_CODE_HINT = "按当前类图生成可编译的 Java 类/接口骨架（方法体为 TODO 占位），用于课程「类图正向工程」环节。";

  function resetClassCodePanel(dtype) {
    if (!classCodePanel) return;
    const isClass = dtype === "class";
    classCodePanel.style.display = isClass ? "block" : "none";
    if (!isClass) return;
    if (classCodeOutput) classCodeOutput.innerHTML = "";
    if (classCodeStatus) {
      classCodeStatus.style.color = "var(--color-text-secondary)";
      classCodeStatus.textContent = CLASS_CODE_HINT;
    }
    if (genClassCodeBtn) {
      genClassCodeBtn.disabled = false;
      genClassCodeBtn.textContent = "生成骨架代码";
    }
  }

  async function generateClassCode() {
    if (!currentModelData || !(currentModelData.classes || []).length) {
      if (classCodeStatus) {
        classCodeStatus.style.color = "var(--color-error)";
        classCodeStatus.textContent = "当前类图没有可转换的类，请先补充类与属性后再试。";
      }
      return;
    }
    if (genClassCodeBtn) {
      genClassCodeBtn.disabled = true;
      genClassCodeBtn.textContent = "生成中…";
    }
    if (classCodeStatus) {
      classCodeStatus.style.color = "var(--color-text-secondary)";
      classCodeStatus.textContent = "正在生成 Java 骨架代码…";
    }
    try {
      const data = await apiPost(
        "/v1/uml/class-code",
        { model: currentModelData },
        { timeoutMs: 30000, showProgress: false }
      );
      const files = data.files || {};
      const names = Object.keys(files);
      if (!names.length) throw new Error("服务未返回任何 Java 文件");
      if (classCodeOutput) {
        classCodeOutput.innerHTML = names
          .map(
            (n) => `<details class="code-details" style="margin-top: 8px;">
              <summary style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-family: var(--font-mono); font-size: 12px;">${escapeHtml(n)}</span>
                <span style="font-size: 11px; color: var(--color-text-secondary);">点击展开 / 收起</span>
              </summary>
              <div style="display: flex; justify-content: flex-end; margin-top: 6px;">
                <a class="btn btn-secondary" style="font-size: 11px; padding: 2px 10px;"
                   href="data:text/plain;charset=utf-8,${encodeURIComponent(files[n])}"
                   download="${escapeHtml(n)}">下载 ${escapeHtml(n)}</a>
              </div>
              <pre class="code-block" style="margin-top: 6px;">${escapeHtml(files[n])}</pre>
            </details>`
          )
          .join("");
      }
      if (classCodeStatus) {
        classCodeStatus.style.color = "var(--color-success)";
        classCodeStatus.textContent = `已按 ${data.class_count || names.length} 个类型生成 ${data.file_count || names.length} 个 Java 文件；方法体为 TODO 占位，可下载后补全业务逻辑。`;
      }
      if (genClassCodeBtn) genClassCodeBtn.textContent = "重新生成";
    } catch (err) {
      if (classCodeStatus) {
        classCodeStatus.style.color = "var(--color-error)";
        classCodeStatus.textContent = `生成失败：${err.message || "服务异常，请稍后重试"}`;
      }
      if (genClassCodeBtn) genClassCodeBtn.textContent = "重试生成";
    } finally {
      if (genClassCodeBtn) genClassCodeBtn.disabled = false;
    }
  }

  if (genClassCodeBtn) {
    genClassCodeBtn.addEventListener("click", generateClassCode);
  }

  // 类图要素清单：类/接口（含成员统计）+ 类间关系
  function buildClassElements(model) {
    const classes = model.classes || [];
    const relations = model.relations || [];

    const classRows = classes.length
      ? classes.map((c) => {
          const kindLabel = c.is_interface ? "接口" : c.is_abstract ? "抽象类" : "具体类";
          const kindBadge = c.is_interface ? "badge-info" : c.is_abstract ? "badge-warning" : "badge-success";
          const attrs = (c.attributes || []).map((a) => `${visibilityMark(a.visibility)}${a.name}`).join(", ");
          const methods = (c.methods || [])
            .map((m) => {
              const ps = (m.params || []).map((p) => `${p.name}: ${p.type || "Object"}`).join(", ");
              return `${visibilityMark(m.visibility)}${m.name}(${ps})`;
            })
            .join(", ");
          return `<tr>
            <td style="font-weight: 600; color: var(--color-text);">${escapeHtml(c.name || "-")}</td>
            <td><span class="badge ${kindBadge}" style="font-size: 11px;">${kindLabel}</span></td>
            <td style="color: var(--color-text-secondary); font-size: 13px;">${attrs ? escapeHtml(attrs.slice(0, 60)) : "—"}</td>
            <td style="color: var(--color-text-secondary); font-size: 13px;">${methods ? escapeHtml(methods.slice(0, 60)) : "—"}</td>
          </tr>`;
        }).join("")
      : `<tr><td colspan="4" style="text-align: center; color: var(--color-text-secondary); padding: 24px 0;">未提取到类或接口</td></tr>`;

    const relationCnMap = {
      association: "关联",
      aggregation: "聚合",
      composition: "组合",
      generalization: "泛化(继承)",
      dependency: "依赖",
      realization: "实现",
    };
    const relationRows = relations.length
      ? relations.map((r) => {
          const labelText = relationCnMap[r.type] || r.type || "-";
          const multFrom = r.source_multiplicity ? ` [${r.source_multiplicity}]` : "";
          const multTo = r.target_multiplicity ? ` [${r.target_multiplicity}]` : "";
          return `<tr>
            <td><code style="font-family: var(--font-mono); font-size: 12px;">${escapeHtml(r.from || r.source_id || "-")}${escapeHtml(multFrom)}</code></td>
            <td><code style="font-family: var(--font-mono); font-size: 12px;">${escapeHtml(r.to || r.target_id || "-")}${escapeHtml(multTo)}</code></td>
            <td><span class="badge badge-secondary" style="font-size: 11px;">${escapeHtml(labelText)}</span></td>
            <td style="color: var(--color-text-secondary); font-size: 13px;">${escapeHtml(r.label || "—")}</td>
          </tr>`;
        }).join("")
      : `<tr><td colspan="4" style="text-align: center; color: var(--color-text-secondary); padding: 24px 0;">未声明类间关系</td></tr>`;

    return `
      <div>
        <div class="elements-section-header">
          <span><i data-icon="package"></i> 类与接口清单 (Classes)</span>
          <span style="font-size: 11px; color: var(--color-text-secondary);">共 ${classes.length} 个类型</span>
        </div>
        <div style="overflow-x: auto;">
          <table class="usecase-element-table">
            <thead><tr><th style="width: 150px;">类 / 接口名</th><th style="width: 90px;">类型</th><th style="width: 200px;">属性</th><th>方法</th></tr></thead>
            <tbody>${classRows}</tbody>
          </table>
        </div>
      </div>
      <div>
        <div class="elements-section-header">
          <span><i data-icon="link"></i> 类间关系 (Relations)</span>
          <span style="font-size: 11px; color: var(--color-text-secondary);">共 ${relations.length} 条关系</span>
        </div>
        <div style="overflow-x: auto;">
          <table class="usecase-element-table">
            <thead><tr><th style="width: 160px;">源 (from)</th><th style="width: 160px;">目标 (to)</th><th style="width: 110px;">关系类型</th><th>标签</th></tr></thead>
            <tbody>${relationRows}</tbody>
          </table>
        </div>
      </div>`;
  }

  // 后端 Visibility 枚举值即符号本身（+ - # ~），同时兼容单词写法
  function visibilityMark(vis) {
    if (!vis) return "";
    const map = {
      "+": "+",
      "-": "-",
      "#": "#",
      "~": "~",
      public: "+",
      private: "-",
      protected: "#",
      package: "~",
    };
    return map[vis] || "";
  }

  // 时序图要素清单：生命线 + 按序消息 + 组合片段
  function buildSequenceElements(model) {
    const lifelines = model.lifelines || [];
    const messages = model.messages || [];
    const fragments = model.fragments || [];
    const kindCnMap = {
      actor: "角色",
      object: "对象",
      boundary: "边界",
      control: "控制",
      entity: "实体",
      database: "数据库",
    };
    const msgKindCnMap = { sync: "同步", async: "异步", return: "返回", create: "创建", destroy: "销毁" };

    const lifelineChips = lifelines.length
      ? lifelines.map((l) => {
          const kind = l.kind || "object";
          return `<div class="actor-chip">
            <span class="actor-icon">${IconLib.svg(kind === "actor" ? "user" : "settings", 14)}</span>
            <span class="actor-name">${escapeHtml(l.name)}</span>
            <span class="actor-role-badge actor-role-secondary">${kindCnMap[kind] || kind}</span>
          </div>`;
        }).join("")
      : `<span style="font-size: 13px; color: var(--color-text-secondary);">未提取到生命线</span>`;

    const sortedMessages = messages.slice().sort((a, b) => (a.order || 0) - (b.order || 0));
    const messageRows = sortedMessages.length
      ? sortedMessages.map((m) => {
          const kind = m.kind || "sync";
          return `<tr>
            <td><code style="font-family: var(--font-mono); font-weight: 600; color: var(--color-primary); font-size: 12px;">${m.order}</code></td>
            <td><code style="font-family: var(--font-mono); font-size: 12px;">${escapeHtml(m.from || m.source_id || "-")}</code></td>
            <td><code style="font-family: var(--font-mono); font-size: 12px;">${escapeHtml(m.to || m.target_id || "-")}</code></td>
            <td style="color: var(--color-text-secondary); font-size: 13px;">${escapeHtml(m.label || "—")}</td>
            <td><span class="badge badge-secondary" style="font-size: 11px;">${msgKindCnMap[kind] || kind}</span></td>
          </tr>`;
        }).join("")
      : `<tr><td colspan="5" style="text-align: center; color: var(--color-text-secondary); padding: 24px 0;">未提取到消息</td></tr>`;

    const fragmentRows = fragments.length
      ? fragments.map((f) => `<tr>
          <td><span class="badge badge-info" style="font-size: 11px;">${escapeHtml(f.kind || "alt")}</span></td>
          <td style="color: var(--color-text-secondary); font-size: 13px;">${escapeHtml(f.condition || "—")}</td>
          <td><code style="font-family: var(--font-mono); font-size: 12px;">#${f.start_order} — #${f.end_order}</code></td>
        </tr>`).join("")
      : `<tr><td colspan="3" style="text-align: center; color: var(--color-text-secondary); padding: 24px 0;">无组合片段</td></tr>`;

    return `
      <div>
        <div class="elements-section-header">
          <span><i data-icon="users"></i> 生命线 (Lifelines)</span>
          <span style="font-size: 11px; color: var(--color-text-secondary);">共 ${lifelines.length} 条</span>
        </div>
        <div class="actors-chip-group">${lifelineChips}</div>
      </div>
      <div>
        <div class="elements-section-header">
          <span><i data-icon="package"></i> 消息时序清单 (Messages)</span>
          <span style="font-size: 11px; color: var(--color-text-secondary);">共 ${messages.length} 条消息</span>
        </div>
        <div style="overflow-x: auto;">
          <table class="usecase-element-table">
            <thead><tr><th style="width: 60px;">顺序</th><th style="width: 150px;">发送方</th><th style="width: 150px;">接收方</th><th>消息内容</th><th style="width: 90px;">类型</th></tr></thead>
            <tbody>${messageRows}</tbody>
          </table>
        </div>
      </div>
      <div>
        <div class="elements-section-header">
          <span><i data-icon="link"></i> 组合片段 (Fragments)</span>
          <span style="font-size: 11px; color: var(--color-text-secondary);">共 ${fragments.length} 个片段</span>
        </div>
        <div style="overflow-x: auto;">
          <table class="usecase-element-table">
            <thead><tr><th style="width: 90px;">片段类型</th><th>监护条件</th><th style="width: 150px;">消息区间</th></tr></thead>
            <tbody>${fragmentRows}</tbody>
          </table>
        </div>
      </div>`;
  }

  // 部署图要素清单：节点 + 构件（含宿主）+ 部署/通信关系
  function buildDeploymentElements(model) {
    const nodes = model.nodes || [];
    const artifacts = model.artifacts || [];
    const associations = model.associations || [];
    const assocCnMap = { communication: "通信", dependency: "依赖", association: "关联" };

    const nodeRows = nodes.length
      ? nodes.map((n) => `<tr>
          <td style="font-weight: 600; color: var(--color-text);">${escapeHtml(n.name || "-")}</td>
          <td><span class="badge ${n.kind === "device" ? "badge-info" : "badge-secondary"}" style="font-size: 11px;">${n.kind === "device" ? "物理设备" : "执行环境"}</span></td>
          <td>${n.stereotype ? `<code style="font-family: var(--font-mono); font-size: 12px; color: var(--color-primary);">&lt;&lt;${escapeHtml(n.stereotype)}&gt;&gt;</code>` : "—"}</td>
          <td style="color: var(--color-text-secondary); font-size: 13px;">${escapeHtml(n.spec || "—")}</td>
        </tr>`).join("")
      : `<tr><td colspan="4" style="text-align: center; color: var(--color-text-secondary); padding: 24px 0;">未提取到部署节点</td></tr>`;

    const artifactRows = artifacts.length
      ? artifacts.map((a) => `<tr>
          <td style="font-weight: 600; color: var(--color-text);">${escapeHtml(a.name || "-")}</td>
          <td><code style="font-family: var(--font-mono); font-size: 12px;">${escapeHtml(a.deployed_on || "未指定宿主")}</code></td>
        </tr>`).join("")
      : `<tr><td colspan="2" style="text-align: center; color: var(--color-text-secondary); padding: 24px 0;">未声明部署构件</td></tr>`;

    const assocRows = associations.length
      ? associations.map((r) => `<tr>
          <td><code style="font-family: var(--font-mono); font-size: 12px;">${escapeHtml(r.from || r.source_id || "-")}</code></td>
          <td><code style="font-family: var(--font-mono); font-size: 12px;">${escapeHtml(r.to || r.target_id || "-")}</code></td>
          <td><span class="badge badge-secondary" style="font-size: 11px;">${assocCnMap[r.kind] || r.kind || "-"}</span></td>
        </tr>`).join("")
      : `<tr><td colspan="3" style="text-align: center; color: var(--color-text-secondary); padding: 24px 0;">未声明部署关系</td></tr>`;

    return `
      <div>
        <div class="elements-section-header">
          <span><i data-icon="monitor"></i> 部署节点 (Nodes)</span>
          <span style="font-size: 11px; color: var(--color-text-secondary);">共 ${nodes.length} 个节点</span>
        </div>
        <div style="overflow-x: auto;">
          <table class="usecase-element-table">
            <thead><tr><th style="width: 170px;">节点名称</th><th style="width: 110px;">类型</th><th style="width: 140px;">构造型</th><th>规格说明</th></tr></thead>
            <tbody>${nodeRows}</tbody>
          </table>
        </div>
      </div>
      <div>
        <div class="elements-section-header">
          <span><i data-icon="package"></i> 部署构件 (Artifacts)</span>
          <span style="font-size: 11px; color: var(--color-text-secondary);">共 ${artifacts.length} 个构件</span>
        </div>
        <div style="overflow-x: auto;">
          <table class="usecase-element-table">
            <thead><tr><th style="width: 200px;">构件名称</th><th>所属节点</th></tr></thead>
            <tbody>${artifactRows}</tbody>
          </table>
        </div>
      </div>
      <div>
        <div class="elements-section-header">
          <span><i data-icon="link"></i> 部署 / 通信关系 (Associations)</span>
          <span style="font-size: 11px; color: var(--color-text-secondary);">共 ${associations.length} 条</span>
        </div>
        <div style="overflow-x: auto;">
          <table class="usecase-element-table">
            <thead><tr><th style="width: 170px;">源 (from)</th><th style="width: 170px;">目标 (to)</th><th>关系类型</th></tr></thead>
            <tbody>${assocRows}</tbody>
          </table>
        </div>
      </div>`;
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
      const sys = currentModelData?.system || currentModelData?.module || currentModelData?.object || "软件工程业务系统";
      const topic = `${sys}设计与建模`;
      try {
        localStorage.setItem("pending_package_topic", topic);
        window.location.href = "/resources.html?tab=package";
      } catch (e) {
        window.location.href = "/resources.html?tab=package";
      }
    });
  }

  // 8.6.4 画布渲染：PlantUML 引擎 → img；draw.io 引擎 → 官方 viewer 渲染 XML
  // draw.io XML 是异步 fetch 拿到的，因此下载按钮必须在回填后再次同步，
  // 否则首次渲染时 xmlSrc 仍为空，按钮会被隐藏且再也不会恢复。
  function refreshDrawioDownloadBtn(xmlSrc, nameHint) {
    if (!downloadPumlBtn || workspaceMode !== "drawio") return;
    if (!xmlSrc) {
      downloadPumlBtn.style.display = "none";
      return;
    }
    const blob = new Blob([xmlSrc], { type: "application/xml;charset=utf-8" });
    downloadPumlBtn.href = URL.createObjectURL(blob);
    downloadPumlBtn.download = `${nameHint || "uml"}_${Date.now()}.xml`;
    downloadPumlBtn.textContent = "下载 .xml";
    downloadPumlBtn.style.display = "inline-flex";
  }

  function htmlEscapeAttr(text) {
    return String(text).replace(/&/g, "&amp;").replace(/'/g, "&#39;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function renderDrawioCanvas() {
    if (!drawioViewerEl) return;
    const xml = window.__lastDrawioSrc || "";
    if (!xml) return;
    drawioViewerEl.innerHTML =
      '<div class="mxgraph" style="max-width:100%;background:#ffffff;" data-mxgraph=\'' +
      htmlEscapeAttr(JSON.stringify({ xml: xml, toolbar: "zoom", "page-visible": true })) +
      "'></div>";
    if (window.GraphViewer && window.GraphViewer.processElements) {
      window.GraphViewer.processElements();
    }
  }

  function showCanvasForMode() {
    const img = document.getElementById("uml-image");
    const hasXml = (window.__lastDrawioSrc || "").length > 0;
    const isDrawio = workspaceMode === "drawio" && hasXml;
    if (img) img.style.display = isDrawio ? "none" : "inline-block";
    if (drawioViewerEl) drawioViewerEl.style.display = isDrawio ? "block" : "none";
    if (isDrawio) renderDrawioCanvas();
  }

  // 8.6.5 绘图引擎 → 工作区/导出联动（引擎决定源码类型与下载文件）
  if (engineSelect) {
    engineSelect.addEventListener("change", () => {
      setWorkspaceMode(engineSelect.value === "drawio" ? "drawio" : "plantuml");
    });
  }

  function setWorkspaceMode(mode) {
    workspaceMode = mode;
    const isDrawio = mode === "drawio";
    if (plantumlCode) {
      plantumlCode.textContent = isDrawio ? (drawioSrcCurrent || "// 暂无 draw.io 源码，请先生成模型") : (originalPumlSource || plantumlCode.textContent);
    }
    if (plantumlEditor && plantumlEditor.style.display === "block") {
      plantumlEditor.value = plantumlCode ? plantumlCode.textContent : "";
    }
    if (downloadPumlBtn) {
      downloadPumlBtn.textContent = isDrawio ? "下载 .xml" : "下载 .puml";
      if (isDrawio) refreshDrawioDownloadBtn(drawioSrcCurrent);
    }
    if (reRenderPumlBtn) {
      reRenderPumlBtn.innerHTML = isDrawio
        ? "应用到导出"
        : IconLib.svg("refresh-cw", 14) + " 立即重绘当前代码";
    }
    showCanvasForMode();
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
        toggleEditorBtn.innerHTML = IconLib.svg("pencil", 14) + " 开启在线编辑";
      } else {
        plantumlEditor.value = plantumlCode.textContent || "";
        plantumlEditor.style.display = "block";
        plantumlCode.style.display = "none";
        if (reRenderPumlBtn) reRenderPumlBtn.style.display = "inline-flex";
        if (resetPumlBtn) resetPumlBtn.style.display = "inline-flex";
        toggleEditorBtn.innerHTML = IconLib.svg("eye", 14) + " 退出编辑视图";
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
        showError("源码不能为空");
        return;
      }

      if (workspaceMode === "drawio") {
        // draw.io 模式：编辑后的 XML 直接应用到导出（无服务端位图重绘）
        drawioSrcCurrent = editedCode;
        window.__lastDrawioSrc = editedCode;
        window.__lastDrawioEdited = true;
        plantumlCode.textContent = editedCode;
        if (downloadDrawioBtn) {
          const blob = new Blob([editedCode], { type: "application/xml;charset=utf-8" });
          downloadDrawioBtn.href = URL.createObjectURL(blob);
          downloadDrawioBtn.download = `${(currentModelData && currentModelData.type) || "model"}_${Date.now()}.xml`;
          downloadDrawioBtn.style.display = "inline-flex";
        }
        appendRefactorLog("success", "draw.io 源码已更新，点击「下载 .xml」导出编辑后的文件。");
        return;
      }

      // PlantUML 模式：三图型统一走 /v1/uml/render 在线重绘
      plantumlCode.textContent = editedCode;
      reRenderPumlBtn.disabled = true;
      reRenderPumlBtn.textContent = "重绘中…";
      hideError();
      const dtype = (currentModelData && currentModelData.type) || "usecase";
      try {
        const res = await apiPost(
          "/v1/uml/render",
          { plantuml: editedCode, diagram_type: dtype, format: "png" },
          { timeoutMs: 180000 }
        );
        if (res && res.status === "rendered" && res.download_url) {
          const img = document.getElementById("uml-image");
          if (img) {
            img.src = res.download_url;
            img.style.display = "inline-block";
          }
          const srcOnly = document.getElementById("uml-source-fallback");
          if (srcOnly) srcOnly.style.display = "none";
          appendRefactorLog ? null : null;
        } else {
          showError((res && res.reason) || "重绘失败（已降级为源码展示）");
        }
      } catch (err) {
        showError("重绘失败：" + (err.message || "服务异常"));
      } finally {
        reRenderPumlBtn.disabled = false;
        reRenderPumlBtn.innerHTML =
          workspaceMode === "drawio"
            ? "应用到导出"
            : IconLib.svg("refresh-cw", 14) + " 立即重绘当前代码";
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
          <div style="font-weight: 600; color: var(--color-text); margin-bottom: 4px; display: flex; align-items: center; gap: 6px;">
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
        <div class="refactor-result-card" style="border-color: var(--color-border); background: var(--brand-50);">
          <div style="font-weight: 600; color: var(--color-text); margin-bottom: 3px; display: flex; align-items: center; gap: 6px;">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#0284c7" stroke-width="2">
              <polyline points="1 4 1 10 7 10"></polyline>
              <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path>
            </svg>
            版本已回滚
          </div>
          <div style="color: var(--color-text-secondary);">${escapeHtml(text)}</div>
        </div>
      `;
    } else {
      entryDiv.innerHTML = `
        <div class="refactor-result-card" style="border-color: var(--color-error-border); background: var(--color-error-light);">
          <div style="font-weight: 600; color: var(--color-error); margin-bottom: 3px;">重构未完成</div>
          <div style="color: var(--color-error-strong);">${escapeHtml(text)}</div>
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

      const res = await apiPost("/v1/uml/chat-adjust", payload, { timeoutMs: 260000 });
      if (res && res.success) {
        appendRefactorLog("success", res.reply || "已完成模型重构演进。", res.diff_summary);

        // 更新并重绘全界面视图（diagram_type 跟随修正后模型，不写死用例图）
        const updatedData = {
          diagram_type: (res.model && res.model.type) || (currentModelData && currentModelData.type) || "usecase",
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
        diagram_type: (previousUmlState.model && previousUmlState.model.type) || "usecase",
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
