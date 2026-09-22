/**
 * 课件与教案交互逻辑（js/resources.js）
 * 严格按照 M5 前端页面设计文档 6.5 节规范实现
 */

document.addEventListener("DOMContentLoaded", () => {
  // Tab 切换逻辑
  const tabBtnPpt = document.getElementById("tab-btn-ppt");
  const tabBtnLesson = document.getElementById("tab-btn-lesson");
  const panelPpt = document.getElementById("panel-ppt");
  const panelLesson = document.getElementById("panel-lesson");

  const errorBar = document.getElementById("resources-error-bar");
  const skeletonBox = document.getElementById("resources-skeleton-box");

  function switchTab(target) {
    hideError();
    if (target === "lesson") {
      tabBtnLesson.classList.add("active");
      tabBtnPpt.classList.remove("active");
      panelLesson.style.display = "block";
      panelPpt.style.display = "none";
    } else {
      tabBtnPpt.classList.add("active");
      tabBtnLesson.classList.remove("active");
      panelPpt.style.display = "block";
      panelLesson.style.display = "none";
    }
  }

  tabBtnPpt.addEventListener("click", () => switchTab("ppt"));
  tabBtnLesson.addEventListener("click", () => switchTab("lesson"));

  // 支持 URL 参数 ?tab=lesson 初始化
  const urlParams = new URLSearchParams(window.location.search);
  const initialTab = urlParams.get("tab");
  if (initialTab === "lesson") {
    switchTab("lesson");
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

  // ===================== PPT 生成处理 =====================
  const pptTopic = document.getElementById("ppt-topic");
  const pptMinutes = document.getElementById("ppt-minutes");
  const generatePptBtn = document.getElementById("generate-ppt-btn");
  const pptTopicError = document.getElementById("ppt-topic-error");
  const pptResultSection = document.getElementById("ppt-result-section");
  const pptResultTitle = document.getElementById("ppt-result-title");
  const pptPagesCountBadge = document.getElementById("ppt-pages-count-badge");
  const pptDownloadBtn = document.getElementById("ppt-download-btn");
  const pptOutlineContainer = document.getElementById("ppt-outline-container");
  const pptPagesGrid = document.getElementById("ppt-pages-grid");

  pptTopic.addEventListener("input", () => {
    if (pptTopic.value.trim().length >= 2) {
      pptTopicError.style.display = "none";
      pptTopic.classList.remove("error");
    }
  });

  generatePptBtn.addEventListener("click", async () => {
    const topic = pptTopic.value.trim();
    const minutes = parseInt(pptMinutes.value, 10) || 90;

    if (!topic || topic.length < 2 || topic.length > 100) {
      pptTopicError.style.display = "block";
      pptTopic.classList.add("error");
      pptTopic.focus();
      return;
    }

    hideError();
    pptResultSection.style.display = "none";
    skeletonBox.style.display = "block";
    generatePptBtn.disabled = true;
    generatePptBtn.textContent = "生成中…（约 1 分钟）";

    try {
      const data = await apiPost("/v1/ppt", { topic, minutes }, { timeoutMs: 180000 });
      renderPptResults(data);
    } catch (err) {
      showError(err.message || "服务异常，请稍后重试");
    } finally {
      skeletonBox.style.display = "none";
      generatePptBtn.disabled = false;
      generatePptBtn.textContent = "生成 PPT 课件";
    }
  });

  function renderPptResults(data) {
    pptResultSection.style.display = "block";
    pptResultSection.scrollIntoView({ behavior: "smooth", block: "start" });

    // 1. 标题与下载按钮
    pptResultTitle.textContent = data.title || "课件生成大纲";
    pptPagesCountBadge.textContent = `共 ${data.total_pages || (data.pages ? data.pages.length : 0)} 页`;
    if (data.download_url) {
      pptDownloadBtn.href = data.download_url;
      pptDownloadBtn.download = `${data.title || "course"}.pptx`;
      pptDownloadBtn.style.display = "inline-flex";
    } else {
      pptDownloadBtn.style.display = "none";
    }

    // 2. 课程大纲结构
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

    // 3. 幻灯片分页预览
    const pages = data.pages || [];
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
        ${
          pg.note
            ? `
          <details class="page-note-details">
            <summary>💡 讲授指导要点</summary>
            <p style="margin-top: 4px;">${escapeHtml(pg.note)}</p>
          </details>
        `
            : ""
        }
      `;
      pptPagesGrid.appendChild(card);
    });
  }

  // ===================== 教案生成处理 =====================
  const lessonTopic = document.getElementById("lesson-topic");
  const lessonMinutes = document.getElementById("lesson-minutes");
  const generateLessonBtn = document.getElementById("generate-lesson-btn");
  const lessonTopicError = document.getElementById("lesson-topic-error");
  const lessonResultSection = document.getElementById("lesson-result-section");
  const lessonMissingFieldsBar = document.getElementById("lesson-missing-fields-bar");
  const lessonCourseName = document.getElementById("lesson-course-name");
  const lessonDownloadBtn = document.getElementById("lesson-download-btn");

  const goalKnowledgeList = document.getElementById("goal-knowledge-list");
  const goalAbilityList = document.getElementById("goal-ability-list");
  const goalLiteracyList = document.getElementById("goal-literacy-list");
  const keyPointsList = document.getElementById("key-points-list");
  const difficultPointsList = document.getElementById("difficult-points-list");
  const flowTbody = document.getElementById("flow-tbody");
  const exercisesList = document.getElementById("exercises-list");
  const homeworkList = document.getElementById("homework-list");
  const lessonMarkdownBlock = document.getElementById("lesson-markdown-block");

  lessonTopic.addEventListener("input", () => {
    if (lessonTopic.value.trim().length >= 2) {
      lessonTopicError.style.display = "none";
      lessonTopic.classList.remove("error");
    }
  });

  generateLessonBtn.addEventListener("click", async () => {
    const topic = lessonTopic.value.trim();
    const minutes = parseInt(lessonMinutes.value, 10) || 45;

    if (!topic || topic.length < 2 || topic.length > 100) {
      lessonTopicError.style.display = "block";
      lessonTopic.classList.add("error");
      lessonTopic.focus();
      return;
    }

    hideError();
    lessonResultSection.style.display = "none";
    skeletonBox.style.display = "block";
    generateLessonBtn.disabled = true;
    generateLessonBtn.textContent = "生成中…（约 1 分钟）";

    try {
      const data = await apiPost("/v1/lesson", { topic, minutes }, { timeoutMs: 180000 });
      renderLessonResults(data);
    } catch (err) {
      showError(err.message || "服务异常，请稍后重试");
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

    // 下载链接
    if (data.download_url) {
      lessonDownloadBtn.href = data.download_url;
      lessonDownloadBtn.download = `${lesson.course_name || "lesson"}.docx`;
      lessonDownloadBtn.style.display = "inline-flex";
    } else {
      lessonDownloadBtn.style.display = "none";
    }

    // 1. 教学目标渲染
    const goals = lesson.teaching_goals || {};
    renderList(goalKnowledgeList, goals.knowledge);
    renderList(goalAbilityList, goals.ability);
    renderList(goalLiteracyList, goals.literacy);

    // 2. 重难点
    renderList(keyPointsList, lesson.key_points);
    renderList(difficultPointsList, lesson.difficult_points);

    // 3. 教学流程表
    const flows = lesson.teaching_flow || [];
    flowTbody.innerHTML = "";
    flows.forEach((item) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td style="font-weight: 600;">${escapeHtml(item.stage || "-")}</td>
        <td><span class="badge badge-info">${escapeHtml(item.minutes || 0)} 分钟</span></td>
        <td>${escapeHtml(item.teacher_activity || "-")}</td>
        <td>${escapeHtml(item.student_activity || "-")}</td>
      `;
      flowTbody.appendChild(tr);
    });

    // 4. 实训练习与作业
    renderList(exercisesList, lesson.class_exercises, "ol");
    renderList(homeworkList, lesson.homework, "ol");

    // 5. Markdown 文本
    lessonMarkdownBlock.textContent = data.markdown || "";
  }

  function renderList(container, items, tag = "ul") {
    container.innerHTML = "";
    if (!items || items.length === 0) {
      container.innerHTML = `<li style="color: var(--color-text-secondary); list-style: none;">（暂无）</li>`;
      return;
    }
    items.forEach((txt) => {
      const li = document.createElement("li");
      li.textContent = txt;
      container.appendChild(li);
    });
  }
});
