// 한우 스마트 컨설팅 통합 웹 플랫폼 클라이언트 스크립트

const API_BASE = ""; // 동일 origin
const ACCESS_TOKEN_KEY = "hanwoo_access_token";

// URL의 ?token=... 을 localStorage에 저장하고 주소창에서는 지운다.
function getAccessToken() {
  try {
    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get("token");
    if (urlToken) {
      localStorage.setItem(ACCESS_TOKEN_KEY, urlToken);
      params.delete("token");
      const query = params.toString();
      const newUrl = window.location.pathname + (query ? `?${query}` : "") + window.location.hash;
      window.history.replaceState({}, "", newUrl);
    }
  } catch (e) {}
  try {
    return localStorage.getItem(ACCESS_TOKEN_KEY) || "";
  } catch (e) {
    return "";
  }
}

// 모든 /api/* 호출에 접속 토큰을 실어 보내는 fetch 래퍼
async function apiFetch(url, options = {}) {
  const headers = Object.assign({}, options.headers || {}, { "X-Access-Token": getAccessToken() });
  const res = await fetch(url, Object.assign({}, options, { headers }));
  if (res.status === 401) {
    alert("접근 권한이 없습니다. 관리자에게 올바른 접속 주소(토큰 포함)를 요청하세요.");
  }
  return res;
}

let currentFarmId = null;
let currentVisitId = null;
let benchmarkChart = null;
let currentMetric = "avg_weight";
let dashboardDataCache = null;

// 초기화
document.addEventListener("DOMContentLoaded", () => {
  initNavigation();
  initTime();
  loadFarms();
  loadDashboard();
  initSurveyRatingButtons();
  initVoiceInput();
  initModal();
  initEventListeners();
});

// 시스템 시계
function initTime() {
  const timeEl = document.getElementById("systemTime");
  const update = () => {
    const now = new Date();
    timeEl.textContent = now.toLocaleDateString("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit", weekday: "short" }) + " " + now.toLocaleTimeString("ko-KR");
  };
  update();
  setInterval(update, 1000);
}

// 탭 네비게이션
function initNavigation() {
  const navItems = document.querySelectorAll(".nav-item");
  navItems.forEach(btn => {
    btn.addEventListener("click", () => {
      const tabId = btn.dataset.tab;
      navItems.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
      const targetPane = document.getElementById(`tab-${tabId}`);
      if (targetPane) targetPane.classList.add("active");

      if (tabId === "dashboard") {
        loadDashboard();
      } else if (tabId === "database") {
        loadDatabaseView();
      }
    });
  });
}

// 농가 목록 로드
async function loadFarms() {
  try {
    const res = await apiFetch(`${API_BASE}/api/farms`);
    const farms = await res.json();
    const select = document.getElementById("farmSelect");
    select.innerHTML = '<option value="">농가를 선택하세요...</option>';
    
    farms.forEach(f => {
      const opt = document.createElement("option");
      opt.value = f.id;
      opt.textContent = `${f.farm_name} (${f.owner_name || '대표자미상'}, ${f.total_heads}두)`;
      select.appendChild(opt);
    });

    if (farms.length > 0 && !currentFarmId) {
      currentFarmId = farms[0].id;
      select.value = currentFarmId;
      loadFarmDetail(currentFarmId);
    }
  } catch (err) {
    console.error("농가 목록 로드 실패:", err);
  }
}

// 대시보드 로드
async function loadDashboard() {
  try {
    const res = await apiFetch(`${API_BASE}/api/dashboard`);
    const data = await res.json();
    dashboardDataCache = data;

    // KPI 카드
    document.getElementById("kpiTotalFarms").textContent = `${data.kpi.total_farms} 농가`;
    document.getElementById("kpiTotalVisits").textContent = `${data.kpi.total_visits} 회`;
    document.getElementById("kpiTotalShipments").textContent = `${data.kpi.total_shipments} 두`;
    document.getElementById("kpiAvg1PlusRate").textContent = `${data.kpi.avg_1plus_rate}%`;

    // 연도별 표 렌더링
    const tbody = document.querySelector("#yearlyTable tbody");
    tbody.innerHTML = "";
    data.yearly_averages.forEach(row => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${row.year}년</strong></td>
        <td>${row.farm_count}</td>
        <td>${row.head_count}두</td>
        <td><strong>${row.avg_weight || '-'} kg</strong></td>
        <td>${row.avg_bms || '-'}</td>
        <td><span class="badge-status positive">${row.rate_1plus_above || '-'}%</span></td>
        <td>${row.avg_month_age || '-'}개월</td>
      `;
      tbody.appendChild(tr);
    });

    // 최근 방문 이력
    const vbody = document.querySelector("#recentVisitsTable tbody");
    vbody.innerHTML = "";
    data.recent_visits.forEach(v => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${v.farm_name}</strong></td>
        <td>${v.visit_number}차 방문</td>
        <td>${v.visit_date}</td>
        <td>${v.consultant_name}</td>
        <td><span class="badge-status positive">${v.status === 'completed' ? '완료' : '진행중'}</span></td>
        <td>${v.has_report ? '<button class="btn btn-outline btn-sm" onclick="viewReport(' + v.id + ')">리포트 보기</button>' : '<span class="text-muted">미생성</span>'}</td>
      `;
      vbody.appendChild(tr);
    });

    // 차트 렌더링
    renderBenchmarkChart(currentMetric);
  } catch (err) {
    console.error("대시보드 로드 실패:", err);
  }
}

// 벤치마크 차트 렌더링
function renderBenchmarkChart(metric) {
  if (!dashboardDataCache) return;
  const ctx = document.getElementById("benchmarkChart").getContext("2d");

  const years = [2023, 2024, 2025, 2026];
  const natData = dashboardDataCache.national_benchmarks;
  const avgData = dashboardDataCache.yearly_averages;

  // 지표 라벨
  const metricLabels = {
    avg_weight: { label: "도체중 (kg)", natKey: "도체중" },
    avg_bms: { label: "BMS 마블링", natKey: "BMS" },
    rate_1plus_above: { label: "1+이상 출현율 (%)", natKey: "rate_1plus_above" },
    avg_month_age: { label: "출하월령 (개월)", natKey: "출하월령" }
  };

  const meta = metricLabels[metric] || metricLabels.avg_weight;

  // 전국 데이터
  const natValues = years.map(y => natData[meta.natKey] ? (natData[meta.natKey][y] || null) : null);

  // 방문농가 전체 평균 데이터
  const farmValues = years.map(y => {
    const found = avgData.find(d => d.year === y);
    return found ? found[metric] : null;
  });

  if (benchmarkChart) {
    benchmarkChart.destroy();
  }

  benchmarkChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: years.map(y => `${y}년`),
      datasets: [
        {
          label: "전국 평균",
          data: natValues,
          borderColor: "#94a3b8",
          backgroundColor: "rgba(148, 163, 184, 0.1)",
          borderWidth: 2,
          borderDash: [5, 5],
          pointRadius: 4,
          tension: 0.2
        },
        {
          label: "방문농가 전체 평균 (누적DB)",
          data: farmValues,
          borderColor: "#2563eb",
          backgroundColor: "rgba(37, 99, 235, 0.1)",
          borderWidth: 3,
          pointRadius: 6,
          pointBackgroundColor: "#2563eb",
          tension: 0.3
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "top",
          labels: { font: { family: "Pretendard", size: 12 } }
        },
        tooltip: {
          titleFont: { family: "Pretendard" },
          bodyFont: { family: "Pretendard" }
        }
      },
      scales: {
        y: {
          grid: { color: "#f1f5f9" },
          ticks: { font: { family: "Pretendard" } }
        },
        x: {
          grid: { display: false },
          ticks: { font: { family: "Pretendard" } }
        }
      }
    }
  });
}

// 농가 상세 및 출하성적 로드
async function loadFarmDetail(farmId) {
  if (!farmId) return;
  try {
    const res = await apiFetch(`${API_BASE}/api/farms/${farmId}`);
    const data = await res.json();

    // 비교표 렌더링
    const compTbody = document.querySelector("#comparisonTable tbody");
    compTbody.innerHTML = "";
    if (data.comparisons && data.comparisons.length > 0) {
      data.comparisons.forEach(c => {
        const tr = document.createElement("tr");
        let badgeClass = "positive";
        if (c.status === "미흡" || c.status === "과비주의" || c.status === "지연출하") {
          badgeClass = "negative";
        } else if (c.status === "적정" || c.status === "동일") {
          badgeClass = "warning";
        }

        const diffStr = c.diff !== null ? (c.diff > 0 ? `+${c.diff}` : `${c.diff}`) : '-';

        tr.innerHTML = `
          <td><strong>${c.metric}</strong> (${c.unit})</td>
          <td>${c.farm_value !== null ? `${c.farm_value} ${c.unit}` : '<span class="text-muted">미입력</span>'}</td>
          <td>${c.national_value} ${c.unit}</td>
          <td><strong>${diffStr}</strong></td>
          <td><span class="badge-status ${badgeClass}">${c.status}</span></td>
        `;
        compTbody.appendChild(tr);
      });
    } else {
      compTbody.innerHTML = '<tr><td colspan="5" class="text-center">이력번호를 입력하여 출하성적을 추출해주세요.</td></tr>';
    }

    // 출하 개체 목록 렌더링
    const recTbody = document.querySelector("#shipmentRecordsTable tbody");
    recTbody.innerHTML = "";
    if (data.records && data.records.length > 0) {
      data.records.forEach(r => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td><strong>${r.animal_no}</strong></td>
          <td>${r.gender}</td>
          <td>${r.slaughter_date || '-'}</td>
          <td>${r.carcass_weight || '-'} kg</td>
          <td><span class="badge-status positive">${r.grade_quality || '-'}</span></td>
          <td>${r.grade_yield || '-'}</td>
          <td>${r.bms || '-'}</td>
          <td>${r.backfat || '-'} mm</td>
          <td>${r.ribeye || '-'} ㎠</td>
          <td>${r.month_age || '-'}개월</td>
          <td>${r.total_price ? (r.total_price).toLocaleString() + '원' : '-'}</td>
        `;
        recTbody.appendChild(tr);
      });
    } else {
      recTbody.innerHTML = '<tr><td colspan="11" class="text-center">등록된 출하 개체 성적이 없습니다.</td></tr>';
    }

    // 현장조사 기본값 세팅
    document.getElementById("surveyDate").value = new Date().toISOString().split("T")[0];
    document.getElementById("surveyHeads").value = data.farm.total_heads || "";

    // 최근 방문 회차 세팅
    if (data.visits && data.visits.length > 0) {
      currentVisitId = data.visits[0].id;
    }
  } catch (err) {
    console.error("농가 상세 조회 실패:", err);
  }
}

// 현장조사 평점 버튼 이벤트
function initSurveyRatingButtons() {
  document.querySelectorAll(".btn-group-rating").forEach(group => {
    const buttons = group.querySelectorAll(".btn-rate");
    buttons.forEach(btn => {
      btn.addEventListener("click", () => {
        buttons.forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
      });
    });
  });
}

// 음성 인식 (Web Speech API)
function initVoiceInput() {
  const btn = document.getElementById("btnVoiceInput");
  const textarea = document.getElementById("inputFarmerDialogue");

  if (!("webkitSpeechRecognition" in window) && !("SpeechRecognition" in window)) {
    btn.style.display = "none";
    return;
  }

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognition = new SpeechRecognition();
  recognition.lang = "ko-KR";
  recognition.continuous = false;
  recognition.interimResults = false;

  let isRecording = false;

  btn.addEventListener("click", () => {
    if (!isRecording) {
      recognition.start();
      isRecording = true;
      btn.textContent = "🔴 음성 듣는 중... (말씀하세요)";
      btn.classList.add("active");
    } else {
      recognition.stop();
      isRecording = false;
      btn.textContent = "🎤 음성 인식 시작";
      btn.classList.remove("active");
    }
  });

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    textarea.value += (textarea.value ? " " : "") + transcript;
    isRecording = false;
    btn.textContent = "🎤 음성 인식 시작";
    btn.classList.remove("active");
  };

  recognition.onerror = () => {
    isRecording = false;
    btn.textContent = "🎤 음성 인식 시작";
    btn.classList.remove("active");
  };
}

// 모달 처리
function initModal() {
  const modal = document.getElementById("modalNewFarm");
  document.getElementById("btnNewFarmModal").addEventListener("click", () => {
    modal.style.display = "flex";
  });
  document.getElementById("btnCloseModal").addEventListener("click", () => {
    modal.style.display = "none";
  });
  document.getElementById("btnCancelFarm").addEventListener("click", () => {
    modal.style.display = "none";
  });
  document.getElementById("btnSubmitFarm").addEventListener("click", async () => {
    const name = document.getElementById("newFarmName").value.trim();
    if (!name) {
      alert("농가명을 입력해주세요.");
      return;
    }

    const payload = {
      farm_code: document.getElementById("newFarmCode").value.trim(),
      farm_name: name,
      owner_name: document.getElementById("newOwnerName").value.trim(),
      phone: document.getElementById("newPhone").value.trim(),
      address: document.getElementById("newAddress").value.trim(),
      breeding_type: document.getElementById("newBreedingType").value,
      total_heads: parseInt(document.getElementById("newTotalHeads").value) || 0
    };

    try {
      const res = await apiFetch(`${API_BASE}/api/farms`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const result = await res.json();
      if (result.success) {
        alert("신규 농가가 성공적으로 등록되었습니다!");
        modal.style.display = "none";
        await loadFarms();
        document.getElementById("farmSelect").value = result.farm_id;
        currentFarmId = result.farm_id;
        loadFarmDetail(currentFarmId);
      }
    } catch (err) {
      alert("등록 실패: " + err);
    }
  });
}

// 이벤트 리스너 바인딩
function initEventListeners() {
  // 농가 셀렉트 변경
  document.getElementById("farmSelect").addEventListener("change", (e) => {
    currentFarmId = e.target.value;
    loadFarmDetail(currentFarmId);
  });

  // 대시보드 새로고침
  document.getElementById("btnRefreshDashboard").addEventListener("click", () => {
    loadDashboard();
  });

  // 차트 칩 버튼
  document.querySelectorAll(".chart-controls .btn-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      document.querySelectorAll(".chart-controls .btn-chip").forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      currentMetric = chip.dataset.metric;
      renderBenchmarkChart(currentMetric);
    });
  });

  // 1단계: 축평원 이력번호 추출
  document.getElementById("btnFetchShipment").addEventListener("click", async () => {
    if (!currentFarmId) {
      alert("먼저 상단에서 농가를 선택해주세요.");
      return;
    }
    const text = document.getElementById("inputAnimalNumbers").value.trim();
    if (!text) {
      alert("조회할 개체이력번호를 입력해주세요.");
      return;
    }

    const animalNos = text.split(/[\n,]+/).map(s => s.trim()).filter(s => s.length >= 8);
    if (animalNos.length === 0) {
      alert("올바른 12자리 개체이력번호를 입력해주세요.");
      return;
    }

    const statusEl = document.getElementById("shipmentFetchStatus");
    statusEl.textContent = `축평원 OpenAPI에서 ${animalNos.length}두의 출하성적을 조회 중입니다...`;

    try {
      const res = await apiFetch(`${API_BASE}/api/shipment/lookup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ farm_id: currentFarmId, animal_numbers: animalNos })
      });
      const result = await res.json();
      if (result.success) {
        statusEl.innerHTML = `<span class="badge-status positive">완료: ${result.saved_count}두의 성적이 추출되어 DB에 누적 저장되었습니다!</span>`;
        loadFarmDetail(currentFarmId);
      } else {
        statusEl.textContent = "조회 실패: " + (result.error || "알 수 없는 오류");
      }
    } catch (err) {
      statusEl.textContent = "통신 오류: " + err;
    }
  });

  // 3 & 4단계: 현장조사 저장
  document.getElementById("btnSaveSurvey").addEventListener("click", async () => {
    if (!currentFarmId) {
      alert("먼저 농가를 선택해주세요.");
      return;
    }

    const feedData = {
      growing: document.querySelector('[data-field="feed_growing"] .active')?.dataset.val || "보통",
      early: document.querySelector('[data-field="feed_early"] .active')?.dataset.val || "보통",
      mid: document.querySelector('[data-field="feed_mid"] .active')?.dataset.val || "양호",
      late: document.querySelector('[data-field="feed_late"] .active')?.dataset.val || "보통"
    };

    const facilityData = {
      density: document.querySelector('[data-field="facility_density"] .active')?.dataset.val || "적정",
      ventilation: document.querySelector('[data-field="facility_ventilation"] .active')?.dataset.val || "보통",
      bedding: document.querySelector('[data-field="facility_bedding"] .active')?.dataset.val || "보통"
    };

    const payload = {
      farm_id: currentFarmId,
      visit_date: document.getElementById("surveyDate").value,
      consultant_name: document.getElementById("surveyConsultant").value,
      feed_data: feedData,
      facility_data: facilityData,
      farmer_dialogue: document.getElementById("inputFarmerDialogue").value,
      consultant_memo: document.getElementById("inputConsultantMemo").value
    };

    try {
      const res = await apiFetch(`${API_BASE}/api/survey/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const result = await res.json();
      if (result.success) {
        currentVisitId = result.visit_id;
        alert(`현장 방문 조사표(${result.visit_number}차 방문)가 성공적으로 DB에 저장되었습니다!`);
      }
    } catch (err) {
      alert("저장 실패: " + err);
    }
  });

  // 5단계: Claude AI 리포트 생성
  document.getElementById("btnGenerateReport").addEventListener("click", async () => {
    if (!currentFarmId) {
      alert("먼저 농가를 선택해주세요.");
      return;
    }

    const indicator = document.getElementById("aiLoadingIndicator");
    const container = document.getElementById("reportContainer");
    indicator.style.display = "block";
    container.innerHTML = "";

    try {
      const res = await apiFetch(`${API_BASE}/api/report/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ farm_id: currentFarmId, visit_id: currentVisitId })
      });
      const result = await res.json();
      indicator.style.display = "none";

      if (result.success && result.report_markdown) {
        container.innerHTML = marked.parse(result.report_markdown);
      } else {
        container.innerHTML = `<div class="status-msg negative">리포트 생성 실패: ${result.error || '오류 발생'}</div>`;
      }
    } catch (err) {
      indicator.style.display = "none";
      container.innerHTML = `<div class="status-msg negative">통신 오류: ${err}</div>`;
    }
  });

  // 리포트 인쇄
  document.getElementById("btnPrintReport").addEventListener("click", () => {
    window.print();
  });
}

// 누적 DB 뷰어 로드
async function loadDatabaseView() {
  try {
    const res = await apiFetch(`${API_BASE}/api/farms`);
    const farms = await res.json();
    const tbody = document.querySelector("#dbFarmsTable tbody");
    tbody.innerHTML = "";
    farms.forEach(f => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><code>${f.farm_code || '-'}</code></td>
        <td><strong>${f.farm_name}</strong></td>
        <td>${f.owner_name || '-'}</td>
        <td>${f.phone || '-'}</td>
        <td>${f.breeding_type || '비육우'}</td>
        <td>${f.total_heads || 0}두</td>
        <td><strong>${f.visit_count || 0}회</strong></td>
        <td>${f.shipment_count || 0}두</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("DB 로드 실패:", err);
  }
}

// 리포트 보기 팝업/전환
async function viewReport(visitId) {
  try {
    const res = await apiFetch(`${API_BASE}/api/reports/${visitId}`);
    const data = await res.json();
    if (data.full_markdown) {
      document.querySelector('[data-tab="ai-report"]').click();
      document.getElementById("reportContainer").innerHTML = marked.parse(data.full_markdown);
    } else {
      alert("해당 방문의 리포트가 존재하지 않습니다.");
    }
  } catch (err) {
    alert("리포트 로드 실패: " + err);
  }
}
