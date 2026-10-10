// 화면 전체가 같이 쓰는 것: API 호출, 알림, HTML 이스케이프, 현재 선택 상태.

// 화면을 API 와 다른 주소(예: Live Server)에서 열었을 때만 API 주소를 따로 적는다. 같은 서버면 빈 값.
const API_BASE = window.HANWOO_API_BASE || "";

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
    const err = new Error(typeof body?.detail === "string" ? body.detail : `요청 실패 (${res.status})`);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return body;
}

// 저장 결과 안내 (기존 앱 notify_saved/show_flash): 저장 성공 문구 + GitHub 백업 결과.
// 백업은 ok=true 성공, false 실패(데이터는 저장됨 — 눈에 띄게), null 미설정.
export function notifySaved(message, backup) {
  const el = document.getElementById("flash");
  const b = backup || { ok: null, message: "" };
  const backupLine = b.ok === true ? `<p class="text-xs text-muted mt-1">☁️ ${esc(b.message)}</p>`
    : b.ok === false ? `<p class="text-sm text-neg font-semibold mt-1">⚠️ ${esc(b.message)}</p>`
    : b.message ? `<p class="text-xs text-muted mt-1">ℹ️ ${esc(b.message)}</p>` : "";
  el.innerHTML = `<div class="rounded-xl border ${b.ok === false ? "border-neg/50" : "border-brand/40"} bg-white p-3 mb-4 flex gap-3 items-start">
    <div class="flex-1"><p class="text-sm font-semibold text-brand">✅ ${esc(message)}</p>${backupLine}</div>
    <button class="text-muted text-sm px-1" aria-label="닫기">✕</button></div>`;
  el.querySelector("button").addEventListener("click", () => { el.innerHTML = ""; });
}

export function toast(message) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 3000);
}

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
