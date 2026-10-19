// 현장조사 임시 저장 — 저장 전 입력을 브라우저 저장소에 남겨, 농가 전환·축사 신호 끊김·폰이 탭을 정리해도 입력이 날아가지 않게 한다.
// 서버 저장에 성공하거나 '저장하지 않고 나가기'를 고르면 지운다. 화면을 모르는 순수 함수만 둔다.
// storage 는 localStorage 처럼 getItem/setItem/removeItem/key/length 를 가진 것 (막힌 환경이면 null — 그때는 아무것도 하지 않는다).
export const PREFIX = "survey-draft:";

export const draftKey = (farmId, visitId) => `${PREFIX}${farmId}:${visitId ?? "new"}`;

export function writeDraft(storage, farmId, visitId, values, now = Date.now()) {
  if (!storage || !values) return false;
  try {
    storage.setItem(draftKey(farmId, visitId), JSON.stringify({ v: 1, at: now, farmId, visitId: visitId ?? null, values }));
    return true;
  } catch { return false; }                         // 저장소가 가득 찼거나 막힘 — 화면은 그대로 동작한다
}

export function readDraft(storage, farmId, visitId) {
  if (!storage) return null;
  try {
    const d = JSON.parse(storage.getItem(draftKey(farmId, visitId)) || "null");
    return d && typeof d.values === "object" && d.values ? d : null;
  } catch { return null; }                          // 깨진 값은 없는 것으로 본다
}

export function clearDraft(storage, farmId, visitId) {
  if (!storage) return;
  try { storage.removeItem(draftKey(farmId, visitId)); } catch { /* 무시 */ }
}

// 그 농가의 임시본 전부, 최근 것부터
export function listDrafts(storage, farmId) {
  if (!storage) return [];
  const head = `${PREFIX}${farmId}:`;
  const out = [];
  try {
    for (let i = 0; i < storage.length; i++) {
      const k = storage.key(i);
      if (!k || !k.startsWith(head)) continue;
      const rest = k.slice(head.length);
      const d = readDraft(storage, farmId, rest === "new" ? null : Number(rest));
      if (d) out.push(d);
    }
  } catch { return []; }
  return out.sort((a, b) => b.at - a.at);
}

// 서버 값(빈 양식 또는 저장된 조사표) 위에 임시본을 얹는다. 양식에 새 칸이 생겼어도 빠지지 않고, 사료표는 단계·칸 단위로 합친다.
export function mergeValues(base, draft) {
  const out = { ...base, ...draft };
  if (base?.feed_matrix || draft?.feed_matrix) {
    const fm = {};
    for (const stage of new Set([...Object.keys(base?.feed_matrix || {}), ...Object.keys(draft?.feed_matrix || {})])) {
      fm[stage] = { ...(base?.feed_matrix?.[stage] || {}), ...(draft?.feed_matrix?.[stage] || {}) };
    }
    out.feed_matrix = fm;
  }
  return out;
}

export function fmtTime(ms) {
  const d = new Date(ms);
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getMonth() + 1)}/${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
