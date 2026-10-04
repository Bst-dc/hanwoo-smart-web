import os
import pandas as pd
import sys
sys.stdout.reconfigure(encoding='utf-8')

# 파일 경로 (원본 엑셀은 reference/원본엑셀/ 에 모아둠)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
path_shipment = os.path.join(BASE_DIR, "reference", "원본엑셀", "농가출하데이터.xlsx")
path_survey = os.path.join(BASE_DIR, "reference", "원본엑셀", "한우현장조사_백업_20260916_2217.xlsx")

print("--- 출하데이터 컬럼 ---")
df_shipment = pd.read_excel(path_shipment)
print(df_shipment.columns.tolist())
print(df_shipment.head(2))

print("\n--- 현장조사 백업 컬럼 ---")
df_survey = pd.read_excel(path_survey)
print(df_survey.columns.tolist())
print(df_survey.head(2))
