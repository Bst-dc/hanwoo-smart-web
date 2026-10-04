# -*- coding: utf-8 -*-
"""
전국 통계 벤치마크 및 비교분석 엔진 모듈
"""

NATIONAL_BENCHMARKS = {
    "거세": {
        "도체중": {2023: 467.0, 2024: 470.6, 2025: 478.1, 2026: 490.4},
        "BMS": {2023: 6.2, 2024: 6.2, 2025: 6.3, 2026: 7.0},
        "등지방": {2023: 12.7, 2024: 12.3, 2025: 12.4, 2026: 12.5},
        "단면적": {2023: 97.7, 2024: 97.6, 2025: 100.3, 2026: 106.7},
        "출하월령": {2023: 31.1, 2024: 31.6, 2025: 31.7, 2026: 31.7},
        "rate_1plus_above": {2023: 69.1, 2024: 68.9, 2025: 71.3, 2026: 74.2},
        "rate_1plus_plus": {2023: 39.1, 2024: 39.1, 2025: 41.5, 2026: 45.5},
        "rate_yield_a": {2023: 29.3, 2024: 32.2, 2025: 33.6, 2026: 33.3}
    },
    "암": {
        "도체중": {2023: 366.1, 2024: 371.0, 2025: 377.3, 2026: 393.1},
        "BMS": {2023: 4.5, 2024: 4.6, 2025: 4.7, 2026: 5.0},
        "등지방": {2023: 13.0, 2024: 12.7, 2025: 12.9, 2026: 13.1},
        "단면적": {2023: 86.3, 2024: 87.2, 2025: 88.8, 2026: 96.3},
        "출하월령": {2023: 55.7, 2024: 53.4, 2025: 53.2, 2026: 53.2},
        "rate_1plus_above": {2023: 32.1, 2024: 35.4, 2025: 36.9, 2026: 38.5},
        "rate_1plus_plus": {2023: 12.2, 2024: 14.7, 2025: 15.4, 2026: 16.4},
        "rate_yield_a": {2023: 26.6, 2024: 28.7, 2025: 29.1, 2026: 30.7}
    }
}

EUMSEONG_PRICES_2025 = {
    "1++": 23038,
    "1+": 19590,
    "1": 18165,
    "2": 14969,
    "3": 12735,
    "등외": 10000
}

def compare_farm_with_national(farm_stats, year=2025, gender="거세"):
    """
    농가 성적과 전국 통계를 1:1 비교 분석
    """
    nat = NATIONAL_BENCHMARKS.get(gender, NATIONAL_BENCHMARKS["거세"])
    
    comparisons = []
    
    metrics = [
        ("도체중", "kg", farm_stats.get("avg_weight"), nat["도체중"].get(year, 478.1)),
        ("근내지방도(BMS)", "점", farm_stats.get("avg_bms"), nat["BMS"].get(year, 6.3)),
        ("등지방두께", "mm", farm_stats.get("avg_backfat"), nat["등지방"].get(year, 12.4)),
        ("등심단면적", "㎠", farm_stats.get("avg_ribeye"), nat["단면적"].get(year, 100.3)),
        ("출하월령", "개월", farm_stats.get("avg_month_age"), nat["출하월령"].get(year, 31.7)),
        ("1+이상 출현율", "%", farm_stats.get("rate_1plus_above"), nat["rate_1plus_above"].get(year, 71.3)),
        ("1++ 출현율", "%", farm_stats.get("rate_1plus_plus"), nat["rate_1plus_plus"].get(year, 41.5)),
    ]
    
    for name, unit, farm_val, nat_val in metrics:
        if farm_val is not None:
            diff = round(farm_val - nat_val, 1)
            status = "우수" if diff > 0 else ("동일" if diff == 0 else "미흡")
            if name == "등지방두께":
                # 등지방은 두꺼울수록(양수) 과비이므로 주의
                status = "과비주의" if diff > 1.0 else ("적정" if abs(diff) <= 1.0 else "얇음")
            elif name == "출하월령":
                # 월령은 짧을수록 생산비 절감
                status = "단기출하" if diff < 0 else "지연출하"
        else:
            diff = None
            status = "-"
            
        comparisons.append({
            "metric": name,
            "unit": unit,
            "farm_value": farm_val,
            "national_value": nat_val,
            "diff": diff,
            "status": status
        })
        
    return comparisons
