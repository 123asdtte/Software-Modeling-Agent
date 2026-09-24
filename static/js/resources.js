/**
 * 课件、教案与实训工单交互逻辑（js/resources.js）
 * 扩展功能：教学三件套（PPT、教案、实训工单）、幻灯片全屏放映演示、时间平衡器与本地草稿箱
 */

document.addEventListener("DOMContentLoaded", () => {
  // ===================== 1. 基础状态与 Tab 切换 =====================
  const tabBtnPackage = document.getElementById("tab-btn-package");
  const tabBtnPpt = document.getElementById("tab-btn-ppt");
  const tabBtnLesson = document.getElementById("tab-btn-lesson");
  const tabBtnTasksheet = document.getElementById("tab-btn-tasksheet");

  const panelPackage = document.getElementById("panel-package");
  const panelPpt = document.getElementById("panel-ppt");
  const panelLesson = document.getElementById("panel-lesson");
  const panelTasksheet = document.getElementById("panel-tasksheet");

  const errorBar = document.getElementById("resources-error-bar");
  const skeletonBox = document.getElementById("resources-skeleton-box");
  const skeletonStatusText = document.getElementById("skeleton-status-text");

  let currentPackageData = null;
  let currentPptData = null;
  let currentLessonData = null;
  let currentTasksheetData = null;

  function switchTab(target) {
    hideError();
    if (tabBtnPackage) tabBtnPackage.classList.remove("active");
    tabBtnPpt.classList.remove("active");
    tabBtnLesson.classList.remove("active");
    tabBtnTasksheet.classList.remove("active");

    if (panelPackage) panelPackage.style.display = "none";
    panelPpt.style.display = "none";
    panelLesson.style.display = "none";
    panelTasksheet.style.display = "none";

    if (target === "ppt") {
      tabBtnPpt.classList.add("active");
      panelPpt.style.display = "block";
    } else if (target === "lesson") {
      tabBtnLesson.classList.add("active");
      panelLesson.style.display = "block";
    } else if (target === "tasksheet") {
      tabBtnTasksheet.classList.add("active");
      panelTasksheet.style.display = "block";
    } else {
      if (tabBtnPackage) tabBtnPackage.classList.add("active");
      if (panelPackage) panelPackage.style.display = "block";
    }
  }

  if (tabBtnPackage) tabBtnPackage.addEventListener("click", () => switchTab("package"));
  tabBtnPpt.addEventListener("click", () => switchTab("ppt"));
  tabBtnLesson.addEventListener("click", () => switchTab("lesson"));
  tabBtnTasksheet.addEventListener("click", () => switchTab("tasksheet"));

  // 支持 URL 参数 ?tab=package|ppt|lesson|tasksheet
  const urlParams = new URLSearchParams(window.location.search);
  const initialTab = urlParams.get("tab");
  if (initialTab === "ppt") {
    switchTab("ppt");
  } else if (initialTab === "lesson") {
    switchTab("lesson");
  } else if (initialTab === "tasksheet") {
    switchTab("tasksheet");
  } else {
    switchTab("package");
  }

  // 跨页联动：检测是否从 UML 建模页带入了全案课题
  try {
    const pendingPkgTopic = localStorage.getItem("pending_package_topic");
    if (pendingPkgTopic) {
      setTimeout(() => {
        const pkgInput = document.getElementById("pkg-topic");
        if (pkgInput) {
          pkgInput.value = pendingPkgTopic;
          pkgInput.dispatchEvent(new Event("input"));
        }
      }, 100);
      localStorage.removeItem("pending_package_topic");
      switchTab("package");
    }
  } catch (e) {
    console.warn("读取待生成全案课题失败", e);
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

  function showToast(message, isSuccess = true) {
    const toast = document.createElement("div");
    toast.style.position = "fixed";
    toast.style.bottom = "28px";
    toast.style.left = "50%";
    toast.style.transform = "translateX(-50%) translateY(20px)";
    toast.style.backgroundColor = isSuccess ? "rgba(24, 24, 27, 0.9)" : "rgba(220, 38, 38, 0.9)";
    toast.style.color = "#ffffff";
    toast.style.padding = "8px 18px";
    toast.style.borderRadius = "20px";
    toast.style.fontSize = "13px";
    toast.style.boxShadow = "0 8px 20px rgba(0, 0, 0, 0.2)";
    toast.style.zIndex = "1000000";
    toast.style.backdropFilter = "blur(6px)";
    toast.style.opacity = "0";
    toast.style.transition = "all 0.25s cubic-bezier(0.16, 1, 0.3, 1)";
    toast.textContent = message;
    document.body.appendChild(toast);

    requestAnimationFrame(() => {
      toast.style.transform = "translateX(-50%) translateY(0)";
      toast.style.opacity = "1";
    });

    setTimeout(() => {
      toast.style.transform = "translateX(-50%) translateY(10px)";
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 300);
    }, 2200);
  }

  // ===================== 2. 快捷 Chips 与输入清空处理 =====================
  // PPT 快捷 Chips
  document.querySelectorAll(".ppt-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const topic = chip.getAttribute("data-topic");
      const minutes = chip.getAttribute("data-minutes");
      const template = chip.getAttribute("data-template");
      if (topic) pptTopic.value = topic;
      if (minutes) pptMinutes.value = minutes;
      if (template) pptTemplate.value = template;
      pptTopic.dispatchEvent(new Event("input"));
    });
  });

  // 教案快捷 Chips
  document.querySelectorAll(".lesson-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const topic = chip.getAttribute("data-topic");
      const minutes = chip.getAttribute("data-minutes");
      const student = chip.getAttribute("data-student");
      const venue = chip.getAttribute("data-venue");
      if (topic) lessonTopic.value = topic;
      if (minutes) lessonMinutes.value = minutes;
      if (student) lessonStudent.value = student;
      if (venue) lessonVenue.value = venue;
      lessonTopic.dispatchEvent(new Event("input"));
    });
  });

  // 全案快捷 Chips
  document.querySelectorAll(".pkg-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const topic = chip.getAttribute("data-topic");
      const minutes = chip.getAttribute("data-minutes");
      const student = chip.getAttribute("data-student");
      const mode = chip.getAttribute("data-mode");
      if (topic && pkgTopic) pkgTopic.value = topic;
      if (minutes && pkgMinutes) pkgMinutes.value = minutes;
      if (student && pkgStudent) pkgStudent.value = student;
      if (mode && pkgMode) pkgMode.value = mode;
      if (pkgTopic) pkgTopic.dispatchEvent(new Event("input"));
    });
  });

  // 工单快捷 Chips
  document.querySelectorAll(".tasksheet-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const topic = chip.getAttribute("data-topic");
      const minutes = chip.getAttribute("data-minutes");
      const diff = chip.getAttribute("data-diff");
      const mode = chip.getAttribute("data-mode");
      if (topic) tasksheetTopic.value = topic;
      if (minutes) tasksheetMinutes.value = minutes;
      if (diff) tasksheetDifficulty.value = diff;
      if (mode) tasksheetMode.value = mode;
      tasksheetTopic.dispatchEvent(new Event("input"));
    });
  });

  // ===================== 2.5 TAB 0: 教学全案三件套联产与调度 =====================
  const pkgTopic = document.getElementById("pkg-topic");
  const pkgTopicClear = document.getElementById("pkg-topic-clear");
  const pkgMinutes = document.getElementById("pkg-minutes");
  const pkgMode = document.getElementById("pkg-mode");
  const pkgStudent = document.getElementById("pkg-student");
  const btnGeneratePackage = document.getElementById("btn-generate-package");

  const packageResultSection = document.getElementById("package-result-section");
  const pkgResultCourseTitle = document.getElementById("pkg-result-course-title");
  const pkgPptPagesBadge = document.getElementById("pkg-ppt-pages-badge");
  const pkgPptDesc = document.getElementById("pkg-ppt-desc");
  const pkgDownloadPptBtn = document.getElementById("pkg-download-ppt-btn");
  const btnSwitchToPpt = document.getElementById("btn-switch-to-ppt");

  const pkgLessonMinsBadge = document.getElementById("pkg-lesson-mins-badge");
  const pkgLessonDesc = document.getElementById("pkg-lesson-desc");
  const pkgDownloadLessonBtn = document.getElementById("pkg-download-lesson-btn");
  const btnSwitchToLesson = document.getElementById("btn-switch-to-lesson");

  const pkgTaskIdBadge = document.getElementById("pkg-task-id-badge");
  const pkgTasksheetDesc = document.getElementById("pkg-tasksheet-desc");
  const pkgDownloadTasksheetBtn = document.getElementById("pkg-download-tasksheet-btn");
  const btnSwitchToTasksheet = document.getElementById("btn-switch-to-tasksheet");

  const pkgPlantumlCodeBlock = document.getElementById("pkg-plantuml-code-block");
  const pkgBtnCopyPlantuml = document.getElementById("pkg-btn-copy-plantuml");
  const pkgBtnLaunchUmlWorkbench = document.getElementById("pkg-btn-launch-uml-workbench");

  const btnSavePackageDraft = document.getElementById("btn-save-package-draft");
  const btnDownloadAllPackage = document.getElementById("btn-download-all-package");

  if (pkgTopic && pkgTopicClear) {
    pkgTopic.addEventListener("input", () => {
      const val = pkgTopic.value.trim();
      pkgTopicClear.style.display = val ? "block" : "none";
    });

    pkgTopicClear.addEventListener("click", () => {
      pkgTopic.value = "";
      pkgTopicClear.style.display = "none";
      pkgTopic.focus();
    });

    pkgTopic.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        if (btnGeneratePackage) btnGeneratePackage.click();
      }
    });
  }

  function triggerFileDownload(url, filename) {
    const a = document.createElement("a");
    a.href = url;
    if (filename) a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  if (btnGeneratePackage) {
    btnGeneratePackage.addEventListener("click", async () => {
      const topic = pkgTopic ? pkgTopic.value.trim() : "";
      const minutes = pkgMinutes ? parseInt(pkgMinutes.value, 10) || 90 : 90;
      const mode = pkgMode ? pkgMode.value : "pair";
      const target_student = pkgStudent ? pkgStudent.value : "junior";

      if (!topic || topic.length < 2 || topic.length > 100) {
        showError("请输入有效的课程课题名称（2~100字），例如：校园二手闲置物品交易系统用例建模");
        if (pkgTopic) pkgTopic.focus();
        return;
      }

      hideError();
      if (packageResultSection) packageResultSection.style.display = "none";
      skeletonStatusText.textContent = "AI 教学智能体正在深度协同构建全套教学资源（课件大纲·规范教案·实训工单·PlantUML模型）…（约需 10~25 秒）";
      skeletonBox.style.display = "block";
      btnGeneratePackage.disabled = true;
      btnGeneratePackage.textContent = "正在协同构建全套成果…";

      try {
        const data = await apiPost(
          "/v1/package",
          { topic, minutes, mode, target_student, template: "integrated", venue: "lab" },
          { timeoutMs: 180000 }
        );
        currentPackageData = data;
        currentPptData = data.ppt;
        currentLessonData = data.lesson;
        currentTasksheetData = data.tasksheet;
        renderPackageResults(data);
        showToast(`${IconLib.svg("party-popper", 14)} 教学全案三件套联产成功！全套教学文件已生成完毕。`);
      } catch (err) {
        showError(err.message || "全案联产服务响应超时或异常，请稍后重试");
      } finally {
        skeletonBox.style.display = "none";
        btnGeneratePackage.disabled = false;
        btnGeneratePackage.innerHTML = `${IconLib.svg("rocket", 14)} 一键联产教学全案（生成级别）`;
      }
    });
  }

  function renderPackageResults(data) {
    if (!packageResultSection) return;
    packageResultSection.style.display = "block";
    packageResultSection.scrollIntoView({ behavior: "smooth", block: "start" });

    if (pkgResultCourseTitle) {
      pkgResultCourseTitle.textContent = `${data.topic} · 理实一体化专业教学全案`;
    }

    // PPT
    if (data.ppt) {
      const pageCount = (data.ppt.pages || []).length || 5;
      if (pkgPptPagesBadge) pkgPptPagesBadge.textContent = `${pageCount} 页幻灯片`;
      if (pkgDownloadPptBtn && data.ppt.download_url) {
        pkgDownloadPptBtn.href = data.ppt.download_url;
      }
    }

    // Lesson Plan
    if (data.lesson) {
      const mins = data.lesson.lesson_plan?.total_minutes || 90;
      if (pkgLessonMinsBadge) pkgLessonMinsBadge.textContent = `${mins} 分钟教案`;
      if (pkgDownloadLessonBtn && data.lesson.download_url) {
        pkgDownloadLessonBtn.href = data.lesson.download_url;
      }
    }

    // Tasksheet
    if (data.tasksheet) {
      const taskId = data.tasksheet.tasksheet?.task_id || "WS-2026-SE";
      if (pkgTaskIdBadge) pkgTaskIdBadge.textContent = taskId;
      if (pkgDownloadTasksheetBtn && data.tasksheet.download_url) {
        pkgDownloadTasksheetBtn.href = data.tasksheet.download_url;
      }
    }

    // PlantUML
    if (pkgPlantumlCodeBlock) {
      pkgPlantumlCodeBlock.textContent = data.plantuml || "";
    }
  }

  // 快捷切换与联通事件
  if (btnSwitchToPpt) {
    btnSwitchToPpt.addEventListener("click", () => {
      switchTab("ppt");
      if (currentPptData) {
        renderPptResults(currentPptData);
      }
    });
  }

  if (btnSwitchToLesson) {
    btnSwitchToLesson.addEventListener("click", () => {
      switchTab("lesson");
      if (currentLessonData) {
        renderLessonResults(currentLessonData);
      }
    });
  }

  if (btnSwitchToTasksheet) {
    btnSwitchToTasksheet.addEventListener("click", () => {
      switchTab("tasksheet");
      if (currentTasksheetData) {
        renderTasksheetResults(currentTasksheetData);
      }
    });
  }

  // 复制 PlantUML 源码
  if (pkgBtnCopyPlantuml) {
    pkgBtnCopyPlantuml.addEventListener("click", () => {
      const code = pkgPlantumlCodeBlock ? pkgPlantumlCodeBlock.textContent : "";
      if (!code) return;
      navigator.clipboard.writeText(code).then(() => {
        showToast("标准参考模型 PlantUML 源码已复制！");
      });
    });
  }

  // 跨页跳转至 UML 建模工作台质检
  if (pkgBtnLaunchUmlWorkbench) {
    pkgBtnLaunchUmlWorkbench.addEventListener("click", () => {
      if (!currentPackageData) return;
      const topic = currentPackageData.topic || "软件业务需求建模";
      const ts = currentPackageData.tasksheet?.tasksheet;
      const scenario = ts?.scenario || "";
      const reqText = `【实训全案建模需求】\n课题：${topic}\n情境背景：${scenario}\n请严格按照动宾用例规范与系统边界框定，抽取外部参与者并完成模型质检。`;
      try {
        localStorage.setItem("pending_uml_requirement", reqText);
        showToast("正在载入 UML 建模工作台并启动智能体质检…");
        setTimeout(() => {
          window.location.href = "/uml.html";
        }, 300);
      } catch (e) {
        window.location.href = "/uml.html";
      }
    });
  }

  // 保存全案草稿
  if (btnSavePackageDraft) {
    btnSavePackageDraft.addEventListener("click", () => {
      if (!currentPackageData) return;
      saveResourceDraft("package", `[教学全案] ${currentPackageData.topic}`, currentPackageData);
      showToast("整套教学全案已安全存入本地草稿箱！");
    });
  }

  // 批量导出教学全案文件
  if (btnDownloadAllPackage) {
    btnDownloadAllPackage.addEventListener("click", () => {
      if (!currentPackageData) return;
      const topic = currentPackageData.topic || "全案";
      showToast("正在批量导出全案三件套文件（Word 教案 + Word 工单 + 离线课件）…");

      if (currentPackageData.lesson?.download_url) {
        setTimeout(() => triggerFileDownload(currentPackageData.lesson.download_url, `${topic}-规范教案.doc`), 100);
      }
      if (currentPackageData.tasksheet?.download_url) {
        setTimeout(() => triggerFileDownload(currentPackageData.tasksheet.download_url, `${topic}-实训工单.doc`), 650);
      }
      if (currentPackageData.ppt?.download_url) {
        setTimeout(() => triggerFileDownload(currentPackageData.ppt.download_url, `${topic}-离线课件.html`), 1200);
      }
    });
  }

  // ===================== 3. TAB 1: PPT 课件生成与交互 =====================
  const pptTopic = document.getElementById("ppt-topic");
  const pptMinutes = document.getElementById("ppt-minutes");
  const pptTemplate = document.getElementById("ppt-template");
  const generatePptBtn = document.getElementById("generate-ppt-btn");
  const pptTopicError = document.getElementById("ppt-topic-error");
  const pptTopicClear = document.getElementById("ppt-topic-clear");

  const pptResultSection = document.getElementById("ppt-result-section");
  const pptResultTitle = document.getElementById("ppt-result-title");
  const pptPagesCountBadge = document.getElementById("ppt-pages-count-badge");
  const pptTemplateBadge = document.getElementById("ppt-template-badge");
  const pptMetaSubtitle = document.getElementById("ppt-meta-subtitle");
  const pptDownloadBtn = document.getElementById("ppt-download-btn");
  const pptPresentBtn = document.getElementById("ppt-present-btn");
  const pptExportHtmlBtn = document.getElementById("ppt-export-html-btn");
  const pptCopyMarkdownBtn = document.getElementById("ppt-copy-markdown-btn");
  const pptSaveDraftBtn = document.getElementById("ppt-save-draft-btn");
  const pptOutlineContainer = document.getElementById("ppt-outline-container");
  const pptPagesGrid = document.getElementById("ppt-pages-grid");

  pptTopic.addEventListener("input", () => {
    const val = pptTopic.value.trim();
    pptTopicClear.style.display = val ? "block" : "none";
    if (val.length >= 2) {
      pptTopicError.style.display = "none";
      pptTopic.classList.remove("error");
    }
  });

  pptTopicClear.addEventListener("click", () => {
    pptTopic.value = "";
    pptTopicClear.style.display = "none";
    pptTopic.focus();
  });

  // 键盘快捷键支持 Ctrl+Enter
  pptTopic.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      generatePptBtn.click();
    }
  });

  generatePptBtn.addEventListener("click", async () => {
    const topic = pptTopic.value.trim();
    const minutes = parseInt(pptMinutes.value, 10) || 90;
    const template = pptTemplate.value;

    if (!topic || topic.length < 2 || topic.length > 100) {
      pptTopicError.style.display = "block";
      pptTopic.classList.add("error");
      pptTopic.focus();
      return;
    }

    hideError();
    pptResultSection.style.display = "none";
    skeletonStatusText.textContent = "AI 教学智能体正在梳理知识递进架构与 PPT 页面内容…";
    skeletonBox.style.display = "block";
    generatePptBtn.disabled = true;
    generatePptBtn.textContent = "生成中…（约 15 秒）";

    try {
      const data = await apiPost("/v1/ppt", { topic, minutes, template }, { timeoutMs: 180000 });
      currentPptData = data;
      renderPptResults(data);
    } catch (err) {
      showError(err.message || "PPT 生成服务异常，请稍后重试");
    } finally {
      skeletonBox.style.display = "none";
      generatePptBtn.disabled = false;
      generatePptBtn.textContent = "生成 PPT 课件方案";
    }
  });

  function renderPptResults(data) {
    pptResultSection.style.display = "block";
    pptResultSection.scrollIntoView({ behavior: "smooth", block: "start" });

    // 1. 标题与参数徽章
    pptResultTitle.textContent = data.title || "课件生成大纲";
    const pages = data.pages || [];
    pptPagesCountBadge.textContent = `共 ${data.total_pages || pages.length} 页`;

    const templateNames = {
      integrated: "理实一体化",
      theory: "理论系统规约",
      competition: "技能大赛冲刺",
      project: "全生命周期工作坊",
    };
    pptTemplateBadge.textContent = templateNames[data.template] || "标准课件";
    pptMetaSubtitle.textContent = (data.outline && data.outline.subtitle) || "高职专业课程一体化教学课件";

    // 2. 下载链接
    if (data.download_url) {
      pptDownloadBtn.href = data.download_url;
      pptDownloadBtn.download = `${data.title || "course"}.pptx`;
      pptDownloadBtn.style.display = "inline-flex";
    } else {
      pptDownloadBtn.style.display = "none";
    }

    // 3. 课程大纲结构
    const outline = data.outline || {};
    const sections = outline.sections || [];
    pptOutlineContainer.innerHTML = "";
    if (sections.length === 0) {
      pptOutlineContainer.innerHTML = `<div style="color: var(--color-text-secondary); font-size: 13px;">无大纲章节数据</div>`;
    } else {
      sections.forEach((sec, idx) => {
        const item = document.createElement("div");
        item.className = "outline-section-item";
        item.innerHTML = `
          <div class="outline-section-header">
            <span class="outline-section-name">${idx + 1}. ${escapeHtml(sec.name || "章节")}</span>
            <span class="badge badge-info">${escapeHtml(sec.page_count || 1)} 页</span>
          </div>
          ${
            sec.points && sec.points.length
              ? `<ul class="bullet-list" style="margin-bottom: 0;">
                ${sec.points.map((pt) => `<li>${escapeHtml(pt)}</li>`).join("")}
              </ul>`
              : ""
          }
        `;
        pptOutlineContainer.appendChild(item);
      });
    }

    // 4. 幻灯片逐页卡片渲染
    pptPagesGrid.innerHTML = "";
    pages.forEach((pg, index) => {
      const card = document.createElement("div");
      card.className = "ppt-page-card";
      card.innerHTML = `
        <div>
          <div class="ppt-page-header">
            <h4 class="ppt-page-title">${index + 1}. ${escapeHtml(pg.title || "页面")}</h4>
            <span class="badge badge-primary">${escapeHtml(pg.minutes || 5)} 分钟</span>
          </div>
          <ul class="bullet-list">
            ${(pg.bullets || []).map((b) => `<li>${escapeHtml(b)}</li>`).join("")}
          </ul>
        </div>
        <div>
          ${
            pg.note
              ? `
            <details class="page-note-details">
              <summary>${IconLib.svg("lightbulb", 14)} 讲授指导要点</summary>
              <p style="margin-top: 4px;">${escapeHtml(pg.note)}</p>
            </details>
          `
              : ""
          }
          <div class="ppt-page-card-footer">
            <span style="font-size: 11px; color: var(--color-text-muted);">幻灯片 P${index + 1}</span>
            <button type="button" class="btn btn-secondary btn-play-page" data-page-index="${index}" style="padding: 2px 8px; font-size: 11px;">
              ▶ 从本页放映
            </button>
          </div>
        </div>
      `;
      pptPagesGrid.appendChild(card);
    });

    // 绑定从指定页进入放映
    document.querySelectorAll(".btn-play-page").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const pageIdx = parseInt(e.currentTarget.getAttribute("data-page-index"), 10) || 0;
        openSlidePresentation(data, pageIdx);
      });
    });
  }

  // 复制大纲 Markdown
  pptCopyMarkdownBtn.addEventListener("click", () => {
    if (!currentPptData) return;
    const text = generatePptMarkdown(currentPptData);
    navigator.clipboard.writeText(text).then(() => {
      showToast("课件大纲 Markdown 已成功复制到剪贴板！");
    });
  });

  // 导出免安装纯静态 HTML 互动幻灯片
  pptExportHtmlBtn.addEventListener("click", () => {
    if (!currentPptData) return;
    const htmlContent = generateStandaloneHtmlSlides(currentPptData);
    const blob = new Blob([htmlContent], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${currentPptData.title || "course"}_presentation.html`;
    a.click();
    URL.revokeObjectURL(url);
    showToast("HTML 独立互动演示课件已导出！");
  });

  // 保存 PPT 至本地草稿箱
  pptSaveDraftBtn.addEventListener("click", () => {
    if (!currentPptData) return;
    saveResourceDraft("ppt", currentPptData.title, currentPptData);
    showToast("课件已存入本地教学资源草稿箱！");
  });

  // 全屏放映入口
  pptPresentBtn.addEventListener("click", () => {
    if (!currentPptData) return;
    openSlidePresentation(currentPptData, 0);
  });

  // ===================== 4. 幻灯片全屏放映演示模式 (Presentation Lightbox) =====================
  const presModal = document.getElementById("ppt-presentation-modal");
  const presCourseTitle = document.getElementById("pres-course-title");
  const presPageCounter = document.getElementById("pres-page-counter");
  const presTimer = document.getElementById("pres-timer");
  const presSlideTitle = document.getElementById("pres-slide-title");
  const presSlideMinutes = document.getElementById("pres-slide-minutes");
  const presSlideBullets = document.getElementById("pres-slide-bullets");
  const presNotesBox = document.getElementById("pres-notes-box");
  const presSlideNoteText = document.getElementById("pres-slide-note-text");
  const presToggleNotesBtn = document.getElementById("pres-toggle-notes-btn");
  const presExitBtn = document.getElementById("pres-exit-btn");
  const presPrevBtn = document.getElementById("pres-prev-btn");
  const presNextBtn = document.getElementById("pres-next-btn");
  const presSelectPage = document.getElementById("pres-select-page");

  let presCurrentIndex = 0;
  let presPages = [];
  let presTimerInterval = null;
  let presSeconds = 0;
  let presShowNotes = true;

  function openSlidePresentation(data, startIndex = 0) {
    presPages = data.pages || [];
    if (presPages.length === 0) {
      showError("当前课件暂无幻灯片分页数据");
      return;
    }

    presCurrentIndex = startIndex >= 0 && startIndex < presPages.length ? startIndex : 0;
    presCourseTitle.textContent = data.title || "教学课件";

    // 填充下拉选项
    presSelectPage.innerHTML = "";
    presPages.forEach((pg, i) => {
      const opt = document.createElement("option");
      opt.value = i;
      opt.textContent = `P${i + 1}: ${pg.title || "幻灯片"}`;
      presSelectPage.appendChild(opt);
    });

    // 开启计时
    clearInterval(presTimerInterval);
    presSeconds = 0;
    presTimer.textContent = "00:00";
    presTimerInterval = setInterval(() => {
      presSeconds++;
      const m = String(Math.floor(presSeconds / 60)).padStart(2, "0");
      const s = String(presSeconds % 60).padStart(2, "0");
      presTimer.textContent = `${m}:${s}`;
    }, 1000);

    presModal.style.display = "flex";
    renderCurrentPresSlide();
  }

  function closeSlidePresentation() {
    presModal.style.display = "none";
    clearInterval(presTimerInterval);
  }

  function renderCurrentPresSlide() {
    const page = presPages[presCurrentIndex];
    if (!page) return;

    presPageCounter.textContent = `${presCurrentIndex + 1} / ${presPages.length}`;
    presSelectPage.value = presCurrentIndex;
    presSlideTitle.textContent = page.title || "幻灯片";
    presSlideMinutes.textContent = `${page.minutes || 5} 分钟`;

    presSlideBullets.innerHTML = "";
    (page.bullets || []).forEach((b) => {
      const li = document.createElement("li");
      li.innerHTML = `<span class="slide-bullet-dot"></span><span>${escapeHtml(b)}</span>`;
      presSlideBullets.appendChild(li);
    });

    if (page.note && presShowNotes) {
      presSlideNoteText.textContent = page.note;
      presNotesBox.style.display = "flex";
    } else {
      presNotesBox.style.display = "none";
    }

    presPrevBtn.disabled = presCurrentIndex <= 0;
    presNextBtn.disabled = presCurrentIndex >= presPages.length - 1;
  }

  presPrevBtn.addEventListener("click", () => {
    if (presCurrentIndex > 0) {
      presCurrentIndex--;
      renderCurrentPresSlide();
    }
  });

  presNextBtn.addEventListener("click", () => {
    if (presCurrentIndex < presPages.length - 1) {
      presCurrentIndex++;
      renderCurrentPresSlide();
    }
  });

  presSelectPage.addEventListener("change", (e) => {
    presCurrentIndex = parseInt(e.target.value, 10) || 0;
    renderCurrentPresSlide();
  });

  presToggleNotesBtn.addEventListener("click", () => {
    presShowNotes = !presShowNotes;
    presToggleNotesBtn.style.color = presShowNotes ? "#e4e4e7" : "#ffffff";
    renderCurrentPresSlide();
  });

  presExitBtn.addEventListener("click", closeSlidePresentation);

  // 键盘快捷键监听
  window.addEventListener("keydown", (e) => {
    if (presModal.style.display === "flex") {
      if (e.key === "Escape") {
        closeSlidePresentation();
      } else if (e.key === "ArrowLeft") {
        presPrevBtn.click();
      } else if (e.key === "ArrowRight" || e.key === " ") {
        e.preventDefault();
        presNextBtn.click();
      }
    }
  });

  // ===================== 5. TAB 2: 高职规范教案生成与交互 =====================
  const lessonTopic = document.getElementById("lesson-topic");
  const lessonMinutes = document.getElementById("lesson-minutes");
  const lessonStudent = document.getElementById("lesson-student");
  const lessonVenue = document.getElementById("lesson-venue");
  const generateLessonBtn = document.getElementById("generate-lesson-btn");
  const lessonTopicError = document.getElementById("lesson-topic-error");
  const lessonTopicClear = document.getElementById("lesson-topic-clear");

  const lessonResultSection = document.getElementById("lesson-result-section");
  const lessonMissingFieldsBar = document.getElementById("lesson-missing-fields-bar");
  const lessonCourseName = document.getElementById("lesson-course-name");
  const lessonContextInfo = document.getElementById("lesson-context-info");
  const lessonDownloadBtn = document.getElementById("lesson-download-btn");
  const lessonPrintBtn = document.getElementById("lesson-print-btn");
  const lessonCopyMdBtn = document.getElementById("lesson-copy-md-btn");
  const lessonSaveDraftBtn = document.getElementById("lesson-save-draft-btn");

  const timeBalanceStatusText = document.getElementById("time-balance-status-text");
  const timeAutoBalanceBtn = document.getElementById("time-auto-balance-btn");
  const segStage1 = document.getElementById("seg-stage-1");
  const segStage2 = document.getElementById("seg-stage-2");
  const segStage3 = document.getElementById("seg-stage-3");
  const segStage4 = document.getElementById("seg-stage-4");
  const valStage1 = document.getElementById("val-stage-1");
  const valStage2 = document.getElementById("val-stage-2");
  const valStage3 = document.getElementById("val-stage-3");
  const valStage4 = document.getElementById("val-stage-4");

  const goalKnowledgeList = document.getElementById("goal-knowledge-list");
  const goalAbilityList = document.getElementById("goal-ability-list");
  const goalLiteracyList = document.getElementById("goal-literacy-list");
  const keyPointsList = document.getElementById("key-points-list");
  const difficultPointsList = document.getElementById("difficult-points-list");
  const flowTbody = document.getElementById("flow-tbody");
  const exercisesList = document.getElementById("exercises-list");
  const homeworkList = document.getElementById("homework-list");
  const lessonReflectionText = document.getElementById("lesson-reflection-text");
  const lessonMarkdownBlock = document.getElementById("lesson-markdown-block");

  lessonTopic.addEventListener("input", () => {
    const val = lessonTopic.value.trim();
    lessonTopicClear.style.display = val ? "block" : "none";
    if (val.length >= 2) {
      lessonTopicError.style.display = "none";
      lessonTopic.classList.remove("error");
    }
  });

  lessonTopicClear.addEventListener("click", () => {
    lessonTopic.value = "";
    lessonTopicClear.style.display = "none";
    lessonTopic.focus();
  });

  generateLessonBtn.addEventListener("click", async () => {
    const topic = lessonTopic.value.trim();
    const minutes = parseInt(lessonMinutes.value, 10) || 45;
    const target_student = lessonStudent.value;
    const venue = lessonVenue.value;

    if (!topic || topic.length < 2 || topic.length > 100) {
      lessonTopicError.style.display = "block";
      lessonTopic.classList.add("error");
      lessonTopic.focus();
      return;
    }

    hideError();
    lessonResultSection.style.display = "none";
    skeletonStatusText.textContent = "AI 教学智能体正在构建高职三维目标与四环节规范教案…";
    skeletonBox.style.display = "block";
    generateLessonBtn.disabled = true;
    generateLessonBtn.textContent = "生成中…（约 15 秒）";

    try {
      const data = await apiPost("/v1/lesson", { topic, minutes, target_student, venue }, { timeoutMs: 180000 });
      currentLessonData = data;
      renderLessonResults(data);
    } catch (err) {
      showError(err.message || "教案生成服务异常，请稍后重试");
    } finally {
      skeletonBox.style.display = "none";
      generateLessonBtn.disabled = false;
      generateLessonBtn.textContent = "生成规范教案";
    }
  });

  function renderLessonResults(data) {
    lessonResultSection.style.display = "block";
    lessonResultSection.scrollIntoView({ behavior: "smooth", block: "start" });

    // 缺失字段提示
    const missing = data.missing_fields || [];
    if (missing.length > 0) {
      lessonMissingFieldsBar.textContent = `以下教学设计字段缺失，建议教师在文档中手动补齐：${missing.join("、")}`;
      lessonMissingFieldsBar.style.display = "flex";
    } else {
      lessonMissingFieldsBar.style.display = "none";
    }

    const lesson = data.lesson || {};
    lessonCourseName.textContent = lesson.course_name || "课程教学设计方案";
    lessonContextInfo.textContent = `课时时长：${lesson.total_minutes || 45} 分钟 | 授课对象：${lesson.target_student || "高职专业学生"} | 教学场所：${lesson.teaching_venue || "一体化机房"}`;

    // 下载链接
    if (data.download_url) {
      lessonDownloadBtn.href = data.download_url;
      lessonDownloadBtn.download = `${lesson.course_name || "lesson"}.docx`;
      lessonDownloadBtn.style.display = "inline-flex";
    } else {
      lessonDownloadBtn.style.display = "none";
    }

    // 1. 教学目标渲染（带行内可编辑属性）
    const goals = lesson.teaching_goals || {};
    renderEditableList(goalKnowledgeList, goals.knowledge);
    renderEditableList(goalAbilityList, goals.ability);
    renderEditableList(goalLiteracyList, goals.literacy);

    // 2. 重难点
    renderEditableList(keyPointsList, lesson.key_points);
    renderEditableList(difficultPointsList, lesson.difficult_points);

    // 3. 教学流程表与时间平衡器
    const flows = lesson.teaching_flow || [];
    renderFlowTable(flows);
    updateLessonTimeBalancer(flows, lesson.total_minutes || 45);

    // 4. 实训练习与作业
    renderEditableList(exercisesList, lesson.class_exercises, "ol");
    renderEditableList(homeworkList, lesson.homework, "ol");

    // 5. 教学反思
    lessonReflectionText.textContent = lesson.teaching_reflection || "暂无教学反思建议";

    // 6. Markdown 文本
    lessonMarkdownBlock.textContent = data.markdown || "";
  }

  function renderFlowTable(flows) {
    flowTbody.innerHTML = "";
    flows.forEach((item, idx) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td style="font-weight: 600;">${escapeHtml(item.stage || "-")}</td>
        <td>
          <input type="number" class="form-input flow-time-input" data-stage-index="${idx}" value="${item.minutes || 0}" min="1" max="180" style="width: 60px; padding: 4px 6px; font-size: 12px; display: inline-block;" /> 分钟
        </td>
        <td contenteditable="true" style="outline: none; border-radius: 4px; padding: 4px;">${escapeHtml(item.teacher_activity || "-")}</td>
        <td contenteditable="true" style="outline: none; border-radius: 4px; padding: 4px;">${escapeHtml(item.student_activity || "-")}</td>
      `;
      flowTbody.appendChild(tr);
    });

    // 监听表格中各环节分钟手动修改
    flowTbody.querySelectorAll(".flow-time-input").forEach((input) => {
      input.addEventListener("change", () => {
        const flows = currentLessonData?.lesson?.teaching_flow || [];
        const idx = parseInt(input.getAttribute("data-stage-index"), 10);
        if (flows[idx]) {
          flows[idx].minutes = parseInt(input.value, 10) || 0;
          updateLessonTimeBalancer(flows, currentLessonData?.lesson?.total_minutes || 45);
        }
      });
    });
  }

  function updateLessonTimeBalancer(flows, targetTotal) {
    const m1 = flows[0]?.minutes || 5;
    const m2 = flows[1]?.minutes || 15;
    const m3 = flows[2]?.minutes || 18;
    const m4 = flows[3]?.minutes || 7;
    const actualSum = m1 + m2 + m3 + m4;

    valStage1.textContent = `${m1}m`;
    valStage2.textContent = `${m2}m`;
    valStage3.textContent = `${m3}m`;
    valStage4.textContent = `${m4}m`;

    const p1 = Math.round((m1 / actualSum) * 100);
    const p2 = Math.round((m2 / actualSum) * 100);
    const p3 = Math.round((m3 / actualSum) * 100);
    const p4 = 100 - p1 - p2 - p3;

    segStage1.style.width = `${p1}%`;
    segStage2.style.width = `${p2}%`;
    segStage3.style.width = `${p3}%`;
    segStage4.style.width = `${p4}%`;

    if (actualSum === targetTotal) {
      timeBalanceStatusText.textContent = `已平衡：合计 ${actualSum} 分钟（与总课时吻合）`;
      timeBalanceStatusText.style.color = "var(--color-success)";
    } else {
      timeBalanceStatusText.textContent = `时序偏差：当前合计 ${actualSum}m / 目标 ${targetTotal}m`;
      timeBalanceStatusText.style.color = "var(--color-warning)";
    }
  }

  // 自动平衡时序
  timeAutoBalanceBtn.addEventListener("click", () => {
    if (!currentLessonData?.lesson) return;
    const total = currentLessonData.lesson.total_minutes || 45;
    const flows = currentLessonData.lesson.teaching_flow || [];
    if (flows.length >= 4) {
      flows[0].minutes = Math.max(3, Math.round(total * 0.12));
      flows[1].minutes = Math.max(8, Math.round(total * 0.33));
      flows[3].minutes = Math.max(3, Math.round(total * 0.15));
      flows[2].minutes = total - flows[0].minutes - flows[1].minutes - flows[3].minutes;
      renderFlowTable(flows);
      updateLessonTimeBalancer(flows, total);
      showToast("已按高职理实一体化标准比例重平衡四环节时间！");
    }
  });

  // 打印教案
  lessonPrintBtn.addEventListener("click", () => {
    window.print();
  });

  // 复制教案 Markdown
  lessonCopyMdBtn.addEventListener("click", () => {
    if (!currentLessonData) return;
    const text = lessonMarkdownBlock.textContent || "";
    navigator.clipboard.writeText(text).then(() => {
      showToast("教案 Markdown 已成功复制到剪贴板！");
    });
  });

  // 保存教案至本地草稿箱
  lessonSaveDraftBtn.addEventListener("click", () => {
    if (!currentLessonData?.lesson) return;
    saveResourceDraft("lesson", currentLessonData.lesson.course_name, currentLessonData);
    showToast("教案设计方案已存入本地草稿箱！");
  });

  function renderEditableList(container, items, tag = "ul") {
    container.innerHTML = "";
    if (!items || items.length === 0) {
      container.innerHTML = `<li style="color: var(--color-text-secondary); list-style: none;">（暂无）</li>`;
      return;
    }
    items.forEach((txt) => {
      const li = document.createElement("li");
      li.textContent = txt;
      li.setAttribute("contenteditable", "true");
      li.style.outline = "none";
      li.style.cursor = "text";
      li.title = "点击可直接编辑修改";
      container.appendChild(li);
    });
  }

  // ===================== 6. TAB 3: 理实一体化实训任务工单生成 (NEW!) =====================
  const tasksheetTopic = document.getElementById("tasksheet-topic");
  const tasksheetMinutes = document.getElementById("tasksheet-minutes");
  const tasksheetDifficulty = document.getElementById("tasksheet-difficulty");
  const tasksheetMode = document.getElementById("tasksheet-mode");
  const generateTasksheetBtn = document.getElementById("generate-tasksheet-btn");
  const tasksheetTopicError = document.getElementById("tasksheet-topic-error");
  const tasksheetTopicClear = document.getElementById("tasksheet-topic-clear");

  const tasksheetResultSection = document.getElementById("tasksheet-result-section");
  const tasksheetCourseName = document.getElementById("tasksheet-course-name");
  const tasksheetIdBadge = document.getElementById("tasksheet-id-badge");
  const tasksheetDownloadBtn = document.getElementById("tasksheet-download-btn");
  const tasksheetPrintBtn = document.getElementById("tasksheet-print-btn");
  const tasksheetCopyMdBtn = document.getElementById("tasksheet-copy-md-btn");
  const tasksheetSaveDraftBtn = document.getElementById("tasksheet-save-draft-btn");

  const metaTaskId = document.getElementById("meta-task-id");
  const metaTaskRole = document.getElementById("meta-task-role");
  const metaTaskMode = document.getElementById("meta-task-mode");
  const metaTaskDiff = document.getElementById("meta-task-diff");

  const tasksheetScenarioContent = document.getElementById("tasksheet-scenario-content");
  const tasksheetDeliverablesContainer = document.getElementById("tasksheet-deliverables-container");
  const tasksheetStepsContainer = document.getElementById("tasksheet-steps-container");
  const rubricTbody = document.getElementById("rubric-tbody");
  const tasksheetPitfallsContainer = document.getElementById("tasksheet-pitfalls-container");
  const tasksheetMarkdownBlock = document.getElementById("tasksheet-markdown-block");

  tasksheetTopic.addEventListener("input", () => {
    const val = tasksheetTopic.value.trim();
    tasksheetTopicClear.style.display = val ? "block" : "none";
    if (val.length >= 2) {
      tasksheetTopicError.style.display = "none";
      tasksheetTopic.classList.remove("error");
    }
  });

  tasksheetTopicClear.addEventListener("click", () => {
    tasksheetTopic.value = "";
    tasksheetTopicClear.style.display = "none";
    tasksheetTopic.focus();
  });

  generateTasksheetBtn.addEventListener("click", async () => {
    const topic = tasksheetTopic.value.trim();
    const minutes = parseInt(tasksheetMinutes.value, 10) || 45;
    const difficulty = tasksheetDifficulty.value;
    const mode = tasksheetMode.value;

    if (!topic || topic.length < 2 || topic.length > 100) {
      tasksheetTopicError.style.display = "block";
      tasksheetTopic.classList.add("error");
      tasksheetTopic.focus();
      return;
    }

    hideError();
    tasksheetResultSection.style.display = "none";
    skeletonStatusText.textContent = "AI 教学智能体正在构建高职实训任务工单与考核评价量规…";
    skeletonBox.style.display = "block";
    generateTasksheetBtn.disabled = true;
    generateTasksheetBtn.textContent = "生成中…（约 15 秒）";

    try {
      const data = await apiPost("/v1/tasksheet", { topic, minutes, difficulty, mode }, { timeoutMs: 180000 });
      currentTasksheetData = data;
      renderTasksheetResults(data);
    } catch (err) {
      showError(err.message || "实训工单生成服务异常，请稍后重试");
    } finally {
      skeletonBox.style.display = "none";
      generateTasksheetBtn.disabled = false;
      generateTasksheetBtn.textContent = "生成实训任务工单";
    }
  });

  function renderTasksheetResults(data) {
    tasksheetResultSection.style.display = "block";
    tasksheetResultSection.scrollIntoView({ behavior: "smooth", block: "start" });

    const ts = data.tasksheet || {};
    tasksheetCourseName.textContent = ts.course_name || "实训任务工单";
    tasksheetIdBadge.textContent = ts.task_id || "WS-2026-SE01";

    if (data.download_url) {
      tasksheetDownloadBtn.href = data.download_url;
      tasksheetDownloadBtn.download = `${ts.task_id || "tasksheet"}.docx`;
      tasksheetDownloadBtn.style.display = "inline-flex";
    } else {
      tasksheetDownloadBtn.style.display = "none";
    }

    // 元数据卡片
    metaTaskId.textContent = ts.task_id || "-";
    metaTaskRole.textContent = ts.occupational_role || "软件建模师";
    metaTaskMode.textContent = ts.training_mode || "双人结对协作";
    metaTaskDiff.textContent = `${ts.difficulty || "进阶"} (${ts.duration_minutes || 45}分钟)`;

    // 1. 任务情景
    tasksheetScenarioContent.textContent = ts.scenario || "-";

    // 2. 成果交付物
    tasksheetDeliverablesContainer.innerHTML = "";
    (ts.deliverables || []).forEach((d) => {
      const card = document.createElement("div");
      card.className = "tasksheet-meta-card";
      card.innerHTML = `
        <div style="font-weight: 700; font-size: 13px; color: var(--color-primary); margin-bottom: 4px;">
          ${escapeHtml(d.name)}
        </div>
        <div style="font-size: 11px; color: var(--color-info); margin-bottom: 4px;">格式：${escapeHtml(d.format)}</div>
        <div style="font-size: 12px; color: var(--color-text-secondary); line-height: 1.4;">${escapeHtml(d.desc)}</div>
      `;
      tasksheetDeliverablesContainer.appendChild(card);
    });

    // 3. 阶梯工序
    tasksheetStepsContainer.innerHTML = "";
    (ts.steps || []).forEach((s) => {
      const stepCard = document.createElement("div");
      stepCard.className = "task-step-card";
      stepCard.innerHTML = `
        <div class="task-step-header">
          <span class="task-step-title">工序 ${s.step_num}：${escapeHtml(s.step_name)}</span>
          <span class="badge badge-info">建议 ${escapeHtml(s.estimated_time)} 分钟</span>
        </div>
        <div style="font-size: 13px; color: var(--color-text); line-height: 1.6;">
          <strong>操作指引：</strong>${escapeHtml(s.guide)}
        </div>
        <div class="task-step-checkpoint">
          <span style="font-weight: 700; color: var(--color-primary);">${IconLib.svg("check", 14)} 关键检验点：</span>
          <span>${escapeHtml(s.checkpoint)}</span>
        </div>
      `;
      tasksheetStepsContainer.appendChild(stepCard);
    });

    // 4. 考核量规
    rubricTbody.innerHTML = "";
    (ts.rubric || []).forEach((r) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td style="font-weight: 600; color: var(--color-text);">${escapeHtml(r.item)}</td>
        <td><span class="badge badge-primary">${escapeHtml(r.weight)}</span></td>
        <td style="color: var(--color-text-secondary); line-height: 1.5;">${escapeHtml(r.standard)}</td>
      `;
      rubricTbody.appendChild(tr);
    });

    // 5. 翻车锦囊
    tasksheetPitfallsContainer.innerHTML = "";
    (ts.pitfalls || []).forEach((p) => {
      const pit = document.createElement("div");
      pit.className = "pitfall-card";
      pit.innerHTML = `
        <div class="pitfall-title">
          <span>${IconLib.svg("circle-x", 14)}</span>
          <span>${escapeHtml(p.trap)}</span>
        </div>
        <div class="pitfall-solution">
          <strong>${IconLib.svg("lightbulb", 14)} 避坑纠错：</strong>${escapeHtml(p.solution)}
        </div>
      `;
      tasksheetPitfallsContainer.appendChild(pit);
    });

    // 6. 教师备课标准模型与 PlantUML 源码
    const tsPlantumlBlock = document.getElementById("tasksheet-plantuml-block");
    if (tsPlantumlBlock) {
      const plantumlCode =
        (ts.deliverables || []).find((d) => d.sample_plantuml)?.sample_plantuml ||
        currentPackageData?.plantuml ||
        `@startuml\nleft to right direction\nactor "用户" as U\npackage "${ts.course_name || "软件系统"}" {\n  usecase "办理业务" as UC1\n  usecase "身份认证" as UC2\n  UC1 ..> UC2 : <<include>>\n}\nU --> UC1\n@enduml`;
      tsPlantumlBlock.textContent = plantumlCode;
    }

    // 7. Markdown
    tasksheetMarkdownBlock.textContent = data.markdown || "";
  }

  // 绑定工单页 PlantUML 复制与跳转工作台
  const tasksheetCopyPlantumlBtn = document.getElementById("tasksheet-copy-plantuml-btn");
  if (tasksheetCopyPlantumlBtn) {
    tasksheetCopyPlantumlBtn.addEventListener("click", () => {
      const block = document.getElementById("tasksheet-plantuml-block");
      if (block && block.textContent) {
        navigator.clipboard.writeText(block.textContent).then(() => {
          showToast("标准参考模型 PlantUML 源码已复制！");
        });
      }
    });
  }

  const tasksheetLaunchUmlBtn = document.getElementById("tasksheet-launch-uml-btn");
  if (tasksheetLaunchUmlBtn) {
    tasksheetLaunchUmlBtn.addEventListener("click", () => {
      const topic = currentTasksheetData?.tasksheet?.course_name || "软件工程需求建模";
      const scenario = currentTasksheetData?.tasksheet?.scenario || "";
      const reqText = `【实训任务建模需求】\n课题：${topic}\n情境描述：${scenario}`;
      try {
        localStorage.setItem("pending_uml_requirement", reqText);
        showToast("正在载入 UML 建模工作台并启动智能体质检…");
        setTimeout(() => {
          window.location.href = "/uml.html";
        }, 300);
      } catch (e) {
        window.location.href = "/uml.html";
      }
    });
  }

  // 打印工单
  tasksheetPrintBtn.addEventListener("click", () => {
    window.print();
  });

  // 复制工单 Markdown
  tasksheetCopyMdBtn.addEventListener("click", () => {
    if (!currentTasksheetData) return;
    const text = tasksheetMarkdownBlock.textContent || "";
    navigator.clipboard.writeText(text).then(() => {
      showToast("实训任务工单 Markdown 已成功复制到剪贴板！");
    });
  });

  // 保存工单草稿
  tasksheetSaveDraftBtn.addEventListener("click", () => {
    if (!currentTasksheetData?.tasksheet) return;
    saveResourceDraft("tasksheet", currentTasksheetData.tasksheet.course_name, currentTasksheetData);
    showToast("实训工单已存入本地草稿箱！");
  });

  // ===================== 7. 教学资源草稿箱 (History Drawer) =====================
  const DRAFT_KEY = "ai_teaching_platform_resource_drafts_v1";
  const btnOpenHistory = document.getElementById("btn-open-history");
  const historyOverlay = document.getElementById("history-overlay");
  const historyDrawer = document.getElementById("history-drawer");
  const historyCloseBtn = document.getElementById("history-close-btn");
  const historyDoneBtn = document.getElementById("history-done-btn");
  const historyClearAllBtn = document.getElementById("history-clear-all-btn");
  const historyListContainer = document.getElementById("history-list-container");
  const historyBadgeCount = document.getElementById("history-badge-count");

  function getDrafts() {
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  }

  function saveResourceDraft(type, title, data) {
    const drafts = getDrafts();
    const item = {
      id: `draft_${Date.now()}`,
      type, // "package" | "ppt" | "lesson" | "tasksheet"
      title: title || "教学资源草稿",
      createdAt: new Date().toLocaleString(),
      data,
    };
    drafts.unshift(item);
    // 最多保留 30 条
    if (drafts.length > 30) drafts.pop();
    localStorage.setItem(DRAFT_KEY, JSON.stringify(drafts));
    updateDraftsBadge();
  }

  function updateDraftsBadge() {
    const drafts = getDrafts();
    historyBadgeCount.textContent = drafts.length;
    historyBadgeCount.style.display = drafts.length > 0 ? "inline-block" : "none";
  }

  function renderDraftsList() {
    const drafts = getDrafts();
    if (drafts.length === 0) {
      historyListContainer.innerHTML = `
        <div style="color: var(--color-text-secondary); text-align: center; padding: 40px 0; font-size: 13px;">
          暂无已保存的资源草稿<br>生成课件、教案或工单后可一键保存
        </div>
      `;
      return;
    }

    const typeBadges = {
      package: `<span class="badge badge-primary" style="background: linear-gradient(135deg,#18181b,#52525b); color:#fff;">${IconLib.svg("zap", 14)} 教学全案</span>`,
      ppt: '<span class="badge badge-warning">PPT 课件</span>',
      lesson: '<span class="badge badge-success">高职教案</span>',
      tasksheet: '<span class="badge badge-primary">实训工单</span>',
    };

    historyListContainer.innerHTML = "";
    drafts.forEach((d) => {
      const card = document.createElement("div");
      card.className = "history-item-card";
      card.innerHTML = `
        <div class="history-item-top">
          ${typeBadges[d.type] || '<span class="badge badge-info">教学资源</span>'}
          <button type="button" class="btn-delete-draft" data-id="${d.id}" style="background: none; border: none; color: var(--color-text-muted); cursor: pointer; font-size: 12px;" title="删除草稿">${IconLib.svg("x", 14)}</button>
        </div>
        <div class="history-item-title">${escapeHtml(d.title)}</div>
        <div class="history-item-meta">保存时间：${escapeHtml(d.createdAt)}</div>
      `;

      card.addEventListener("click", (e) => {
        if (e.target.classList.contains("btn-delete-draft")) return;
        restoreDraft(d);
        closeHistoryDrawer();
      });

      card.querySelector(".btn-delete-draft").addEventListener("click", (e) => {
        e.stopPropagation();
        deleteDraft(d.id);
      });

      historyListContainer.appendChild(card);
    });
  }

  function deleteDraft(id) {
    let drafts = getDrafts();
    drafts = drafts.filter((d) => d.id !== id);
    localStorage.setItem(DRAFT_KEY, JSON.stringify(drafts));
    updateDraftsBadge();
    renderDraftsList();
  }

  function restoreDraft(draft) {
    if (draft.type === "package") {
      switchTab("package");
      currentPackageData = draft.data;
      if (draft.data.ppt) currentPptData = draft.data.ppt;
      if (draft.data.lesson) currentLessonData = draft.data.lesson;
      if (draft.data.tasksheet) currentTasksheetData = draft.data.tasksheet;
      renderPackageResults(draft.data);
      showToast(`已调出历史教学全案：${draft.title}`);
    } else if (draft.type === "ppt") {
      switchTab("ppt");
      currentPptData = draft.data;
      renderPptResults(draft.data);
      showToast(`已调出历史课件：${draft.title}`);
    } else if (draft.type === "lesson") {
      switchTab("lesson");
      currentLessonData = draft.data;
      renderLessonResults(draft.data);
      showToast(`已调出历史教案：${draft.title}`);
    } else if (draft.type === "tasksheet") {
      switchTab("tasksheet");
      currentTasksheetData = draft.data;
      renderTasksheetResults(draft.data);
      showToast(`已调出历史实训工单：${draft.title}`);
    }
  }

  function openHistoryDrawer() {
    renderDraftsList();
    historyOverlay.style.display = "block";
    historyDrawer.classList.add("open");
  }

  function closeHistoryDrawer() {
    historyDrawer.classList.remove("open");
    setTimeout(() => {
      historyOverlay.style.display = "none";
    }, 280);
  }

  btnOpenHistory.addEventListener("click", openHistoryDrawer);
  historyCloseBtn.addEventListener("click", closeHistoryDrawer);
  historyDoneBtn.addEventListener("click", closeHistoryDrawer);
  historyOverlay.addEventListener("click", closeHistoryDrawer);

  historyClearAllBtn.addEventListener("click", () => {
    if (confirm("确定要清空本地所有教学资源草稿吗？此操作无法撤销。")) {
      localStorage.removeItem(DRAFT_KEY);
      updateDraftsBadge();
      renderDraftsList();
      showToast("本地教学资源草稿已清空");
    }
  });

  // 初始化草稿角标
  updateDraftsBadge();

  // ===================== 8. 辅助函数：Markdown 格式化生成与单文件 HTML 演示导出 =====================
  function generatePptMarkdown(data) {
    const outline = data.outline || {};
    const sections = outline.sections || [];
    const pages = data.pages || [];

    let md = `# ${data.title || "教学课件"}\n> ${outline.subtitle || ""}\n\n`;
    md += `## 章节递进大纲\n`;
    sections.forEach((sec, idx) => {
      md += `### ${idx + 1}. ${sec.name} (${sec.page_count}页)\n`;
      (sec.points || []).forEach((pt) => {
        md += `- ${pt}\n`;
      });
      md += "\n";
    });

    md += `## 幻灯片逐页内容\n`;
    pages.forEach((pg, idx) => {
      md += `### 第 ${idx + 1} 页：${pg.title} (${pg.minutes}分钟)\n`;
      (pg.bullets || []).forEach((b) => {
        md += `- ${b}\n`;
      });
      if (pg.note) {
        md += `> ${IconLib.svg("lightbulb", 14)} 讲授指导要点：${pg.note}\n`;
      }
      md += "\n";
    });

    return md;
  }

  function generateStandaloneHtmlSlides(data) {
    const title = data.title || "课件演示";
    const pagesJson = JSON.stringify(data.pages || []);
    return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>${escapeHtml(title)} - 交互演示幻灯片</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #131316; color: #fafafa; height: 100vh; display: flex; flex-direction: column; justify-content: space-between; padding: 32px; overflow: hidden; }
    .top { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 16px; }
    .main { flex: 1; display: flex; align-items: center; justify-content: center; }
    .card { background: #232326; border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; width: 100%; max-width: 960px; min-height: 460px; padding: 48px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5); display: flex; flex-direction: column; justify-content: space-between; }
    .heading { font-size: 28px; font-weight: 800; color: #f8fafc; margin-bottom: 24px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 16px; display: flex; justify-content: space-between; }
    .bullets { list-style: none; display: flex; flex-direction: column; gap: 16px; }
    .bullets li { font-size: 20px; line-height: 1.6; color: #a1a1aa; display: flex; align-items: flex-start; gap: 12px; }
    .bullets li::before { content: "•"; color: #e4e4e7; font-size: 28px; line-height: 1; }
    .note { margin-top: 24px; background: rgba(255,255,255,0.06); border-left: 4px solid #e4e4e7; padding: 12px 16px; border-radius: 4px; font-size: 14px; color: #a1a1aa; }
    .bottom { display: flex; justify-content: space-between; align-items: center; }
    .btn { background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); color: #fff; padding: 8px 18px; border-radius: 8px; font-size: 14px; cursor: pointer; }
    .btn:hover { background: #3f3f46; }
  </style>
</head>
<body>
  <div class="top">
    <div style="font-size: 18px; font-weight: 700;">${escapeHtml(title)}</div>
    <div id="counter" style="color: #a1a1aa;">1 / 1</div>
  </div>
  <div class="main">
    <div class="card">
      <div>
        <div class="heading">
          <span id="slide-title">第一讲</span>
          <span id="slide-time" style="font-size: 14px; color: #e4e4e7;">10 分钟</span>
        </div>
        <ul class="bullets" id="slide-bullets"></ul>
      </div>
      <div class="note" id="slide-note"></div>
    </div>
  </div>
  <div class="bottom">
    <span style="color: #71717a; font-size: 13px;">按键盘 ← / → 或空格键快速翻页</span>
    <div>
      <button class="btn" id="prev">上一页</button>
      <button class="btn" id="next">下一页</button>
    </div>
  </div>
  <script>
    const pages = ${pagesJson};
    let cur = 0;
    function render() {
      if(!pages.length) return;
      const p = pages[cur];
      document.getElementById("counter").textContent = (cur + 1) + " / " + pages.length;
      document.getElementById("slide-title").textContent = p.title || "";
      document.getElementById("slide-time").textContent = (p.minutes || 5) + " 分钟";
      const ul = document.getElementById("slide-bullets");
      ul.innerHTML = "";
      (p.bullets||[]).forEach(b => {
        const li = document.createElement("li");
        li.textContent = b;
        ul.appendChild(li);
      });
      const noteBox = document.getElementById("slide-note");
      if(p.note) { noteBox.style.display = "block"; noteBox.innerHTML = IconLib.svg("lightbulb", 14) + " 备课要点："; }
      else { noteBox.style.display = "none"; }
    }
    document.getElementById("prev").onclick = () => { if(cur > 0) { cur--; render(); } };
    document.getElementById("next").onclick = () => { if(cur < pages.length - 1) { cur++; render(); } };
    window.onkeydown = (e) => {
      if(e.key === "ArrowLeft") document.getElementById("prev").click();
      if(e.key === "ArrowRight" || e.key === " ") document.getElementById("next").click();
    };
    render();
  </script>
</body>
</html>`;
  }
});
