# -*- coding: utf-8 -*-
"""
Claude AI 종합 컨설팅 리포트 생성 서비스 모듈
"""
import os
import json
import urllib.request
import urllib.error

def get_api_key():
    # 1. 웹시스템 폴더의 api_key.txt 탐색
    paths = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "api_key.txt"),
    ]
    for p in paths:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                key = f.read().strip()
                if key:
                    return key
    return os.environ.get("ANTHROPIC_API_KEY", "")

def generate_consulting_report(farm_name, shipment_data, survey_data, comparisons):
    """
    Claude API를 호출하여 7단 맞춤형 종합 컨설팅 보고서 생성
    """
    api_key = get_api_key()
    if not api_key:
        return "⚠️ Anthropic API 키가 설정되지 않았습니다. api_key.txt 파일을 확인해주세요."

    system_prompt = (
        "당신은 대한민국 최고의 한우 사양관리 수석 컨설턴트입니다. "
        "농가의 출하성적(도체중, BMS, 등지방두께, 단면적, 출하월령) 정량 데이터와 "
        "현장 방문(사양관리, 축사환경, 농가 대화) 정성 데이터를 융합 분석하여 "
        "'진단 → 원인 → 처방 → 액션플랜' 흐름의 7단 구성 맞춤형 컨설팅 리포트를 마크다운으로 작성하세요."
    )

    prompt = f"""
[농가명]: {farm_name}

[1. 출하성적 vs 전국 평균 비교 데이터]:
{json.dumps(comparisons, ensure_ascii=False, indent=2)}

[2. 최근 출하성적 상세 요약]:
{json.dumps(shipment_data, ensure_ascii=False, indent=2)}

[3. 현장 방문 조사 및 농가 대화 데이터]:
{json.dumps(survey_data, ensure_ascii=False, indent=2)}

[보고서 작성 가이드라인]
농장주 입장에서 읽기 쉽게 다음 7단 구성으로 작성해주세요:
# 1. 📋 종합 컨설팅 개요 배너
농가명, 방문일시, 컨설턴트, 핵심 평가 등급을 일목요연하게 제시하세요.

# 2. ⚡ 핵심 진단 요약 (30초 요약 카드)
출하성적과 현장 조사에서 도출된 가장 시급한 핵심 이슈 3가지를 명확히 요약하세요.

# 3. 📊 출하성적 전국 비교 및 수익성 분석
전국 대비 도체중, BMS, 등지방, 단면적, 1+이상 출현율 격차를 분석하고 두당 및 연간 수익성 임팩트를 제시하세요.

# 4. 🔍 현장 사양관리 및 축사환경 실태 진단
육성기/비육전기/비육중기/비육후기 사료 급여와 우방밀도, 환기, 깔짚 상태의 적정성을 평가하세요.

# 5. 💡 문제별 원인 분석 및 개선 처방 (1:1 매칭)
현장에서 확인된 문제마다 [문제 현상] → [근본 원인] → [정밀 처방]의 1:1 매칭 구조로 구체적인 수치와 함께 제시하세요.

# 6. 🚀 실행 우선순위 로드맵 (Action Plan)
- 1단계 (즉시 조치 / 1~2주):
- 2단계 (기반 구축 / 1~3개월):
- 3단계 (성적 개선 / 6개월~출하):

# 7. 📌 안내 및 출처
참고 문헌(국립축산과학원 한우사양표준) 및 담당 축협 컨설턴트 협의 권장 면책 문구를 포함하세요.
"""

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    payload = {
        "model": "claude-sonnet-4-5-20250929",
        "max_tokens": 6000,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    content += block.get("text", "")
            return content
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        return f"⚠️ Claude API 호출 오류 (HTTP {e.code}): {err_msg}"
    except Exception as e:
        return f"⚠️ Claude API 통신 오류: {str(e)}"
