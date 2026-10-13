// 데이터 관리 · 백업 — 표 미리보기, CSV·DB 파일 내려받기, 신규 농가 등록.
// 범위는 위쪽 농가 선택을 따른다 ('전체 농가'면 전부). 열·파일 이름은 기존 앱과 같다.
import { api, card, esc, flash, num, table } from "../api.js";

const btn = "rounded-xl px-4 py-3 min-h-[48px] text-sm font-semibold disabled:opacity-50";
const inputCls = "w-full rounded-xl border border-line bg-white px-3 py-2";
const errBox = (m) => `<div class="rounded-xl border border-neg/40 bg-white p-3 mb-3 text-sm text-neg">⚠️ ${esc(m)}</div>`;
const BREEDING = ["비육우", "일관사육", "번식우"];
const form = { code: "", name: "", owner: "", region: "", breeding_type: "비육우", total_heads: 100, open: false };

function stat(label, value, unit) {
  return `<div class="rounded-2xl bg-white border border-line p-4"><div class="text-sm text-muted">${esc(label)}</div>
    <div class="kpi-value text-2xl font-bold mt-1">${num(value)} <span class="text-base font-semibold">${esc(unit)}</span></div></div>`;
}

function newFarmForm() {
  const seg = BREEDING.map((b) => `<button type="button" data-bt="${b}" class="bt px-3 py-2 min-h-[44px] rounded-xl border text-sm ${form.breeding_type === b ? "bg-brand text-white border-brand font-semibold" : "bg-white border-line text-muted"}">${b}</button>`).join("");
  return `
    <details id="nf" class="rounded-2xl bg-white border border-line p-4" ${form.open ? "open" : ""}>
      <summary class="cursor-pointer font-semibold">➕ 신규 농가 등록</summary>
      <form id="nf-form" class="mt-3 grid gap-3 sm:grid-cols-2" novalidate>
        <div><label class="block text-sm text-muted mb-1" for="nf-name">농가명 *</label><input id="nf-name" data-k="name" class="${inputCls}" value="${esc(form.name)}" placeholder="예: 한우사랑농장" maxlength="60" required></div>
        <div><label class="block text-sm text-muted mb-1" for="nf-code">조합원 번호</label><input id="nf-code" data-k="code" class="${inputCls}" value="${esc(form.code)}" placeholder="비우면 자동으로 붙습니다" maxlength="30"></div>
        <div><label class="block text-sm text-muted mb-1" for="nf-owner">대표자명</label><input id="nf-owner" data-k="owner" class="${inputCls}" value="${esc(form.owner)}" maxlength="30"></div>
        <div><label class="block text-sm text-muted mb-1" for="nf-region">지역</label><input id="nf-region" data-k="region" class="${inputCls}" value="${esc(form.region)}" placeholder="예: 경북 영천" maxlength="30"></div>
        <div><span class="block text-sm text-muted mb-1">사육형태</span><div class="flex flex-wrap gap-2">${seg}</div></div>
        <div><label class="block text-sm text-muted mb-1" for="nf-heads">사육두수</label><input id="nf-heads" data-k="total_heads" type="number" inputmode="numeric" min="0" class="${inputCls} kpi-value" value="${form.total_heads}"></div>
        <div id="nf-dup" class="sm:col-span-2"></div>
        <button id="nf-save" type="submit" class="${btn} sm:col-span-2 bg-brand text-white">신규 농가 저장</button>
      </form>
    </details>`;
}

function bindNewFarm(el, ctx) {
  const f = el.querySelector("#nf-form");
  const nf = el.querySelector("#nf");
  nf.addEventListener("toggle", () => { form.open = nf.open; });
  let dup = null, timer = null, seq = 0;
  const checkDup = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const mine = ++seq;                                     // 늦게 온 옛 응답이 새 결과를 덮지 않게
      const q = new URLSearchParams({ name: form.name.trim(), code: form.code.trim() });
      const found = (form.name.trim() || form.code.trim()) ? (await api(`/api/farms/duplicate?${q}`)).match : null;
      if (mine !== seq) return;
      dup = found;
      el.querySelector("#nf-dup").innerHTML = dup ? `
        <div class="rounded-xl border border-neg/40 bg-[#FBEDE8] p-3 text-sm text-neg">
          ⚠️ 이미 등록된 농가와 일치합니다 — <b>${esc(dup.name)}</b> (${esc(dup.owner || "대표자 미입력")}, ${esc(dup.region || "지역 미입력")}, 조합원번호 ${esc(dup.code || "미입력")}).
          <div class="mt-1">같은 농가라면 새로 등록하지 말고 위쪽 농가 선택에서 고르세요. 새로 저장하면 출하성적과 조사표가 서로 다른 농가로 쪼개집니다.</div>
          <label class="flex items-center gap-2 mt-2"><input id="nf-confirm" type="checkbox" class="h-5 w-5"> 그래도 별개의 새 농가로 등록합니다</label>
        </div>` : "";
    }, 300);
  };
  f.querySelectorAll("[data-k]").forEach((i) => i.addEventListener("input", () => {
    form[i.dataset.k] = i.value;
    if (i.dataset.k === "name" || i.dataset.k === "code") checkDup();
  }));
  f.querySelectorAll(".bt").forEach((b) => b.addEventListener("click", () => {
    form.breeding_type = b.dataset.bt;
    f.querySelectorAll(".bt").forEach((x) => {
      const on = x === b;
      x.classList.toggle("bg-brand", on); x.classList.toggle("text-white", on); x.classList.toggle("border-brand", on); x.classList.toggle("font-semibold", on);
      x.classList.toggle("bg-white", !on); x.classList.toggle("border-line", !on); x.classList.toggle("text-muted", !on);
    });
  }));
  if (form.name || form.code) checkDup();
  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!form.name.trim()) { flash(errBox("농가명을 넣어주세요.")); window.scrollTo(0, 0); return; }
    const confirm = el.querySelector("#nf-confirm");
    if (dup && !confirm?.checked) { flash(errBox("이미 등록된 농가와 일치합니다. 별개의 농가라면 확인란에 체크하세요.")); window.scrollTo(0, 0); return; }
    const save = el.querySelector("#nf-save");
    save.disabled = true; save.textContent = "저장 중…";
    try {
      const r = await api("/api/farms", { method: "POST", body: JSON.stringify({ ...form, total_heads: Number(form.total_heads) || 0, open: undefined, confirm_duplicate: !!confirm?.checked }) });
      Object.assign(form, { code: "", name: "", owner: "", region: "", breeding_type: "비육우", total_heads: 100, open: false });
      const b = r.backup;
      await ctx.onSaved();
      ctx.onPickFarm(r.id);                                   // 농가를 바꾸면 알림이 지워지므로 알림은 그 뒤에
      flash(`<div class="rounded-xl border border-brand-line bg-brand-tint p-3 mb-3 text-sm">✅ <b>${esc(r.name)}</b> 농가를 등록하고 선택했습니다. 이제 출하성적·현장조사를 입력할 수 있습니다.
        <div class="text-xs ${b.ok === false ? "text-neg" : "text-muted"} mt-1">${b.ok === true ? "☁️" : b.ok === false ? "⚠️" : "ℹ️"} ${esc(b.message)}</div></div>`);
      window.scrollTo(0, 0);
    } catch (ex) {
      flash(errBox(ex.message)); window.scrollTo(0, 0);
      save.disabled = false; save.textContent = "신규 농가 저장";
    }
  });
}

function preview(title, d, extraNote = "") {
  const shown = d.rows.length;
  return `<details class="rounded-2xl bg-white border border-line p-4">
    <summary class="cursor-pointer font-semibold">${esc(title)} <span class="text-sm font-normal text-muted">${num(d.count)}행${d.count > shown ? ` · 앞 ${num(shown)}행만 표시` : ""}</span></summary>
    ${extraNote}<div class="mt-3">${table({ columns: d.columns, rows: d.rows }, { empty: "자료가 없습니다." })}</div></details>`;
}

export async function renderData(el, ctx) {
  const { farm, isCurrent = () => true } = ctx;
  el.innerHTML = '<p class="text-sm text-muted">불러오는 중…</p>';
  const q = farm ? `?farm_id=${farm.id}` : "";
  const d = await api(`/api/data/summary${q}`);
  if (!isCurrent()) return;
  const scope = farm ? `<b>${esc(farm.name)}</b> 농가만` : "<b>전체 농가</b>";
  const reportRows = d.reports.rows.map((r) => {
    const o = Object.fromEntries(d.reports.columns.map((c, i) => [c, r[i]]));
    return `<li class="py-2 flex items-center justify-between gap-2"><span class="text-sm">${esc(o.farm_name)} · ${esc(o.visit_date)} · ${esc(o.report_mode)}</span>
      <a class="shrink-0 text-sm font-semibold text-brand underline" href="/api/reports/${o["리포트ID"]}/download?fmt=html&inline=1" target="_blank" rel="noopener">새 탭에서 보기</a></li>`;
  }).join("");

  el.innerHTML = `
    <h2 class="text-xl font-bold">데이터 관리 · 백업</h2>
    <p class="text-sm text-muted mt-1">범위: ${scope} — 위쪽 농가 선택에서 '전체 농가'를 고르면 모든 농가를 봅니다.</p>
    <div class="mt-4">${newFarmForm()}</div>
    <div class="grid grid-cols-2 gap-3 mt-4">
      ${stat("농가", d.farms.count, "곳")}${stat("출하성적", d.shipments.count, "두")}
      ${stat("현장 방문", d.visits.count, "회")}${stat("AI 리포트", d.reports.count, "개")}
    </div>
    <h3 class="text-base font-bold mt-6 mb-2">📥 내려받기</h3>
    ${card(`
      <div class="grid gap-2 sm:grid-cols-3">
        <a class="${btn} border border-line bg-white text-center" href="/api/data/export/farms${q}">농가 목록 CSV</a>
        <a class="${btn} border border-line bg-white text-center" href="/api/data/export/shipments${q}">출하성적 CSV</a>
        <a class="${btn} border border-line bg-white text-center" href="/api/data/export/visits${q}">현장 방문 이력 CSV</a>
      </div>
      <p class="text-xs text-muted mt-2">엑셀에서 바로 열 수 있습니다 (한글 깨짐 없음). ${farm ? "지금은 이 농가 것만 받습니다." : ""}</p>
      <hr class="my-4 border-line">
      <div class="font-semibold">💾 전체 DB 파일 백업 (.db)</div>
      <p class="text-sm text-muted mt-1">농가·방문·조사표·출하성적·AI 리포트 전체를 파일 하나로 받습니다. <b class="text-neg">조합원 정보가 들어 있으니 보관에 주의하세요.</b> 위 농가 선택과 상관없이 전체를 받습니다.</p>
      <a id="db-dl" class="${btn} mt-3 inline-flex items-center justify-center border border-line bg-white" href="/api/data/db-file">DB 파일 받기 (몇 초 걸림)</a>`)}
    <h3 class="text-base font-bold mt-6 mb-2">📋 자료 보기</h3>
    <div class="space-y-3">
      ${preview("농가 목록", d.farms)}
      ${preview("출하성적 (도축일 최신 순)", d.shipments)}
      ${preview("현장 방문 이력", d.visits, '<p class="text-xs text-muted mt-2">긴 원본 글은 앞 40자만 보입니다. 전체는 CSV 로 받으세요. 고치기는 현장조사 메뉴에서 합니다.</p>')}
      <details class="rounded-2xl bg-white border border-line p-4" ${d.reports.count ? "" : ""}>
        <summary class="cursor-pointer font-semibold">AI 리포트 <span class="text-sm font-normal text-muted">${num(d.reports.count)}개</span></summary>
        ${d.reports.count ? `<ul class="divide-y divide-line mt-2">${reportRows}</ul>` : '<p class="text-sm text-muted mt-2">저장된 AI 리포트가 없습니다.</p>'}
      </details>
    </div>`;
  bindNewFarm(el, ctx);
}
