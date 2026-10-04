"""
reference/원본PDF/ 의 전문자료 PDF를 AI 리포트용 지식베이스(knowledge/*.md)로 추출한다.

AI 리포트 생성 시 이 md 파일들이 프롬프트에 상주해 "근거 있는 처방"을 쓰게 하는 용도.
자료가 바뀔 때만 수동으로 1회 실행한다 (앱 실행 중에는 호출되지 않는다).

    python build_knowledge.py

주의: 원본 PDF는 .gitignore 대상(reference/)이라 저장소에 올라가지 않는다.
      다른 PC에서 돌리려면 reference/원본PDF/ 에 같은 파일이 있어야 한다.
"""
import re
import sys
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:
    sys.exit("pypdf가 필요합니다:  python -m pip install pypdf")

# 원본 PDF는 reference/원본PDF/ 에 모아뒀다(이 폴더만으로 재추출이 끝나도록).
_HERE = Path(__file__).parent
SRC_DIR = _HERE / "reference" / "원본PDF"
OUT_DIR = _HERE / "knowledge"

# (파일명, 출력명, 표 위주 페이지를 걸러낼지, 수록할 페이지 범위)
#
# skip_tables=True 는 KPN 육종가처럼 숫자 표만 가득한 페이지를 버린다.
# 그런 페이지는 토큰만 잡아먹고 컨설팅 지식으로는 쓸모가 없다.
#
# page_range 는 (시작, 끝) 1-based 포함 범위. None 이면 전체.
# 계획교배 길라잡이는 513p 중 대부분이 KPN 육종가 표이고, 앞부분은 엑셀 프로그램
# 사용설명서다. 실제 유전학 지식(육종가·근교계수·멘델리안 샘플링·EPD)은 p.14~33
# 뿐이라 그 구간만 쓴다 — 사용설명서가 리포트 근거로 인용되면 곤란하다.
SOURCES = [
    ("20240827_[농협경제지주]한우 컨설팅 길라잡이(A5,136P) - 온라인용.pdf",
     "한우_컨설팅_길라잡이", False, None),
    ("현장에서 배우는 자가TMR(2023).PDF",
     "자가TMR_제조와_배합비", False, None),
    ("한우 계획교배 길라잡이.PDF",
     "한우_육종가_기초지식", True, (14, 33)),
]

HANGUL = re.compile(r"[가-힣]")
# 이중 렌더링 판정에 쓰는 낱말 덩어리 (한글 또는 영문)
WORD_RUN = re.compile(r"[가-힣]+|[A-Za-z]+")


def collapse_doubled(text):
    """굵은 글씨가 이중 렌더링된 줄을 되돌린다.

    '44.. 황황체체낭낭종종((LLuutteeaall))' → '4. 황체낭종(Luteal)'

    줄 단위로 판정한다. 한글이나 영문 덩어리 중 '4글자 이상이고 통째로 두 번씩
    찍힌' 것이 하나라도 있으면 그 줄 전체가 이중 렌더링된 것으로 보고, 붙어있는
    같은 글자 쌍을 모두 한 개로 줄인다 — 그 줄에서는 숫자·괄호까지 전부 두 번씩
    찍혀 있기 때문이다.

    멀쩡한 줄은 건드리지 않는다. '곳곳', 'coffee', '1122'처럼 원래 겹치는 글자를
    망가뜨리지 않기 위한 안전장치다.
    """
    lines = []
    for line in text.split("\n"):
        if any(
            len(run) >= 4 and len(run) % 2 == 0 and run[0::2] == run[1::2]
            for run in WORD_RUN.findall(line)
        ):
            line = re.sub(r"(.)\1", r"\1", line)
        lines.append(line)
    return "\n".join(lines)


def is_table_page(text):
    """KPN 육종가표처럼 숫자·영문 코드가 대부분인 페이지인지 판정."""
    if len(text) < 200:
        return False
    digits = sum(c.isdigit() for c in text)
    hangul = len(HANGUL.findall(text))
    # 숫자가 한글보다 많으면 데이터 표로 본다
    return digits > hangul


def clean(text):
    text = collapse_doubled(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract(pdf_path, skip_tables, page_range=None):
    reader = PdfReader(pdf_path)
    total = len(reader.pages)
    kept, dropped, chunks = 0, 0, []
    lo, hi = page_range if page_range else (1, total)

    for i, page in enumerate(reader.pages):
        if not (lo <= i + 1 <= hi):
            dropped += 1
            continue
        raw = (page.extract_text() or "").strip()
        if len(raw) < 40:          # 표지·장 구분 페이지
            dropped += 1
            continue
        if skip_tables and is_table_page(raw):
            dropped += 1
            continue
        chunks.append(f"[p.{i + 1}]\n{clean(raw)}")
        kept += 1

    return "\n\n".join(chunks), total, kept, dropped


def main():
    if not SRC_DIR.exists():
        sys.exit(f"원본 폴더를 찾을 수 없습니다: {SRC_DIR}")
    OUT_DIR.mkdir(exist_ok=True)

    print(f"원본: {SRC_DIR}")
    print(f"출력: {OUT_DIR}\n")
    grand_total = 0

    for filename, out_name, skip_tables, page_range in SOURCES:
        src = SRC_DIR / filename
        if not src.exists():
            print(f"  [건너뜀] 파일 없음: {filename}")
            continue

        print(f"  {out_name} ... ", end="", flush=True)
        body, total, kept, dropped = extract(src, skip_tables, page_range)

        header = (
            f"# {out_name.replace('_', ' ')}\n\n"
            f"> 출처: {filename}\n"
            f"> 전체 {total}페이지 중 {kept}페이지 수록"
            f"{f' (표·여백 {dropped}페이지 제외)' if dropped else ''}\n\n"
        )
        out_path = OUT_DIR / f"{out_name}.md"
        out_path.write_text(header + body, encoding="utf-8")

        chars = len(body)
        grand_total += chars
        print(f"{total}p → {kept}p 수록 / {chars:,}자 (약 {chars // 1000}K 토큰)")

    print(f"\n합계 약 {grand_total:,}자 / {grand_total // 1000}K 토큰")
    print("(한글은 대략 1자 = 1토큰으로 잡은 어림치입니다)")


if __name__ == "__main__":
    main()
