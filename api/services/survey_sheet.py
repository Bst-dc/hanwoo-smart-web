"""현장조사표 수기용 인쇄 양식 — A4 로 뽑아 현장에서 손으로 적고, 돌아와 앱 '현장조사' 메뉴에 옮겨 입력한다.

항목·순서·선택지는 surveys.FORM 한 곳에서 만든다. 앱 입력 화면과 같은 순서라서 종이를 보면서 그대로 옮겨 적을 수 있고,
양식을 고치면 인쇄 양식도 같이 바뀐다. 농가를 고르면 조합원명·번호·지역(과 그 지역 날씨)을 미리 적어 둔다.
"""
from html import escape as e

from . import surveys

CSS = """
@page { size: A4; margin: 12mm; }
* { box-sizing: border-box; }
body { font-family: "Malgun Gothic", "Apple SD Gothic Neo", sans-serif; font-size: 10pt; color: #111; margin: 0; }
.bar { padding: 10px 12mm; background: #E6F0EC; font-size: 10pt; display: flex; gap: 12px; align-items: center; }
.bar button { font-size: 11pt; padding: 6px 14px; border: 0; border-radius: 6px; background: #2E6B57; color: #fff; cursor: pointer; }
.sheet { padding: 4mm 12mm 8mm; }
h1 { font-size: 15pt; margin: 0 0 2px; }
.guide { font-size: 8.5pt; color: #555; margin: 0 0 8px; }
section { border: 1px solid #333; margin-bottom: 7px; break-inside: avoid; }
section h2 { margin: 0; padding: 3px 8px; font-size: 10.5pt; background: #eee; border-bottom: 1px solid #333; }
table { border-collapse: collapse; width: 100%; table-layout: fixed; }
th, td { border: 1px solid #999; padding: 3px 6px; vertical-align: middle; text-align: left; }
th { background: #f7f7f7; font-weight: 600; width: 26%; font-size: 9.5pt; }
td.fill { height: 8mm; }
.opt { white-space: nowrap; margin-right: 8px; }
.note { padding: 4px 8px; font-size: 9pt; color: #444; }
.feed th, .feed td { text-align: center; font-size: 9pt; }
.feed th.row { text-align: left; width: 19%; }
.feed .opt { margin-right: 2px; font-size: 8pt; letter-spacing: -0.3px; }
.feed td { height: 7mm; }
.memo { height: 38mm; }
.unit { color: #666; font-size: 8.5pt; }
.fixed { background: #fafafa; }
@media print { .bar { display: none; } .sheet { padding: 0; } }
"""

WEATHER_LABEL = {"dailyAvgTemp": "연평균기온 (℃)", "highTemp": "최고기온 (℃)", "lowTemp": "최저기온 (℃)",
                 "annualPrecip": "평균강수량 (연간) (mm)", "avgWindSpeed": "평균풍속 (m/s)", "avgHumidity": "평균상대습도 (%)"}


def _boxes(options, checked=None) -> str:
    # 선택지 사이에 공백을 둬야 긴 목록이 칸 안에서 줄바꿈된다 (각 선택지는 nowrap 이라 중간에서 끊기지 않는다)
    return " ".join(f'<span class="opt">{"☑" if o == checked else "☐"} {e(o)}</span>' for o in options)


def _plain(label: str) -> str:
    """'조합원번호' 처럼 이모지를 뺀 칸 이름 (인쇄 글꼴에 이모지가 없을 수 있다)."""
    return "".join(ch for ch in label if ord(ch) < 0x2190 or 0xAC00 <= ord(ch) <= 0xD7A3 or ch.isascii() or ch in "℃㎠㎡").strip()


def _cell(f: dict, prefill: dict) -> str:
    key, kind = f["key"], f["kind"]
    if kind in ("select", "radio"):
        return _boxes(f["options"], prefill.get(key))
    if kind == "feed":
        return ""
    return e(str(prefill.get(key, "")))


def _feed_table() -> str:
    head = "".join(f"<th>{e(s)}</th>" for s in surveys.FEED_STAGES)
    rows = []
    for row in surveys.FEED_ROWS:
        cells = ("".join(f'<td>{_boxes(surveys.FEED_LEVELS)}</td>' for _ in surveys.FEED_STAGES) if "수준" in row
                 else "".join("<td></td>" for _ in surveys.FEED_STAGES))
        rows.append(f'<tr><th class="row">{e(row)}</th>{cells}</tr>')
    return f'<table class="feed"><tr><th class="row">구분</th>{head}</tr>{"".join(rows)}</table>'


def _section(s: dict, prefill: dict, weather: dict | None) -> str:
    title = _plain(s["title"])
    fields = s["fields"]
    if title.startswith("2."):                                   # 날씨는 지역을 고르면 앱이 채운다
        if weather:
            cells = "".join(f"<tr><th>{e(WEATHER_LABEL[k])}</th><td class='fixed'>{weather[v]}</td></tr>"
                            for k, v in surveys.WEATHER_FIELDS.items())
            body = f'<table>{cells}</table><div class="note">{e(prefill.get("region", ""))} 지역 기준값이 미리 적혀 있습니다 (출처: {e(weather["source"])}). 손으로 적을 필요 없습니다.</div>'
        else:
            body = '<div class="note">앱에서 지역을 고르면 날씨 값이 자동으로 채워집니다. 손으로 적을 필요 없습니다.</div>'
        return f"<section><h2>{e(title)}</h2>{body}</section>"

    rows = []
    for f in fields:
        label = e(_plain(f["label"]))
        if f["kind"] == "feed":
            rows.append(f'<tr><th colspan="2" style="width:auto">{label}</th></tr>'
                        f'<tr><td colspan="2" style="padding:4px">{_feed_table()}</td></tr>')
        elif f["kind"] == "textarea":
            rows.append(f'<tr><th>{label}</th><td class="memo"></td></tr>')
        elif f["kind"] in ("select", "radio"):
            rows.append(f"<tr><th>{label}</th><td>{_cell(f, prefill)}</td></tr>")
        else:
            rows.append(f'<tr><th>{label}</th><td class="fill">{_cell(f, prefill)}</td></tr>')
    return f"<section><h2>{e(title)}</h2><table>{''.join(rows)}</table></section>"


def build_html(farm: dict | None = None) -> str:
    """farm 은 {name, code, region} (없으면 빈 양식). 반환은 완성된 HTML 문서."""
    prefill: dict = {}
    weather = None
    if farm:
        prefill = {"memberName": farm.get("name", ""), "memberId": farm.get("code", "")}
        region = farm.get("region", "")
        if region in surveys.REGIONS:
            prefill["region"] = region
            weather = surveys.WEATHER.get(region)
    sub = f' — {e(farm["name"])}' if farm else ""
    body = "".join(_section(s, prefill, weather) for s in surveys.FORM)
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>현장조사표(수기용){e(sub)}</title><style>{CSS}</style></head><body>
<div class="bar"><button onclick="window.print()">🖨️ 인쇄 (A4)</button><span>용지에 손으로 적은 뒤, 앱의 '현장조사 → 새 방문조사 작성'에 같은 순서로 입력하세요.</span></div>
<div class="sheet">
<h1>한우 스마트 컨설팅 · 현장조사표{e(sub)}</h1>
<p class="guide">선택 항목은 해당하는 칸에 ✔ 표시, 숫자·글 항목은 빈 칸에 직접 적습니다. 항목 순서는 앱 입력 화면과 같습니다.</p>
{body}
</div></body></html>"""
