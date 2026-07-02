# -*- coding: utf-8 -*-
"""Hi-Flow 수중드론 누적 측정 데이터 시뮬레이터.

드론이 수면을 이동하며 측정 지점마다 정지한 뒤 센서를 수심별로 하강시켜
수질(탁도)을 측정하는 과정을 여러 회차에 걸쳐 시뮬레이션하고,
누적된 측정 데이터를 data/measurements.csv 로 저장한다.

실제 운용 시 이 파일 대신 드론이 전송한 실측 CSV를 그대로 사용하면 된다.
(컬럼 형식: run_id, timestamp, x_m, y_m, depth_m, turbidity_ntu)
"""

from pathlib import Path

import numpy as np
import pandas as pd

# ── 측정 환경 설정 ──────────────────────────────────────────────
AREA_SIZE = 100.0        # 측정 수역 크기 (m) — 100m x 100m
GRID_STEP = 10.0         # 측정 지점 간격 (m)
DEPTHS = np.arange(0.5, 5.01, 0.5)   # 측정 수심 (m): 0.5m ~ 5.0m, 0.5m 간격
NUM_RUNS = 8             # 누적 측정 회차 수
START_DATE = "2026-06-01"
BASE_TURBIDITY = 2.0     # 깨끗한 물의 기준 탁도 (NTU)
NOISE_STD = 0.8          # 센서 측정 노이즈 (NTU)

rng = np.random.default_rng(42)


def true_turbidity(x, y, depth, run):
    """시뮬레이션용 실제 탁도장(場): 기준 탁도 + 오염원 2곳의 3D 가우시안 플룸.

    주 오염원은 회차가 지날수록 동쪽으로 서서히 이동해
    누적 데이터에서 시간에 따른 변화도 관찰할 수 있게 한다.
    """
    # 주 오염원: (65, 40) 부근, 수심 3m 중심 — 회차당 동쪽으로 1.5m 이동
    cx1 = 65.0 + 1.5 * run
    plume1 = 38.0 * np.exp(
        -((x - cx1) ** 2 + (y - 40.0) ** 2) / (2 * 18.0**2)
        - (depth - 3.0) ** 2 / (2 * 1.2**2)
    )
    # 보조 오염원: (25, 75) 부근, 표층(1.5m) 중심
    plume2 = 15.0 * np.exp(
        -((x - 25.0) ** 2 + (y - 75.0) ** 2) / (2 * 12.0**2)
        - (depth - 1.5) ** 2 / (2 * 1.0**2)
    )
    return BASE_TURBIDITY + plume1 + plume2


def main():
    coords = np.arange(0.0, AREA_SIZE + 0.1, GRID_STEP)
    rows = []
    for run in range(NUM_RUNS):
        run_date = pd.Timestamp(START_DATE) + pd.Timedelta(days=run)
        t = run_date + pd.Timedelta(hours=9)  # 매 회차 09:00 출발
        for x in coords:
            for y in coords:
                for depth in DEPTHS:
                    value = true_turbidity(x, y, depth, run) + rng.normal(0, NOISE_STD)
                    rows.append(
                        {
                            "run_id": run + 1,
                            "timestamp": t,
                            "x_m": x,
                            "y_m": y,
                            "depth_m": depth,
                            "turbidity_ntu": round(max(value, 0.1), 2),
                        }
                    )
                    t += pd.Timedelta(seconds=20)  # 수심 1단계 측정에 20초 소요 가정

    df = pd.DataFrame(rows)
    out = Path(__file__).parent / "data" / "measurements.csv"
    out.parent.mkdir(exist_ok=True)
    df.to_csv(out, index=False)
    print(f"저장 완료: {out}")
    print(f"총 {len(df):,}개 측정값 (회차 {NUM_RUNS}회 x 지점 {len(coords)**2}곳 x 수심 {len(DEPTHS)}단계)")
    print(f"탁도 범위: {df['turbidity_ntu'].min()} ~ {df['turbidity_ntu'].max()} NTU")


if __name__ == "__main__":
    main()
