"""출하성적 성별 고치기 (운영 DB) — 서버의 consulting-next 컨테이너 안에서 실행한다.

입력(표준입력, JSON): [{"animal_no": "...", "from": "암", "to": "거세"}, ...]
- from: 지금 DB 에 있어야 하는 값. 하나라도 다르면 아무것도 고치지 않고 멈춘다 (그사이 바뀐 행을 덮어쓰지 않게).
- gender 칸만 고친다. 다른 칸은 건드리지 않는다.

순서: 확인 → (--apply 일 때만) 백업 2곳(컨테이너 /tmp 의 .db 파일, GitHub 비공개 데이터 저장소) → 한 번에 고침(전부 되거나 전부 취소) → 다시 읽어 검증 → GitHub 백업.

실행 예:
  미리보기:  sudo docker compose exec -T consulting-next python -m tools.fix_gender < fix.json
  고치기:    sudo docker compose exec -T consulting-next python -m tools.fix_gender --apply < fix.json
  백업 꺼내기: sudo docker compose cp consulting-next:/tmp/<파일> ./
"""
import argparse
import datetime
import json
import logging
import sys

from api import backup, db

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
GENDERS = {"거세", "암", "수"}


def load(stream) -> list[dict]:
    rows = json.load(stream)
    bad = [r for r in rows if r.get("from") not in GENDERS or r.get("to") not in GENDERS or not r.get("animal_no")]
    if bad:
        sys.exit(f"입력 오류: 성별은 거세/암/수, 이력번호는 필수입니다. 예: {bad[0]}")
    if len({r["animal_no"] for r in rows}) != len(rows):
        sys.exit("입력 오류: 같은 이력번호가 두 번 있습니다.")
    return rows


def current(conn, nos: list[str]) -> dict:
    sql = f"SELECT animal_no, gender FROM shipment_records WHERE animal_no IN ({','.join('?' * len(nos))})"
    return {r[0]: r[1] for r in conn.execute(sql, nos).fetchall()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 고친다 (없으면 미리보기만)")
    args = ap.parse_args()
    rows = load(sys.stdin)
    nos = [r["animal_no"] for r in rows]
    if not db.using_supabase():
        sys.exit("운영 DB(Supabase)에 연결되어 있지 않습니다. consulting-next 컨테이너 안에서 실행하세요.")

    conn = db.connect()
    try:
        now = current(conn, nos)
        missing = [n for n in nos if n not in now]
        differ = [r for r in rows if r["animal_no"] in now and now[r["animal_no"]] != r["from"]]
        print(f"대상 {len(rows)}두 · DB 에 없음 {len(missing)} · 지금 값이 예상과 다름 {len(differ)}")
        for r in differ[:10]:
            print(f"  다름: {r['animal_no']} 예상 {r['from']} / 지금 {now[r['animal_no']]}")
        if missing or differ:
            sys.exit("멈춤: 예상과 다른 행이 있어 아무것도 고치지 않았습니다.")
        plan = {}
        for r in rows:
            plan[(r["from"], r["to"])] = plan.get((r["from"], r["to"]), 0) + 1
        print("바꿀 내용:", ", ".join(f"{a}→{b} {n}두" for (a, b), n in sorted(plan.items())))
        if not args.apply:
            print("미리보기만 했습니다. 고치려면 --apply 를 붙여 다시 실행하세요.")
            return

        # 1) 백업
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = f"/tmp/hanwoo_before_gender_fix_{stamp}.db"
        db.db_adapter.export_to_sqlite(db.db_schema.SCHEMA, path, db.db_schema.SQLITE_DDL, db.db_schema.TABLES)
        print(f"백업 파일: {path}")
        gh = backup.run("성별 고치기 전 백업")
        print(f"GitHub 백업: {gh['message']}")
        if gh["ok"] is not True:
            sys.exit("멈춤: GitHub 백업이 되지 않아 고치지 않았습니다. (백업 파일은 위 경로에 있습니다)")

        # 2) 고치기 — 전부 되거나 전부 취소
        try:
            for r in rows:
                cur = conn.execute("UPDATE shipment_records SET gender = ? WHERE animal_no = ? AND gender = ?",
                                   (r["to"], r["animal_no"], r["from"]))
                if cur.rowcount != 1:
                    raise RuntimeError(f"{r['animal_no']} 행이 {cur.rowcount}개 바뀜")
            conn.commit()
        except Exception as e:
            conn.rollback()
            sys.exit(f"멈춤: 고치는 중 오류가 나서 모두 되돌렸습니다 ({e}).")

        # 3) 검증
        db.db_adapter.clear_cache()
        after = current(conn, nos)
        ok = sum(after[r["animal_no"]] == r["to"] for r in rows)
        print(f"검증: {ok}/{len(rows)}두가 바른 값입니다.")
        gh = backup.run("출하성적 성별 고침")
        print(f"GitHub 백업: {gh['message']}")
        print(f"백업 파일 꺼내기: sudo docker compose cp consulting-next:{path} ./")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
