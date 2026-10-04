// 한우 스마트 컨설팅 (GitHub Pages 서버리스 버전)

const STORAGE_KEY = "hanwoo_consulting_db_v1";
let db = loadDB();
let currentFarmId = db.farms[0]?.id || null;
let benchmarkChart = null;
let currentMetric = "avg_weight";

const NATIONAL_BENCHMARKS = {
  "거세": {
    "도체중": { 2023: 467.0, 2024: 470.6, 2025: 478.1, 2026: 490.4 },
    "BMS": { 2023: 6.2, 2024: 6.2, 2025: 6.3, 2026: 7.0 },
    "등지방": { 2023: 12.7, 2024: 12.3, 2025: 12.4, 2026: 12.5 },
    "단면적": { 2023: 97.7, 2024: 97.6, 2025: 100.3, 2026: 106.7 },
    "출하월령": { 2023: 31.1, 2024: 31.6, 2025: 31.7, 2026: 31.7 },
    "rate_1plus_above": { 2023: 69.1, 2024: 68.9, 2025: 71.3, 2026: 74.2 },
  }
};

function loadDB() {
  const data = localStorage.getItem(STORAGE_KEY);
  if (data) {
    try { return JSON.parse(data); } catch(e) {}
  }
  // 초기 빈 데이터베이스
  const initial = {
    farms: [],
    visits: [],
    surveys: {},
    shipments: [],
    reports: {}
  };
  saveDB(initial);
  return initial;
}

function saveDB(data) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  db = data;
}

document.addEventListener("DOMContentLoaded", () => {
  initNavigation();
  loadFarms();
  loadDashboard();
  initRatingButtons();
  initModals();
  initEvents();
});

function initNavigation() {
  document.querySelectorAll(".nav-item").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
      if (btn.dataset.tab === "dashboard") loadDashboard();
      if (btn.dataset.tab === "database") loadDatabaseView();
      if (btn.dataset.tab === "ai-report") checkMissingData();
    });
  });
}

function loadFarms() {
  const select = document.getElementById("farmSelect");
  select.innerHTML = '<option value="">농가를 선택하세요...</option>';
  db.farms.forEach(f => {
    const opt = document.createElement("option");
    opt.value = f.id;
    opt.textContent = `${f.farm_name} (${f.owner_name}, ${f.total_heads}두)`;
    select.appendChild(opt);
  });
  if (currentFarmId) {
    select.value = currentFarmId;
    loadFarmDetail(currentFarmId);
  }
}

function loadDashboard() {
  document.getElementById("kpiTotalFarms").textContent = `${db.farms.length} 농가`;
  document.getElementById("kpiTotalVisits").textContent = `${db.visits.length} 회`;
  document.getElementById("kpiTotalShipments").textContent = `${db.shipments.length} 두`;

  const total = db.shipments.length;
  const plusCount = db.shipments.filter(s => s.grade_quality === "1++" || s.grade_quality === "1+").length;
  const rate = total > 0 ? (plusCount * 100 / total).toFixed(1) : "0.0";
  document.getElementById("kpiAvg1PlusRate").textContent = `${rate}%`;

  // 연도별 집계
  const yearlyMap = {};
  db.shipments.forEach(s => {
    const y = s.slaughter_year || 2025;
    if (!yearlyMap[y]) yearlyMap[y] = { count: 0, farms: new Set(), weight: [], bms: [], plus: 0 };
    yearlyMap[y].count++;
    yearlyMap[y].farms.add(s.farm_id);
    if (s.carcass_weight) yearlyMap[y].weight.push(s.carcass_weight);
    if (s.bms) yearlyMap[y].bms.push(s.bms);
    if (s.grade_quality === "1++" || s.grade_quality === "1+") yearlyMap[y].plus++;
  });

  const tbody = document.querySelector("#yearlyTable tbody");
  tbody.innerHTML = "";
  Object.keys(yearlyMap).sort().forEach(y => {
    const d = yearlyMap[y];
    const avgW = d.weight.length ? (d.weight.reduce((a,b)=>a+b,0)/d.weight.length).toFixed(1) : "-";
    const avgB = d.bms.length ? (d.bms.reduce((a,b)=>a+b,0)/d.bms.length).toFixed(1) : "-";
    const rPlus = (d.plus * 100 / d.count).toFixed(1);
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${y}년</strong></td>
      <td>${d.farms.size}</td>
      <td>${d.count}두</td>
      <td><strong>${avgW} kg</strong></td>
      <td>${avgB}</td>
      <td><span class="badge-status positive">${rPlus}%</span></td>
    `;
    tbody.appendChild(tr);
  });

  renderChart(currentMetric, yearlyMap);
}

function renderChart(metric, yearlyMap) {
  const ctx = document.getElementById("benchmarkChart").getContext("2d");
  const years = [2023, 2024, 2025, 2026];
  const nat = NATIONAL_BENCHMARKS["거세"];

  const natMap = {
    avg_weight: years.map(y => nat["도체중"][y]),
    avg_bms: years.map(y => nat["BMS"][y]),
    rate_1plus_above: years.map(y => nat["rate_1plus_above"][y])
  };

  const farmValues = years.map(y => {
    const d = yearlyMap[y];
    if (!d) return null;
    if (metric === "avg_weight") return d.weight.length ? (d.weight.reduce((a,b)=>a+b,0)/d.weight.length).toFixed(1) : null;
    if (metric === "avg_bms") return d.bms.length ? (d.bms.reduce((a,b)=>a+b,0)/d.bms.length).toFixed(1) : null;
    if (metric === "rate_1plus_above") return (d.plus * 100 / d.count).toFixed(1);
  });

  if (benchmarkChart) benchmarkChart.destroy();

  benchmarkChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: years.map(y => `${y}년`),
      datasets: [
        { label: "전국 평균", data: natMap[metric], borderColor: "#94a3b8", borderDash: [5, 5], tension: 0.2 },
        { label: "방문농가 전체 평균 (누적DB)", data: farmValues, borderColor: "#2563eb", borderWidth: 3, tension: 0.3 }
      ]
    },
    options: { responsive: true, maintainAspectRatio: false }
  });
}

function loadFarmDetail(farmId) {
  const fShipments = db.shipments.filter(s => s.farm_id === Number(farmId));
  const tbody = document.querySelector("#comparisonTable tbody");
  tbody.innerHTML = "";

  if (fShipments.length > 0) {
    const weights = fShipments.map(s => s.carcass_weight).filter(Boolean);
    const bmsList = fShipments.map(s => s.bms).filter(Boolean);
    const plusCount = fShipments.filter(s => s.grade_quality === "1++" || s.grade_quality === "1+").length;

    const avgW = weights.length ? (weights.reduce((a,b)=>a+b,0)/weights.length).toFixed(1) : null;
    const avgB = bmsList.length ? (bmsList.reduce((a,b)=>a+b,0)/bmsList.length).toFixed(1) : null;
    const plusRate = (plusCount * 100 / fShipments.length).toFixed(1);

    const nat = NATIONAL_BENCHMARKS["거세"];
    const rows = [
      { name: "도체중", farm: avgW, nat: nat["도체중"][2025], unit: "kg" },
      { name: "근내지방도(BMS)", farm: avgB, nat: nat["BMS"][2025], unit: "점" },
      { name: "1+이상 출현율", farm: plusRate, nat: nat["rate_1plus_above"][2025], unit: "%" },
    ];

    rows.forEach(r => {
      const diff = r.farm ? (r.farm - r.nat).toFixed(1) : "-";
      const badge = diff > 0 ? "positive" : "negative";
      const status = diff > 0 ? "우수" : "미흡";
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${r.name}</strong></td>
        <td>${r.farm} ${r.unit}</td>
        <td>${r.nat} ${r.unit}</td>
        <td><strong>${diff > 0 ? '+'+diff : diff}</strong></td>
        <td><span class="badge-status ${badge}">${status}</span></td>
      `;
      tbody.appendChild(tr);
    });
  } else {
    tbody.innerHTML = '<tr><td colspan="5" class="text-center">등록된 출하성적이 없습니다.</td></tr>';
  }

  // 개체 목록
  const sTable = document.querySelector("#shipmentRecordsTable tbody");
  sTable.innerHTML = "";
  fShipments.forEach(s => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${s.animal_no}</strong></td>
      <td>${s.slaughter_date || '-'}</td>
      <td>${s.carcass_weight || '-'} kg</td>
      <td><span class="badge-status positive">${s.grade_quality || '-'}</span></td>
      <td>${s.bms || '-'}</td>
      <td>${s.backfat || '-'} mm</td>
      <td>${s.ribeye || '-'} ㎠</td>
      <td>${s.month_age || '-'}개월</td>
    `;
    sTable.appendChild(tr);
  });
}

function initRatingButtons() {
  document.querySelectorAll(".btn-group-rating").forEach(g => {
    g.querySelectorAll(".btn-rate").forEach(b => {
      b.addEventListener("click", () => {
        g.querySelectorAll(".btn-rate").forEach(x => x.classList.remove("active"));
        b.classList.add("active");
      });
    });
  });
}

function initModals() {
  const modal = document.getElementById("modalNewFarm");
  document.getElementById("btnNewFarmModal").onclick = () => modal.style.display = "flex";
  document.getElementById("btnCloseModal").onclick = () => modal.style.display = "none";
  document.getElementById("btnCancelFarm").onclick = () => modal.style.display = "none";

  document.getElementById("btnSubmitFarm").onclick = () => {
    const name = document.getElementById("newFarmName").value.trim();
    if (!name) return alert("농가명을 입력해주세요.");
    const newId = (db.farms[db.farms.length - 1]?.id || 0) + 1;
    db.farms.push({
      id: newId,
      farm_code: `F${newId + 1000}`,
      farm_name: name,
      owner_name: document.getElementById("newOwnerName").value.trim() || "대표자",
      breeding_type: "비육우",
      total_heads: Number(document.getElementById("newTotalHeads").value) || 100
    });
    saveDB(db);
    modal.style.display = "none";
    loadFarms();
    document.getElementById("farmSelect").value = newId;
    currentFarmId = newId;
    loadFarmDetail(newId);
    alert("농가가 등록되었습니다!");
  };

  // API 키 설정
  document.getElementById("btnSetApiKey").onclick = () => {
    const key = prompt("Anthropic Claude API 키를 입력하세요 (브라우저에만 안전하게 저장됩니다):", localStorage.getItem("claude_api_key") || "");
    if (key !== null) {
      localStorage.setItem("claude_api_key", key.trim());
      alert("API 키가 저장되었습니다!");
    }
  };
}

function initEvents() {
  document.getElementById("farmSelect").onchange = (e) => {
    currentFarmId = e.target.value;
    loadFarmDetail(currentFarmId);
  };

  document.querySelectorAll(".chart-controls .btn-chip").forEach(c => {
    c.onclick = () => {
      document.querySelectorAll(".chart-controls .btn-chip").forEach(x => x.classList.remove("active"));
      c.classList.add("active");
      currentMetric = c.dataset.metric;
      loadDashboard();
    };
  });

  // 이력번호 입력 시뮬레이션
  document.getElementById("btnFetchShipment").onclick = () => {
    if (!currentFarmId) return alert("농가를 선택하세요.");
    const val = document.getElementById("inputAnimalNumbers").value.trim();
    if (!val) return alert("이력번호를 입력하세요.");
    const nos = val.split(/[\n,]+/).map(s=>s.trim()).filter(Boolean);

    nos.forEach((no, idx) => {
      db.shipments.push({
        farm_id: Number(currentFarmId),
        animal_no: no,
        slaughter_date: "2026-03-15",
        slaughter_year: 2026,
        carcass_weight: 480 + (idx * 5),
        grade_quality: idx % 2 === 0 ? "1++" : "1+",
        bms: 7.0 + (idx * 0.5),
        backfat: 12.0,
        ribeye: 102.0,
        month_age: 31.0
      });
    });
    saveDB(db);
    document.getElementById("shipmentFetchStatus").innerHTML = `<span class="badge-status positive">${nos.length}두 성적 저장 완료!</span>`;
    loadFarmDetail(currentFarmId);
  };

  // 현장조사 저장
  document.getElementById("btnSaveSurvey").onclick = () => {
    if (!currentFarmId) return alert("농가를 선택하세요.");
    const vId = (db.visits[db.visits.length - 1]?.id || 0) + 1;
    db.visits.push({
      id: vId,
      farm_id: Number(currentFarmId),
      visit_number: db.visits.filter(v => v.farm_id === Number(currentFarmId)).length + 1,
      visit_date: new Date().toISOString().split("T")[0],
      consultant_name: "배성태 컨설턴트"
    });
    db.surveys[vId] = {
      dialogue: document.getElementById("inputFarmerDialogue").value,
      memo: document.getElementById("inputConsultantMemo").value
    };
    saveDB(db);
    alert("현장조사가 브라우저 DB에 저장되었습니다!");
  };

  // Claude AI 리포트 생성
  document.getElementById("btnGenerateReport").onclick = async () => {
    const apiKey = localStorage.getItem("claude_api_key");
    const container = document.getElementById("reportContainer");
    const indicator = document.getElementById("aiLoadingIndicator");

    const farm = db.farms.find(f => f.id === Number(currentFarmId));
    const farmName = farm ? farm.farm_name : "농가";

    if (!apiKey) {
      // 로컬 기본 리포트 템플릿 즉시 렌더링
      container.innerHTML = marked.parse(`
# 📋 [${farmName}] 한우 맞춤형 AI 종합 컨설팅 보고서
- **조사일자**: ${new Date().toLocaleDateString()} | **컨설턴트**: 배성태 수석 컨설턴트
- **분석 상태**: 오프라인 템플릿 모드 (상단 'Claude API 키 설정' 시 실시간 심층 AI 생성 지원)

---
## ⚡ 1. 핵심 진단 요약
- **도체중**: 전국 평균 대비 우수 수준 유지 중
- **마블링(BMS)**: 육성기 양질 조사료 보강 시 1++ 출현율 추가 15%p 상승 여력 확인
- **사양관리**: 비육후기 고열량 사료 급여 프로그램 최적화 필요

---
## 💡 2. 개선 처방 및 실행 로드맵
1. **1단계 (즉시)**: 비육중기 배합사료 2.0% 정밀 통제
2. **2단계 (1~3개월)**: 송아지/육성기 조사료 무제한 급여 환경 조성
3. **3단계 (출하 전)**: 비타민C 및 글리세롤 투여로 수송 감량 10kg 방지
      `);
      return;
    }

    indicator.style.display = "block";
    try {
      const resp = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
          "x-api-key": apiKey,
          "anthropic-version": "2023-06-01",
          "content-type": "application/json"
        },
        body: JSON.stringify({
          model: "claude-3-haiku-20240307",
          max_tokens: 3000,
          messages: [{ role: "user", content: `${farmName} 농가의 한우 출하성적 및 현장 사양관리 개선 종합 리포트를 7단 구성 마크다운으로 작성해줘.` }]
        })
      });
      const data = await resp.json();
      indicator.style.display = "none";
      const text = data.content?.[0]?.text || "리포트 생성 실패";
      container.innerHTML = marked.parse(text);
    } catch(err) {
      indicator.style.display = "none";
      alert("AI 통신 오류: " + err);
    }
  };

  document.getElementById("btnPrintReport").onclick = () => window.print();

  // 백업
  document.getElementById("btnExportJson").onclick = () => {
    const blob = new Blob([JSON.stringify(db, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `한우컨설팅_누적DB_${new Date().toISOString().split("T")[0]}.json`;
    a.click();
  };

  document.getElementById("btnResetSample").onclick = () => {
    if (confirm("데이터를 초기 샘플 상태로 복원하시겠습니까?")) {
      localStorage.removeItem(STORAGE_KEY);
      db = loadDB();
      loadFarms();
      loadDashboard();
      alert("샘플 데이터로 복원되었습니다.");
    }
  };
}

function loadDatabaseView() {
  const tbody = document.querySelector("#dbFarmsTable tbody");
  tbody.innerHTML = "";
  db.farms.forEach(f => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><code>${f.farm_code}</code></td>
      <td><strong>${f.farm_name}</strong></td>
      <td>${f.owner_name}</td>
      <td>${f.breeding_type}</td>
      <td>${f.total_heads}두</td>
    `;
    tbody.appendChild(tr);
  });
}

function checkMissingData() {
  const missingCard = document.getElementById("missingDataAlertCard");
  const missingTableBody = document.querySelector("#missingDataFarmsTable tbody");
  const missingCountBadge = document.getElementById("missingDataCountBadge");

  if (!missingCard || !missingTableBody || !missingCountBadge) return;

  // 출하 성적이 있는 농가 ID 목록 추출
  const farmsWithShipments = [...new Set(db.shipments.map(s => s.farm_id))];

  // 현장 조사(visits/surveys)가 있는 농가 ID 목록 추출
  const farmsWithSurveys = new Set(
    db.visits.filter(v => db.surveys[v.id]).map(v => v.farm_id)
  );

  // 출하 성적은 있으나 현장 조사가 없는 농가 목록 도출
  const missingFarmIds = farmsWithShipments.filter(farmId => !farmsWithSurveys.has(farmId));

  if (missingFarmIds.length > 0) {
    missingCard.style.display = "block";
    missingCountBadge.textContent = `누락 ${missingFarmIds.length}건`;
    missingTableBody.innerHTML = "";

    missingFarmIds.forEach(farmId => {
      const farm = db.farms.find(f => f.id === farmId);
      if (farm) {
        const shipmentCount = db.shipments.filter(s => s.farm_id === farmId).length;
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td><code>${farm.farm_code}</code></td>
          <td><strong>${farm.farm_name}</strong></td>
          <td>${farm.owner_name}</td>
          <td>${shipmentCount}두</td>
          <td>
            <button class="btn btn-outline btn-sm" onclick="goToSurveyTab(${farm.id})">조사 입력하기</button>
          </td>
        `;
        missingTableBody.appendChild(tr);
      }
    });
  } else {
    missingCard.style.display = "none";
  }
}

function goToSurveyTab(farmId) {
  const select = document.getElementById("farmSelect");
  if (select) select.value = farmId;
  currentFarmId = farmId;
  loadFarmDetail(farmId);
  
  // 현장조사 탭으로 이동
  const surveyBtn = document.querySelector('.nav-item[data-tab="field-survey"]');
  if (surveyBtn) surveyBtn.click();
}
