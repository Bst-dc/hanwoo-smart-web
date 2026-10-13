// 화면 전체가 같이 쓰는 것: API 호출, 알림, HTML 이스케이프, 현재 선택 상태.

// 화면을 API 와 다른 주소(예: Live Server)에서 열었을 때만 API 주소를 따로 적는다. 같은 서버면 빈 값.
const API_BASE = window.CONSULTING_API_BASE || "";

export const state = { farms: [], farmId: null, onUnauthorized: () => {} };

export async function api(path, options = {}) {
  const res = await fetch(API_BASE + path, {
    credentials: "include",                       // 로그인 쿠키
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    state.onUnauthorized();
    throw new Error("로그인이 필요합니다.");
  }
  const body = res.headers.get("content-type")?.includes("application/json") ? await res.json() : null;
  if (!res.ok) {
    const detail = body?.detail;
    const err = new Error(typeof detail === "string" ? detail
      : Array.isArray(detail) ? detail.map((d) => d.msg).join(" · ") : `요청 실패 (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return body;
}

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const num = (n) => Number(n).toLocaleString("ko-KR");
export const card = (inner, extra = "") => `<section class="rounded-2xl bg-white border border-line p-4 ${extra}">${inner}</section>`;

export function toast(message) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 3000);
}

// 브라우저 저장소는 막혀 있을 수 있어서(사생활 보호 창 등) 모든 읽기·쓰기를 감싼다.
export const store = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch { /* 저장 못 해도 화면은 동작한다 */ } },
};

// 표: columns 와 rows(배열의 배열)를 그린다. 숫자 열은 헤더와 값을 같이 가운데 정렬한다.
// align 으로 열마다 "left" | "center" | "right" 를 직접 정할 수 있다.
export function table({ columns, rows }, { fmt = {}, align = {}, empty = "데이터가 없습니다." } = {}) {
  if (!rows.length) return `<p class="text-sm text-muted">${esc(empty)}</p>`;
  const colAlign = columns.map((c, i) => align[c] ?? (rows.some((r) => typeof r[i] === "number") ? "center" : "left"));
  const cls = { left: "text-left", center: "text-center", right: "text-right" };
  const cell = (c, v) => (v === null || v === undefined || v === "" ? '<span class="text-muted">-</span>'
    : esc(fmt[c] ? fmt[c](v) : typeof v === "number" ? num(v) : v));
  return `<div class="table-wrap border border-line rounded-xl"><table class="w-full text-sm">
    <thead class="bg-panel"><tr>${columns.map((c, i) => `<th class="px-3 py-2 ${cls[colAlign[i]]} font-semibold whitespace-nowrap">${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r) => `<tr class="border-t border-line">${r.map((v, i) =>
      `<td class="px-3 py-2 whitespace-nowrap ${cls[colAlign[i]]} ${colAlign[i] === "left" ? "" : "kpi-value"}">${cell(columns[i], v)}</td>`).join("")}</tr>`).join("")}</tbody>
    </table></div>`;
}
