---
name: report
description: 누적 측정 데이터를 회차별 수치 요약 Excel 보고서(output/report.xlsx)로 정리한다. 사용자가 "보고서 만들어줘", "엑셀로 정리해줘"라고 하면 사용한다.
---

# 수치 요약 Excel 보고서 생성

1. `data/measurements.csv`가 없으면 먼저 데이터를 생성한다:
   ```powershell
   python generate_data.py
   ```
2. 보고서를 생성한다:
   ```powershell
   python export_report.py
   ```
3. `output/report.xlsx` 생성을 확인하고 기본 프로그램으로 연다:
   ```powershell
   Start-Process (Resolve-Path output\report.xlsx)
   ```
4. 콘솔 요약 표를 바탕으로 회차 수·오염 셀 수·최고 오염 위치를 보고한다.

참고
- 시트 구성: ① 회차별 요약 ② 오염 셀 목록(빨간 배경, 심한 순) ③ 셀별 전체 데이터
- 오염 판정: pH 6.5~8.5 벗어남 또는 EC 500 µS/cm 초과 (`thresholds.py`)
- 필요 패키지: pandas, openpyxl (`pip install -r requirements.txt`)
