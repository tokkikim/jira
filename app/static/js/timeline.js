// 프로젝트 목록 로드 함수
async function loadProjects() {
  const projectButtons = document.getElementById("project-buttons");
  if (!projectButtons) {
    console.error("프로젝트 버튼 컨테이너를 찾을 수 없습니다.");
    return;
  }

  try {
    const res = await fetch("/api/projects");
    if (!res.ok) {
      throw new Error(`HTTP error! status: ${res.status}`);
    }
    const data = await res.json();

    if (data.error) {
      throw new Error(data.error);
    }

    const projects = data.projects || [];
    console.log("로드된 프로젝트:", projects);

    // 프로젝트 버튼 생성
    projectButtons.innerHTML = "";
    projects.forEach((project) => {
      const button = document.createElement("button");
      button.className = "project-btn";
      button.dataset.key = project.key;
      button.textContent = `${project.key} - ${project.name}`;
      button.title = project.name;

      // 클릭 이벤트
      button.addEventListener("click", () => {
        button.classList.toggle("selected");
        updateProjectInput();
      });

      projectButtons.appendChild(button);
    });

    // URL 파라미터에서 선택된 프로젝트 복원
    const qs = new URLSearchParams(window.location.search);
    const selectedProjects = qs.get("projects") || qs.get("project") || "";
    if (selectedProjects) {
      const projectKeys = selectedProjects.split(",").map((p) => p.trim());
      projectKeys.forEach((key) => {
        const button = projectButtons.querySelector(`[data-key="${key}"]`);
        if (button) {
          button.classList.add("selected");
        }
      });
    }
  } catch (error) {
    console.error("프로젝트 목록 로드 중 오류 발생:", error);
    projectButtons.innerHTML = `<div style="color: #dc2626; font-size: 12px;">프로젝트 목록 로드 실패: ${error.message}</div>`;
  }
}

// 프로젝트 입력 필드 업데이트
function updateProjectInput() {
  const selectedButtons = document.querySelectorAll(".project-btn.selected");
  const projectKeys = Array.from(selectedButtons).map((btn) => btn.dataset.key);
  const projectsInput = document.getElementById("projects");

  if (projectsInput) {
    projectsInput.value = projectKeys.join(",");
  }
}

// 전체 선택/해제 함수
function selectAllProjects() {
  const buttons = document.querySelectorAll(".project-btn");
  buttons.forEach((btn) => btn.classList.add("selected"));
  updateProjectInput();
}

function clearAllProjects() {
  const buttons = document.querySelectorAll(".project-btn");
  buttons.forEach((btn) => btn.classList.remove("selected"));
  updateProjectInput();
}

// 샘플 데이터 로드 함수
async function loadSample() {
  const container = document.getElementById("app");
  if (!container) {
    console.error("타임라인 컨테이너를 찾을 수 없습니다.");
    return;
  }

  // 로딩 상태 표시
  container.innerHTML =
    '<div class="loading">샘플 데이터를 불러오는 중...</div>';

  try {
    const url = new URL("/api/sample", window.location.origin);
    console.log("샘플 데이터 요청 URL:", url.toString());

    const res = await fetch(url);
    if (!res.ok) {
      throw new Error(`HTTP error! status: ${res.status}`);
    }
    const data = await res.json();

    console.log("샘플 데이터 응답:", data);

    if (data.error) {
      throw new Error(data.error);
    }

    renderTimeline(data);
  } catch (error) {
    console.error("샘플 데이터 로드 중 오류 발생:", error);
    container.innerHTML = `<div class="error-message">샘플 데이터 로드 중 오류가 발생했습니다: ${error.message}</div>`;
  }
}

// 타임라인 데이터 로드 함수
async function load() {
  const container = document.getElementById("app");
  if (!container) {
    console.error("타임라인 컨테이너를 찾을 수 없습니다.");
    return;
  }

  // 로딩 상태 표시
  container.innerHTML = '<div class="loading">데이터를 불러오는 중...</div>';

  const projects = document.getElementById("projects").value.trim();
  const group_by = document.getElementById("group_by").value;
  const from_date = document.getElementById("from_date").value;
  const to_date = document.getElementById("to_date").value;

  const url = new URL("/api/timeline", window.location.origin);
  if (projects) url.searchParams.set("projects", projects);
  url.searchParams.set("group_by", group_by);
  if (from_date) url.searchParams.set("from_date", from_date);
  if (to_date) url.searchParams.set("to_date", to_date);

  try {
    console.log("API 요청 URL:", url.toString());
    const res = await fetch(url);
    if (!res.ok) {
      throw new Error(`HTTP error! status: ${res.status}`);
    }
    const data = await res.json();

    console.log("API 응답 데이터:", data);

    if (data.error) {
      throw new Error(data.error);
    }

    renderTimeline(data);

    // URL 업데이트
    const newQs = new URLSearchParams();
    if (projects) newQs.set("projects", projects);
    newQs.set("group_by", group_by);
    if (from_date) newQs.set("from_date", from_date);
    if (to_date) newQs.set("to_date", to_date);
    history.replaceState(null, "", `/?${newQs.toString()}`);
  } catch (error) {
    console.error("데이터 로드 중 오류 발생:", error);
    container.innerHTML = `<div class="error-message">데이터 로드 중 오류가 발생했습니다: ${error.message}</div>`;
  }
}

// 타임라인 렌더링 함수
function renderTimeline(data) {
  console.log("타임라인 렌더링 시작:", data);

  const container = document.getElementById("app");
  if (!container) {
    console.error("타임라인 컨테이너를 찾을 수 없습니다.");
    return;
  }

  container.innerHTML = "";

  if (!data.items || data.items.length === 0) {
    console.log("데이터가 없습니다.");
    container.innerHTML =
      '<div class="no-data">데이터가 없습니다. 프로젝트를 확인하거나 날짜 범위를 조정해보세요.</div>';
    return;
  }

  console.log("아이템 개수:", data.items.length);
  console.log("그룹 개수:", data.groups ? data.groups.length : 0);

  // vis 라이브러리 확인
  if (typeof vis === "undefined") {
    console.error("vis 라이브러리가 로드되지 않았습니다.");
    container.innerHTML =
      '<div class="error-message">타임라인 라이브러리를 로드할 수 없습니다. 페이지를 새로고침해주세요.</div>';
    return;
  }

  if (!vis.Timeline) {
    console.error(
      "vis.Timeline이 정의되지 않았습니다. HTML 테이블로 대체합니다."
    );
    renderSimpleTimeline(data, container);
    return;
  }

  const items = new vis.DataSet(
    (data.items || []).map((it) => ({
      id: it.id,
      group: it.group,
      content: it.content,
      title: it.title || it.content, // 툴팁으로 전체 제목 표시
      start: it.start ? new Date(it.start) : null,
      end: it.end ? new Date(it.end + "T23:59:59") : null,
      style: it.color
        ? `background-color:${it.color};border-color:${it.color};color:#111;font-weight:500;`
        : "font-weight:500;",
    }))
  );

  const groups = new vis.DataSet(data.groups || []);
  const today = new Date();
  const startWindow = new Date(
    today.getFullYear(),
    today.getMonth(),
    today.getDate() - 14
  );
  const endWindow = new Date(
    today.getFullYear(),
    today.getMonth(),
    today.getDate() + 45
  );

  console.log("타임라인 생성 중...");
  console.log("아이템 데이터:", items.get());
  console.log("그룹 데이터:", groups.get());

  const timeline = new vis.Timeline(container, items, groups, {
    stack: false, // 아이템들이 겹치지 않도록 stack 비활성화
    orientation: "top",
    multiselect: false,
    showCurrentTime: true,
    zoomKey: "ctrlKey",
    margin: { item: 4, axis: 12 },
    min: startWindow,
    max: endWindow,
    timeAxis: { scale: "day", step: 1 },
    zoomMin: 1000 * 60 * 60 * 24,
    zoomMax: 1000 * 60 * 60 * 24 * 365,
    height: "100%", // 컨테이너 높이에 맞춤
    autoResize: true, // 자동 크기 조정
    // 간트차트 스타일 설정
    verticalScroll: true,
    horizontalScroll: true,
    zoomable: true,
    moveable: true,
    selectable: false,
    editable: false,
    // 그리드 스타일
    showMajorLabels: true,
    showMinorLabels: true,
    showWeekScale: true,
    showCurrentTime: true,
    // 아이템 스타일 - 각 아이템이 별도 행에 표시
    itemHeightRatio: 0.7,
    itemMargin: 1,
    // 그룹별 정렬
    groupHeightMode: "fixed",
    groupHeight: 40,
    // 그룹 라벨 표시 설정
    showGroupLabels: true,
  });

  timeline.addCustomTime(new Date(), "now");
  console.log("타임라인 생성 완료");
}

// 간단한 HTML 테이블 기반 타임라인 렌더링
function renderSimpleTimeline(data, container) {
  console.log("HTML 테이블 타임라인 렌더링 시작");

  const groups = data.groups || [];
  const items = data.items || [];

  // 그룹별로 아이템 정리
  const groupedItems = {};
  groups.forEach((group) => {
    groupedItems[group.id] = {
      title: group.title,
      items: [],
    };
  });

  items.forEach((item) => {
    if (groupedItems[item.group]) {
      groupedItems[item.group].items.push(item);
    }
  });

  // HTML 생성
  let html =
    '<div style="padding: 32px; background: linear-gradient(135deg, #f8fafc, #f1f5f9); min-height: 100%;">';
  html +=
    '<div style="background: white; border-radius: 24px; padding: 32px; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25); border: 1px solid rgba(255, 255, 255, 0.2);">';
  html +=
    '<h2 style="margin-bottom: 32px; color: #1f2937; font-size: 28px; font-weight: 700; display: flex; align-items: center; gap: 16px; letter-spacing: -0.025em;">';
  html +=
    '<i class="fas fa-chart-line" style="color: #3b82f6; font-size: 32px;"></i>';
  html += "타임라인 대시보드";
  html += "</h2>";

  Object.values(groupedItems).forEach((group) => {
    if (group.items.length > 0) {
      html += `<div style="margin-bottom: 40px;">`;
      html += `<h3 style="color: #1f2937; margin-bottom: 20px; font-size: 20px; font-weight: 700; display: flex; align-items: center; gap: 12px; letter-spacing: -0.025em;">`;
      html += `<i class="fas fa-layer-group" style="color: #10b981; font-size: 24px;"></i>`;
      html += `${group.title}`;
      html += `</h3>`;
      html += `<div style="overflow-x: auto; border-radius: 16px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.1); border: 1px solid #e5e7eb;">`;
      html += `<table style="width: 100%; border-collapse: collapse; background: white; border-radius: 16px; overflow: hidden;">`;
      html += `<thead><tr style="background: linear-gradient(135deg, #f8fafc, #f1f5f9);">`;
      html += `<th style="padding: 16px 20px; text-align: left; border-bottom: 2px solid #e5e7eb; font-weight: 700; color: #1f2937; font-size: 14px; letter-spacing: 0.025em;">이슈</th>`;
      html += `<th style="padding: 16px 20px; text-align: left; border-bottom: 2px solid #e5e7eb; font-weight: 700; color: #1f2937; font-size: 14px; letter-spacing: 0.025em;">시작일</th>`;
      html += `<th style="padding: 16px 20px; text-align: left; border-bottom: 2px solid #e5e7eb; font-weight: 700; color: #1f2937; font-size: 14px; letter-spacing: 0.025em;">종료일</th>`;
      html += `<th style="padding: 16px 20px; text-align: left; border-bottom: 2px solid #e5e7eb; font-weight: 700; color: #1f2937; font-size: 14px; letter-spacing: 0.025em;">기간</th>`;
      html += `</tr></thead><tbody>`;

      group.items.forEach((item) => {
        const startDate = item.start ? new Date(item.start) : null;
        const endDate = item.end ? new Date(item.end) : null;
        const duration =
          startDate && endDate
            ? Math.ceil((endDate - startDate) / (1000 * 60 * 60 * 24)) + 1
            : "N/A";

        html += `<tr style="border-bottom: 1px solid #f1f5f9; transition: all 0.2s ease; cursor: pointer;">`;
        html += `<tr onmouseover="this.style.background='#f8fafc'" onmouseout="this.style.background='white'">`;
        html += `<td style="padding: 16px 20px; font-weight: 600; color: #1f2937; font-size: 14px;">${
          item.content || item.id
        }</td>`;
        html += `<td style="padding: 16px 20px; color: #6b7280; font-size: 14px; font-weight: 500;">${
          startDate ? startDate.toLocaleDateString() : "N/A"
        }</td>`;
        html += `<td style="padding: 16px 20px; color: #6b7280; font-size: 14px; font-weight: 500;">${
          endDate ? endDate.toLocaleDateString() : "N/A"
        }</td>`;
        html += `<td style="padding: 16px 20px; color: #059669; font-weight: 700; font-size: 14px; background: linear-gradient(135deg, #f0fdf4, #dcfce7); border-radius: 8px; text-align: center;">${duration}일</td>`;
        html += `</tr>`;
      });

      html += `</tbody></table>`;
      html += `</div>`;
      html += `</div>`;
    }
  });

  html += "</div>";
  html += "</div>";
  container.innerHTML = html;
  console.log("HTML 테이블 타임라인 렌더링 완료");
}

// 이벤트 리스너 등록
document.addEventListener("DOMContentLoaded", function () {
  // URL 파라미터에서 초기값 설정
  const qs = new URLSearchParams(window.location.search);
  const projectsInput = document.getElementById("projects");
  const groupBySelect = document.getElementById("group_by");
  const fromDateInput = document.getElementById("from_date");
  const toDateInput = document.getElementById("to_date");

  if (projectsInput) {
    projectsInput.value = qs.get("projects") || qs.get("project") || "";
  }
  if (groupBySelect) {
    groupBySelect.value = qs.get("group_by") || "project";
  }
  if (fromDateInput && qs.get("from_date")) {
    fromDateInput.value = qs.get("from_date");
  }
  if (toDateInput && qs.get("to_date")) {
    toDateInput.value = qs.get("to_date");
  }

  // Load 버튼 이벤트 리스너 등록
  const loadButton = document.getElementById("load");
  if (loadButton) {
    loadButton.addEventListener("click", load);
  }

  // Sample Data 버튼 이벤트 리스너 등록
  const sampleButton = document.getElementById("sample");
  if (sampleButton) {
    sampleButton.addEventListener("click", loadSample);
  }

  // 프로젝트 필터 버튼 이벤트 리스너 등록
  const selectAllButton = document.getElementById("select-all");
  if (selectAllButton) {
    selectAllButton.addEventListener("click", selectAllProjects);
  }

  const clearAllButton = document.getElementById("clear-all");
  if (clearAllButton) {
    clearAllButton.addEventListener("click", clearAllProjects);
  }

  // 프로젝트 목록 로드
  loadProjects();

  // 페이지 로드 시 자동으로 샘플 데이터 로드 (테스트용)
  loadSample();
});
