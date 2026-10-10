"""요청·응답 데이터 구조 (Pydantic)."""
from typing import Literal

from pydantic import BaseModel, Field


# ---------- 로그인 ----------
class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class AuthStatus(BaseModel):
    password_required: bool
    authed: bool


# ---------- 농가 ----------
class FarmOption(BaseModel):
    id: int
    label: str = Field(description="선택 목록 표시 이름: 농가명 (대표자, 지역) — 같으면 #id 를 붙인다")
    farm_name: str
    farm_code: str | None = None
    owner_name: str | None = None
    region: str | None = Field(None, description="방문조사표에 적힌 최근 지역이 있으면 그 값")
    breeding_type: str | None = None
    total_heads: int | None = None


class FarmCreate(BaseModel):
    farm_code: str = Field("", max_length=50, description="조합원 번호. 비우면 F+숫자 4자리로 자동 생성")
    farm_name: str = Field(min_length=1, max_length=100)
    owner_name: str = Field("", max_length=50)
    region: str = Field("", max_length=50)
    breeding_type: Literal["비육우", "일관사육", "번식우"] = "비육우"
    total_heads: int = Field(100, ge=0, le=100000)
    confirm_duplicate: bool = Field(False, description="이름·조합원번호가 같은 농가가 있어도 별개 농가로 등록")


class BackupStatus(BaseModel):
    ok: bool | None = Field(description="True 백업 성공, False 실패(데이터는 저장됨), None 백업 미설정")
    message: str


class FarmCreated(BaseModel):
    farm: FarmOption
    backup: BackupStatus


# ---------- 대시보드 ----------
class Plus1Rate(BaseModel):
    """1+ 이상 출현율 KPI. 전국값과의 차이(delta)는 같은 성별의 기준 연도 전국값과 비교한다."""
    value: float = Field(description="방문농가 전체 1+ 이상 출현율 (%)")
    national: float | None = Field(None, description="기준 연도 전국 1+ 이상 출현율 (%)")
    base_year: int | None = Field(None, description="비교 기준 연도 — 1년치가 다 채워진 작년 통계")
    delta: float | None = Field(None, description="value - national (%p)")


class DashboardSummary(BaseModel):
    total_farms: int
    total_visits: int
    total_shipments: int
    steer_plus1: Plus1Rate | None = None
    cow_plus1: Plus1Rate | None = None
    farms_missing_survey: list[str] = Field(default_factory=list, description="출하성적만 있고 조사표가 없는 농가")
    farms_missing_shipment: list[str] = Field(default_factory=list, description="조사표만 있고 출하성적이 없는 농가")


class YearMetrics(BaseModel):
    carcass_weight: float | None = Field(None, description="도체중 kg")
    bms: float | None = None
    ribeye: float | None = Field(None, description="등심단면적 ㎠")
    backfat: float | None = Field(None, description="등지방 mm")
    plus1_rate: float | None = Field(None, description="1+ 이상 출현율 %")
    c_rate: float | None = Field(None, description="육량 C등급 출현율 %")
    month_age: float | None = Field(None, description="출하월령")


class YearRow(BaseModel):
    year: int
    farms: int | None = Field(None, description="출하 농가 수 (그 해 출하가 없으면 None)")
    heads: int | None = Field(None, description="출하 두수")
    farm: YearMetrics = Field(description="방문농가 평균")
    national: YearMetrics = Field(description="전국 평균")


class YearlyTrend(BaseModel):
    gender: str = Field(description="거세 | 암")
    rows: list[YearRow] = Field(description="2023년부터 올해까지, 오름차순")


class GenderCompareRow(BaseModel):
    gender: str
    heads: int
    carcass_weight: float | None = None
    bms: float | None = None
    ribeye: float | None = None
    backfat: float | None = None
    plus1_rate: float | None = None
    month_age: float | None = None


# ---------- 1단계 · 출하성적 ----------
class ShipmentDraft(BaseModel):
    """이력제 조회 결과 한 두 (저장 전 검토용). 화면에서 고치거나 지운 뒤 그대로 저장 요청에 쓴다."""
    animal_no: str | None = None
    gender: str | None = Field(None, description="거세 | 암 | 수. 비어 있으면 저장할 때 거세")
    costAmt: float | None = Field(None, description="kg 당 단가 (원)")
    carcass_weight: float | None = None
    grade_quality: str | None = None
    grade_yield: str | None = None
    bms: float | None = None
    backfat: float | None = None
    ribeye: float | None = None
    month_age: float | None = None
    slaughter_date: str | None = None


class EkapeLookupRequest(BaseModel):
    animal_nos: list[str] = Field(min_length=1, max_length=20, description="한 번에 20두까지 — 화면이 나눠서 보낸다")


class EkapeLookupResult(BaseModel):
    key_configured: bool
    records: list[ShipmentDraft]
    not_found: list[str] = Field(description="결과가 없거나 조회에 실패한 번호")


class SaveDraftsRequest(BaseModel):
    records: list[ShipmentDraft] = Field(max_length=1000)


class SaveResult(BaseModel):
    saved: int
    backup: BackupStatus


class ExcelPreview(BaseModel):
    rows: int
    columns: list[str]
    animal_no_column: str | None
    name_column: str | None
    mismatched_names: list[str] = Field(description="파일 안 이름 중 선택한 농가와 다른 것 — 있으면 저장 전 확인 필요")
    will_skip: int = Field(description="이력번호가 없거나 8자 미만이라 건너뛸 행")
    missing_date: int = Field(description="도축일자를 읽지 못해 2025년으로 들어갈 행")
    missing_columns: list[str]


class ComparisonRow(BaseModel):
    label: str
    key: str
    farm: float | None
    national: float | None
    diff: float | None
    verdict: str


class Profit(BaseModel):
    per_head: int = Field(description="두당 추정 차이 (원) = 도체중 격차 × 21,000원")
    total: int
    heads: int


class RecentYear(BaseModel):
    year: int
    farm: YearMetrics
    national: YearMetrics


class ShipmentRecord(BaseModel):
    animal_no: str
    gender: str | None
    slaughter_date: str | None
    carcass_weight: float | None
    grade_quality: str | None
    grade_yield: str | None
    bms: float | None
    backfat: float | None
    ribeye: float | None
    month_age: float | None


class Comparison(BaseModel):
    years: list[int] = Field(description="이 농가에 출하가 있는 연도 (최근 순)")
    year: int | None = Field(description="선택한 연도. null 이면 전체 누적")
    cmp_gender: str = Field(description="전국 비교에 쓴 성별 — '전체' 를 고르면 거세우(없으면 암소)")
    gender_caption: str
    total_count: int = Field(description="비교에 쓴 두수 (cmp_gender 기준)")
    national_year: int | None = None
    rows: list[ComparisonRow] = Field(default_factory=list)
    profit: Profit | None = None
    recent: list[RecentYear] = Field(default_factory=list, description="최근 3개 연도 농가 vs 전국")
    records: list[ShipmentRecord] = Field(description="개체별 성적 (선택한 성별 그대로, 도축일 최근 순)")
