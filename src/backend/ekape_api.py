# -*- coding: utf-8 -*-
"""
축산물품질평가원(ekape) 등급판정 OpenAPI 연동 모듈
"""
import os
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

API_KEY = os.environ.get("EKAPE_API_KEY", "")
CACHE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "ekape_cache.json")

def _load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def _save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def get_cattle_grade(animal_no):
    """
    개체이력번호(12자리)로 축평원 등급판정 상세 데이터 조회
    """
    if not animal_no:
        return None
    
    animal_no = str(animal_no).replace('-', '').strip()
    cache = _load_cache()
    if animal_no in cache:
        return cache[animal_no]
    
    url1 = f"http://data.ekape.or.kr/openapi-data/service/user/grade/confirm/issueNo?animalNo={animal_no}&ServiceKey={API_KEY}"
    try:
        req1 = urllib.request.urlopen(url1, timeout=8)
        xml1 = req1.read().decode('utf-8')
        root1 = ET.fromstring(xml1)
        issue_no_node = root1.find('.//issueNo')
        if issue_no_node is None or not issue_no_node.text:
            return None
        issue_no = issue_no_node.text.strip()
        
        issue_no_encoded = urllib.parse.quote(issue_no)
        url2 = f"http://data.ekape.or.kr/openapi-data/service/user/grade/confirm/cattle?issueNo={issue_no_encoded}&ServiceKey={API_KEY}"
        req2 = urllib.request.urlopen(url2, timeout=8)
        xml2 = req2.read().decode('utf-8')
        root2 = ET.fromstring(xml2)
        
        item = root2.find('.//item')
        if item is None:
            return None
        
        def get_text(node, tag):
            child = node.find(tag)
            return child.text if child is not None else None
        
        def to_float(val):
            try:
                return float(val) if val else None
            except:
                return None

        result = {
            'animal_no': animal_no,
            'costAmt': to_float(get_text(item, 'costAmt')),
            'carcass_weight': to_float(get_text(item, 'weight')),
            'grade_quality': get_text(item, 'qgrade'),
            'grade_yield': get_text(item, 'wgrade'),
            'bms': to_float(get_text(item, 'insfat')),
            'backfat': to_float(get_text(item, 'backfat')),
            'ribeye': to_float(get_text(item, 'rea')),
            'month_age': to_float(get_text(item, 'birthmonth')),
            'slaughter_date': get_text(item, 'judgeBreedNm') or get_text(item, 'judgeDate')
        }
        
        cache[animal_no] = result
        _save_cache(cache)
        return result
    except Exception as e:
        print(f"[ekape API] 개체 {animal_no} 조회 실패: {e}")
        return None
