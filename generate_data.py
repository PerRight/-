# -*- coding: utf-8 -*-
"""Hi-Flow 수중드론 누적 측정 데이터 시뮬레이터.

드론이 수면을 이동하며 측정 지점마다 정지한 뒤 센서를 수심별로 하강시켜
수질(pH·EC)을 측정하는 과정을 여러 회차에 걸쳐 시뮬레이션하고,
누적된 측정 데이터를 data/measurements.csv 로 저장한다.

측정 프로파일: 수심 0.5 / 1.0 / 1.5 m 세 단계 — 각 수심에서 1분(20초 간격 3표본),
지점당 3분.

실제 운용 시 이 파일 대신 드론이 전송한 실측 CSV를 그대로 사용하면 된다.
(컬럼 형식: run_id, timestamp, x_m, y_m, depth_m, ph, ec)
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ── 측정 환경 설정 ──────────────────────────────────────────────
AREA_SIZE = 100.0        # 측정 수역 크기 (m) — 100m x 100m
GRID_STEP = 10.0         # 측정 지점 간격 (m)
DEPTHS = [0.5, 1.0, 1.5]  # 측정 수심 (m) — 각 수심에서 1분씩, 지점당 3분
SAMPLES_PER_DEPTH = 3    # 수심당 표본 수 (1분 동안 20초 간격)
NUM_RUNS = 8             # 누적 측정 회차 수
START_DATE = "2026-06-01"
PH_NOISE = 0.03          # pH 센서 측정 노이즈
EC_NOISE = 4.0           # EC 센서 측정 노이즈 (µS/cm)

rng = np.random.default_rng(42)


def plume(x, y, depth, run):
    """시뮬레이션용 오염 플룸 강도(0~1) — dashboard_server.py 의 plume 과 동일 모델.

    주 오염원: (65, 40) 부근, 수심 1.0 m 중심 — 회차당 동쪽으로 1.5 m 이동해
    누적 데이터에서 시간에 따른 변화도 관찰할 수 있게 한다.
    보조 오염원: (25, 75) 부근, 표층(0.5 m) 중심.
    """
    cx1 = 65.0 + 1.5 * run
    p1 = np.exp(
        -((x - cx1) ** 2 + (y - 40.0) ** 2) / (2 * 18.0**2)
        - (depth - 1.0) ** 2 / (2 * 1.2**2)
    )
    p2 = 0.4 * np.exp(
        -((x - 25.0) ** 2 + (y - 75.0) ** 2) / (2 * 12.0**2)
        - (depth - 0.5) ** 2 / (2 * 1.0**2)
    )
    return np.minimum(p1 + p2, 1.0)


def true_ph(x, y, depth, run):
    """노이즈 없는 실제 pH — 오염원 부근에서 산성으로 내려간다."""
    return 7.10 - 0.04 * depth - 1.1 * plume(x, y, depth, run)


def true_ec(x, y, depth, run):
    """노이즈 없는 실제 EC(µS/cm) — 오염원 부근에서 상승한다."""
    return 320.0 + 6.0 * depth + 220.0 * plume(x, y, depth, run)


def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔에서 µ 등 출력 보장
    coords = np.arange(0.0, AREA_SIZE + 0.1, GRID_STEP)
    rows = []
    for run in range(NUM_RUNS):
        t = pd.Timestamp(START_DATE) + pd.Timedelta(days=run, hours=9)  # 매 회차 09:00 출발
        for x in coords:
            for y in coords:
                for depth in DEPTHS:
                    for _ in range(SAMPLES_PER_DEPTH):
                        ph = true_ph(x, y, depth, run) + rng.normal(0, PH_NOISE)
                        ec = true_ec(x, y, depth, run) + rng.normal(0, EC_NOISE)
                        rows.append(
                            {
                                "run_id": run + 1,
                                "timestamp": t,
                                "x_m": x,
                                "y_m": y,
                                "depth_m": depth,
                                "ph": round(ph, 2),
                                "ec": round(max(ec, 0.0), 0),
                            }
                        )
                        t += pd.Timedelta(seconds=20)

    df = pd.DataFrame(rows)
    out = Path(__file__).parent / "data" / "measurements.csv"
    out.parent.mkdir(exist_ok=True)
    df.to_csv(out, index=False)
    print(f"저장 완료: {out}")
    print(
        f"총 {len(df):,}개 측정값 (회차 {NUM_RUNS}회 x 지점 {len(coords) ** 2}곳"
        f" x 수심 {len(DEPTHS)}단계 x 표본 {SAMPLES_PER_DEPTH}개)"
    )
    print(f"pH 범위: {df['ph'].min()} ~ {df['ph'].max()}")
    print(f"EC 범위: {df['ec'].min()} ~ {df['ec'].max()} µS/cm")


if __name__ == "__main__":
    main()
