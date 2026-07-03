---
name: heatmap
description: 누적 측정 데이터로 3D 히트맵(HTML+PNG)을 렌더링하고 결과를 연다. 사용자가 "히트맵 만들어줘", "3D 히트맵 렌더링"이라고 하면 사용한다. 인자로 "새로"가 오면 데이터를 다시 생성한다.
---

# 누적 데이터 3D 히트맵 렌더링

1. 인자에 "새로"가 있거나 `data/measurements.csv`가 없으면 먼저 데이터를 생성한다:
   ```powershell
   python generate_data.py
   ```
2. 히트맵을 렌더링한다:
   ```powershell
   python visualize_heatmap.py
   ```
3. 출력물이 생성됐는지 확인한다:
   - `output/heatmap_3d.html` — 인터랙티브 (탐사 회차·센서 드롭다운, 회전·확대·호버)
   - `output/heatmap_3d_ph.png`, `output/heatmap_3d_ec.png` — 보고서용 정적 이미지
4. `heatmap_3d_ph.png`와 `heatmap_3d_ec.png`를 Read 도구로 열어 렌더링이 정상인지(핫스팟·한글 레이블·빨간 다이아몬드(오염 셀)·범례) 육안 확인한 뒤,
   인터랙티브 버전을 기본 브라우저로 연다:
   ```powershell
   Start-Process (Resolve-Path output\heatmap_3d.html)
   ```
5. 셀 수·pH/EC 범위·오염 셀 유무를 요약해 보고한다.

참고
- 필요 패키지: numpy, pandas, plotly, matplotlib (`pip install -r requirements.txt`)
- 실측 데이터가 생기면 같은 컬럼 형식으로 `data/measurements.csv`만 교체하면 된다
  (컬럼: run_id, timestamp, x_m, y_m, depth_m, ph, ec).
