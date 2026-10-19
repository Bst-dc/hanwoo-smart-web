// web/survey_draft.js 시험 (node --test). localStorage 대신 Map 으로 만든 가짜 저장소를 쓴다.
import assert from "node:assert/strict";
import { test } from "node:test";
import { clearDraft, draftKey, listDrafts, mergeValues, readDraft, writeDraft } from "../../web/survey_draft.js";

function fakeStorage({ full = false } = {}) {
  const m = new Map();
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => { if (full) throw new Error("QuotaExceededError"); m.set(k, String(v)); },
    removeItem: (k) => m.delete(k),
    key: (i) => [...m.keys()][i] ?? null,
    get length() { return m.size; },
    _m: m,
  };
}

test("새 조사와 기존 방문은 다른 칸에 저장되고, 농가가 다르면 섞이지 않는다", () => {
  const s = fakeStorage();
  assert.equal(draftKey(3, null), "survey-draft:3:new");
  assert.equal(draftKey(3, 41), "survey-draft:3:41");
  writeDraft(s, 3, null, { a: "새" }, 100);
  writeDraft(s, 3, 41, { a: "고침" }, 200);
  writeDraft(s, 30, null, { a: "다른 농가" }, 300);       // 3 과 30 은 접두어가 겹치지만 다른 농가
  assert.deepEqual(readDraft(s, 3, null).values, { a: "새" });
  assert.deepEqual(readDraft(s, 3, 41).values, { a: "고침" });
  assert.deepEqual(listDrafts(s, 3).map((d) => d.visitId), [41, null]);   // 최근 것부터
  assert.deepEqual(listDrafts(s, 30).map((d) => d.values.a), ["다른 농가"]);
});

test("지우면 그 칸만 지워진다", () => {
  const s = fakeStorage();
  writeDraft(s, 3, null, { a: 1 });
  writeDraft(s, 3, 41, { a: 2 });
  clearDraft(s, 3, null);
  assert.equal(readDraft(s, 3, null), null);
  assert.ok(readDraft(s, 3, 41));
});

test("깨진 값·다른 앱의 키·막힌 저장소에서도 오류 없이 없는 것으로 본다", () => {
  const s = fakeStorage();
  s.setItem("survey-draft:3:new", "{깨짐");
  s.setItem("farmId", "3");
  assert.equal(readDraft(s, 3, null), null);
  assert.deepEqual(listDrafts(s, 3), []);
  assert.equal(writeDraft(null, 3, null, { a: 1 }), false);
  assert.equal(readDraft(null, 3, null), null);
  assert.deepEqual(listDrafts(null, 3), []);
  assert.doesNotThrow(() => clearDraft(null, 3, null));
  assert.equal(writeDraft(fakeStorage({ full: true }), 3, null, { a: 1 }), false);   // 가득 차도 화면은 계속 동작
});

test("서버 값 위에 임시본을 얹을 때 새로 생긴 칸과 사료표 칸이 빠지지 않는다", () => {
  const base = { farmName: "", region: "대구", newField: 0,
    feed_matrix: { 육성기: { "배합사료 품목": "", "조사료 품목": "" }, 비육전기: { "배합사료 품목": "" } } };
  const draft = { farmName: "임시", region: "경북", feed_matrix: { 육성기: { "배합사료 품목": "팔공" } } };
  const m = mergeValues(base, draft);
  assert.equal(m.farmName, "임시");
  assert.equal(m.newField, 0);                              // 양식에 새로 생긴 칸
  assert.deepEqual(m.feed_matrix.육성기, { "배합사료 품목": "팔공", "조사료 품목": "" });
  assert.deepEqual(m.feed_matrix.비육전기, { "배합사료 품목": "" });
  assert.equal(base.feed_matrix.육성기["배합사료 품목"], "");   // 원래 값은 바꾸지 않는다
});
