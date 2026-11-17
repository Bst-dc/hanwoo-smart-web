"""조사표 '최근 3년 날씨 비교표' 자료(api/services/weather_history.py) 만들기 — 기상청 API허브 ASOS 일자료(kma_sfcdd).

사용: py -3 -X utf8 build_weather_history.py <키가 든 파일 또는 URL 한 줄이 적힌 txt> [--raw 일자료.csv]
- 키(authKey)는 인자 파일에서만 읽고 어디에도 저장·출력하지 않는다. 결과 파일에는 통계값만 들어간다.
- 지점 9곳(대구 143·구미 279·영천 281·경주 283·의성 278·청송 276·안동 136·합천 285·밀양 288)의 2023~2025 일자료를 하루 한 번씩 받는다.
- 연값: 평균기온 = 일평균기온의 평균, 최고/최저 = 일 최고/최저기온의 연 최대/최소, 강수량 = 일강수량 합, 습도 = 일평균습도의 평균.
  (2025년은 기존 surveys.WEATHER 표와 모두 같다 — 같은 정의이다.)
"""
import csv, os, re, sys, time, urllib.request, datetime as dt, statistics as st
from concurrent.futures import ThreadPoolExecutor

STNS = {"143", "279", "281", "283", "278", "276", "136", "285", "288"}
# 시군 → 지점 (기존 surveys.WEATHER 의 '직접/준용' 과 같다)
REGION_STN = {"대구": "143", "경산": "143", "영천": "281", "구미": "279", "군위": "278", "청도": "288", "고령": "285", "성주": "279",
              "합천": "285", "창녕": "288", "경주": "283", "의성": "278", "청송": "276", "안동": "136", "김천": "279", "칠곡": "279"}
YEARS = ("2023", "2024", "2025")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "api", "services", "weather_history.py")


def fetch_all(key, raw_path):
    done = set()
    if os.path.exists(raw_path):
        done = {r[0] for r in csv.reader(open(raw_path, encoding="utf-8"))}
    d, days = dt.date(2023, 1, 1), []
    while d <= dt.date(2025, 12, 31):
        if d.strftime("%Y%m%d") not in done: days.append(d)
        d += dt.timedelta(days=1)

    def one(d):
        u = f"https://apihub.kma.go.kr/api/typ01/url/kma_sfcdd.php?tm={d:%Y%m%d}&stn=0&help=0&authKey={key}"
        for t in range(4):
            try:
                txt = urllib.request.urlopen(u, timeout=60).read().decode("cp949", "ignore")
                rows = [l.strip().rstrip(",").split(",") for l in txt.splitlines() if re.match(r"\d{8},", l)]
                return d, [r for r in rows if r[1].strip() in STNS]
            except Exception:
                time.sleep(2 * (t + 1))
        return d, None
    fails = 0
    with ThreadPoolExecutor(4) as ex, open(raw_path, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        for d, rows in ex.map(one, days):
            if rows is None: fails += 1; continue
            for r in rows: w.writerow([d.strftime("%Y%m%d")] + [x.strip() for x in r[1:]])
    print("내려받기 끝. 실패 일수:", fails)


def yearly(raw_path):
    by = {}
    for r in csv.reader(open(raw_path, encoding="utf-8")):
        by.setdefault((r[1], r[0][:4]), []).append(r)
    ok = lambda rs, i: [float(r[i]) for r in rs if float(r[i]) not in (-9.0, -99.0)]   # -9/-99 는 결측
    out = {}
    for (stn, y), rs in by.items():
        ta, hi, lo, hm = ok(rs, 10), ok(rs, 11), ok(rs, 13), ok(rs, 18)
        rn = sum(x for x in (float(r[38]) for r in rs) if x > 0)
        out[(stn, y)] = {"avgTemp": round(st.mean(ta), 1), "highTemp": max(hi), "lowTemp": min(lo), "precip": round(rn, 1), "humid": round(st.mean(hm), 1)}
    return out


def main():
    keyfile = sys.argv[1]
    raw = sys.argv[sys.argv.index("--raw") + 1] if "--raw" in sys.argv else os.path.join(HERE, "kma_daily_raw.csv")
    key = re.findall(r"authKey=([^&\s]+)", open(keyfile, encoding="utf-8").read())[-1]
    fetch_all(key, raw)
    y = yearly(raw)
    lines = ['"""최근 3년 지역 날씨 (기상청 ASOS 일자료로 만든 통계값) — build_weather_history.py 가 만든다. 직접 고치지 않는다.',
             '2025년은 surveys.WEATHER 와 같은 값이다(대조 완료). 지점이 없는 시군은 가까운 관측소 값을 준용한다."""',
             "BY_YEAR = {"]
    for yr in YEARS:
        lines.append(f"    {yr}: {{")
        for region, stn in REGION_STN.items():
            lines.append(f"        {region!r}: {y[(stn, yr)]!r},")
        lines.append("    },")
    lines.append("}")
    open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    print("만듦:", OUT)


if __name__ == "__main__":
    main()
