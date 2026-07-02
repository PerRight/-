# 고오염 표시 · 다중 탐사 조회 · Excel 내보내기 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** pH·EC 임계값 기반 오염 셀 빨간색 표시, 탐사 회차별 조회, Excel 수치 요약 내보내기, 측정 프로파일(수심 0.5/1.0/1.5 m·수심당 1분) 반영.

**Architecture:** 임계값은 새 모듈 `thresholds.py` 하나에 두고 서버·오프라인 히트맵·보고서가 공유한다. 대시보드 서버는 시작 시 `data/measurements.csv`를 회차별로 집계해 메모리에 들고 `/api/heatmap?run=`, `/api/runs`, `/api/export`를 제공한다. 오프라인 히트맵은 회차·센서 조합 드롭다운을 HTML 하나에 내장한다.

**Tech Stack:** Python 표준 라이브러리(서버), pandas/plotly/matplotlib/openpyxl(오프라인 도구), pytest(테스트), Plotly.js CDN(대시보드 프런트).

**Spec:** `docs/superpowers/specs/2026-07-02-hotspot-runs-export-design.md`

## Global Constraints

- 오염 임계값: **pH < 6.5 또는 pH > 8.5** / **EC > 500 µS/cm** — `thresholds.py`가 유일한 정의처.
- 오염 표시색: **#d03b3b** (빨강).
- 측정 수심: **0.5 / 1.0 / 1.5 m**, 수심당 1분(지점당 3분). 대시보드 데모 체류는 3초(상수 `DEPTH_DWELL`, 주석에 실제 60초 명시).
- CSV 컬럼: `run_id, timestamp, x_m, y_m, depth_m, ph, ec`.
- `dashboard_server.py`는 pip 의존성 없이 동작해야 한다 (openpyxl은 try-import, 실패 시 CSV 대체).
- 막대 경사 강조 지수: `BAR_EXAGGERATION = 2.5`.
- 시뮬레이션 오염 플룸 수심 중심: 주 오염원 1.0 m, 보조 오염원 0.5 m (generate_data.py와 dashboard_server.py 동일).
- 테스트 실행: `python -m pytest tests/ -v` (프로젝트 루트에서).
- 모든 커밋 메시지 끝에 붙인다: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- 한글 주석·문구는 기존 파일 스타일을 따른다.

---

### Task 1: 기반 구축 — git 초기화, 의존성, thresholds.py

**Files:**
- Create: `.gitignore`
- Create: `thresholds.py`
- Create: `tests/test_thresholds.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `SENSOR_INFO` (dict: sensor_id → {name, unit, decimals, threshold}), `is_polluted(sensor_id, value) -> bool`, `exceedance(sensor_id, value) -> float`, `pollution_reason(ph_mean, ec_mean) -> str` — 이후 모든 태스크가 사용.

- [ ] **Step 1: git 저장소 초기화와 .gitignore 작성**

`.gitignore` 내용:

```
__pycache__/
.pytest_cache/
output/
data/
```

```powershell
git init && git add .gitignore CLAUDE.md README.md requirements.txt generate_data.py visualize_heatmap.py dashboard_server.py dashboard.html .claude docs && git commit -m @'
chore: 기존 프로젝트 초기 커밋

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

Expected: 초기 커밋 생성 (`수중드론 자료/`는 바이너리 자료 폴더 — 추가하지 않아도 됨).

- [ ] **Step 2: requirements.txt에 openpyxl·pytest 추가**

`requirements.txt` 전체 내용:

```
numpy
pandas
plotly
matplotlib
openpyxl
pytest
```

설치: `pip install -r requirements.txt`

- [ ] **Step 3: 실패하는 테스트 작성**

`tests/test_thresholds.py`:

```python
# -*- coding: utf-8 -*-
from thresholds import SENSOR_INFO, exceedance, is_polluted, pollution_reason


def test_ph_low_is_polluted():
    assert is_polluted("ph", 6.2)


def test_ph_high_is_polluted():
    assert is_polluted("ph", 8.9)


def test_ph_in_range_is_clean():
    assert not is_polluted("ph", 7.0)
    assert not is_polluted("ph", 6.5)
    assert not is_polluted("ph", 8.5)


def test_ec_over_threshold_is_polluted():
    assert is_polluted("ec", 520.0)


def test_ec_at_threshold_is_clean():
    assert not is_polluted("ec", 500.0)


def test_none_value_is_clean():
    assert not is_polluted("ph", None)
    assert not is_polluted("ec", None)


def test_unknown_sensor_is_clean():
    assert not is_polluted("do", 999.0)


def test_pollution_reason_both():
    assert pollution_reason(6.0, 600.0) == "pH·EC"


def test_pollution_reason_single():
    assert pollution_reason(6.0, 300.0) == "pH"
    assert pollution_reason(7.0, 600.0) == "EC"


def test_pollution_reason_clean():
    assert pollution_reason(7.0, 400.0) == ""


def test_exceedance_positive_when_over():
    assert exceedance("ec", 550.0) > 0
    assert exceedance("ph", 6.0) > 0


def test_exceedance_zero_when_clean():
    assert exceedance("ec", 400.0) == 0.0
    assert exceedance("ph", 7.0) == 0.0


def test_sensor_info_thresholds():
    assert SENSOR_INFO["ph"]["threshold"] == {"min": 6.5, "max": 8.5}
    assert SENSOR_INFO["ec"]["threshold"] == {"max": 500.0}
```

- [ ] **Step 4: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_thresholds.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'thresholds'`

- [ ] **Step 5: thresholds.py 구현**

```python
# -*- coding: utf-8 -*-
"""센서별 오염 판정 임계값 — 대시보드·히트맵·보고서가 공유하는 단일 기준.

pH: 6.5~8.5 벗어나면 오염 / EC: 500 µS/cm 초과 시 오염.
"""

SENSOR_INFO = {
    "ph": {
        "name": "pH", "unit": "", "decimals": 2,
        "threshold": {"min": 6.5, "max": 8.5},
    },
    "ec": {
        "name": "EC 전기전도도", "unit": "µS/cm", "decimals": 0,
        "threshold": {"max": 500.0},
    },
}


def is_polluted(sensor_id, value):
    """셀 평균값이 임계값을 벗어나면 True."""
    if value is None or sensor_id not in SENSOR_INFO:
        return False
    t = SENSOR_INFO[sensor_id]["threshold"]
    return value < t.get("min", float("-inf")) or value > t.get("max", float("inf"))


def exceedance(sensor_id, value):
    """임계값 초과 정도(상대 비율, 정상이면 0) — '최고 오염' 셀 선정용."""
    if value is None or sensor_id not in SENSOR_INFO:
        return 0.0
    t = SENSOR_INFO[sensor_id]["threshold"]
    r = 0.0
    if "max" in t and value > t["max"]:
        r = (value - t["max"]) / t["max"]
    if "min" in t and value < t["min"]:
        r = max(r, (t["min"] - value) / t["min"])
    return r


def pollution_reason(ph_mean, ec_mean):
    """오염 판정 사유: 'pH' / 'EC' / 'pH·EC' / '' (정상)."""
    reasons = []
    if is_polluted("ph", ph_mean):
        reasons.append("pH")
    if is_polluted("ec", ec_mean):
        reasons.append("EC")
    return "·".join(reasons)
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `python -m pytest tests/test_thresholds.py -v`
Expected: 전부 PASS

- [ ] **Step 7: 커밋**

```powershell
git add thresholds.py tests/test_thresholds.py requirements.txt .gitignore && git commit -m @'
feat: 센서별 오염 임계값 모듈 추가 (pH 6.5~8.5, EC 500)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 2: generate_data.py — pH·EC 전환 + 수심 3단계 프로파일

**Files:**
- Modify: `generate_data.py` (전체 재작성)
- Create: `tests/test_generate_data.py`

**Interfaces:**
- Produces: `data/measurements.csv` (컬럼 `run_id, timestamp, x_m, y_m, depth_m, ph, ec`), 순수 함수 `true_ph(x, y, depth, run)`, `true_ec(x, y, depth, run)` (노이즈 없는 참값, run은 0부터).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_generate_data.py`:

```python
# -*- coding: utf-8 -*-
from generate_data import DEPTHS, SAMPLES_PER_DEPTH, true_ec, true_ph


def test_hotspot_is_polluted():
    # 주 오염원 (65, 40) 수심 1.0 m — pH 산성화·EC 상승으로 임계값을 넘어야 한다
    assert true_ph(65, 40, 1.0, 0) < 6.5
    assert true_ec(65, 40, 1.0, 0) > 500


def test_clean_corner_is_normal():
    assert 6.5 <= true_ph(0, 100, 0.5, 0) <= 8.5
    assert true_ec(0, 100, 0.5, 0) <= 500


def test_depth_profile():
    # 수심 0.5/1.0/1.5 m 세 단계, 수심당 3표본(20초 간격 1분)
    assert DEPTHS == [0.5, 1.0, 1.5]
    assert SAMPLES_PER_DEPTH == 3
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_generate_data.py -v`
Expected: FAIL — `ImportError: cannot import name 'true_ph'`

- [ ] **Step 3: generate_data.py 재작성**

전체 내용:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_generate_data.py -v`
Expected: 3개 전부 PASS

- [ ] **Step 5: 데이터 재생성 및 확인**

Run: `python generate_data.py`
Expected: `총 26,136개 측정값 (회차 8회 x 지점 121곳 x 수심 3단계 x 표본 3개)`, pH 최소값 6.5 미만, EC 최대값 500 초과.

- [ ] **Step 6: 커밋**

```powershell
git add generate_data.py tests/test_generate_data.py && git commit -m @'
feat: 측정 데이터를 pH·EC + 수심 3단계(0.5/1/1.5m) 프로파일로 전환

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 3: dashboard_server.py — 측정 프로파일·플룸 수심·임계값 필드

**Files:**
- Modify: `dashboard_server.py`

**Interfaces:**
- Consumes: `thresholds.SENSOR_INFO`
- Produces: `/api/telemetry`의 각 sensors 항목에 `"threshold"` 필드 (예: `{"min": 6.5, "max": 8.5}`), `max_depth_m` = 1.5. 시뮬레이터가 수심 0.5/1.0/1.5에서만 샘플 수집.

- [ ] **Step 1: import와 플룸 수심 중심 수정**

`dashboard_server.py` 상단 import 블록에 추가 (`from urllib.parse ...` 다음 줄):

```python
from thresholds import SENSOR_INFO
```

`plume` 함수의 수심 중심을 generate_data.py와 맞춘다. 기존:

```python
    p1 = math.exp(-((x - 65) ** 2 + (y - 40) ** 2) / (2 * 18**2) - (depth - 3.0) ** 2 / (2 * 1.2**2))
    p2 = 0.4 * math.exp(-((x - 25) ** 2 + (y - 75) ** 2) / (2 * 12**2) - (depth - 1.5) ** 2 / (2 * 1.0**2))
```

수정:

```python
    p1 = math.exp(-((x - 65) ** 2 + (y - 40) ** 2) / (2 * 18**2) - (depth - 1.0) ** 2 / (2 * 1.2**2))
    p2 = 0.4 * math.exp(-((x - 25) ** 2 + (y - 75) ** 2) / (2 * 12**2) - (depth - 0.5) ** 2 / (2 * 1.0**2))
```

plume docstring의 "주 오염원(65, 40, 수심 3m) + 보조 오염원(25, 75, 표층)"도
"주 오염원(65, 40, 수심 1m) + 보조 오염원(25, 75, 표층 0.5m)"으로 수정.

- [ ] **Step 2: 측정 프로파일 상수 교체**

기존:

```python
AREA_SIZE = 100.0
GRID_STEP = 10.0
DEPTH_STEP = 0.5
MAX_DEPTH = 5.0
```

수정:

```python
AREA_SIZE = 100.0
GRID_STEP = 10.0
DEPTH_LEVELS = [0.5, 1.0, 1.5]  # 측정 수심 (m) — 각 수심 1분, 지점당 3분
DEPTH_DWELL = 3.0     # 수심당 측정 체류 시간 (s) — 데모용. 실제 운용은 60.0 (1분).
DEPTH_STEP = 0.5      # 센서 회수 속도 계산용
MAX_DEPTH = DEPTH_LEVELS[-1]
```

- [ ] **Step 3: simulator의 측정 상태 로직 교체**

`simulator()` 안 변수 초기화부에 `depth_idx = 0` 추가 (`depth = 0.0` 다음 줄).

기존 stabilizing/measuring 블록:

```python
        elif state == "stabilizing":
            if now >= state_until:
                state, depth = "measuring", 0.0
            battery -= 0.003
        elif state == "measuring":
            depth = min(depth + DEPTH_STEP, MAX_DEPTH)
            with LOCK:
                cell = HEATMAP.setdefault((x, y, depth), {})
                for s in SENSORS:
                    if now >= disconnected_until[s["id"]]:
                        v = round(s["read"](x, y, depth, rng), s["decimals"])
                        values[s["id"]] = v
                        acc = cell.setdefault(s["id"], [0.0, 0])
                        acc[0] += v
                        acc[1] += 1
            last_sample_at = datetime.now()
            if depth >= MAX_DEPTH:
                state = "retrieving"
            battery -= 0.005
```

수정 (각 수심에서 DEPTH_DWELL 동안 머물며 TICK마다 샘플 수집):

```python
        elif state == "stabilizing":
            if now >= state_until:
                state, depth_idx = "measuring", 0
                state_until = now + DEPTH_DWELL
            battery -= 0.003
        elif state == "measuring":
            depth = DEPTH_LEVELS[depth_idx]
            with LOCK:
                cell = HEATMAP.setdefault((x, y, depth), {})
                for s in SENSORS:
                    if now >= disconnected_until[s["id"]]:
                        v = round(s["read"](x, y, depth, rng), s["decimals"])
                        values[s["id"]] = v
                        acc = cell.setdefault(s["id"], [0.0, 0])
                        acc[0] += v
                        acc[1] += 1
            last_sample_at = datetime.now()
            if now >= state_until:  # 이 수심에서 1분(데모 3초) 경과 → 다음 수심
                depth_idx += 1
                if depth_idx >= len(DEPTH_LEVELS):
                    state = "retrieving"
                else:
                    state_until = now + DEPTH_DWELL
            battery -= 0.005
```

- [ ] **Step 4: SENSORS와 telemetry에 threshold 추가**

SENSORS의 두 항목에 `"threshold"` 키 추가:

```python
    {
        "id": "ph", "name": "pH", "unit": "", "decimals": 2,
        "threshold": SENSOR_INFO["ph"]["threshold"],
        "read": lambda x, y, d, rng: 7.10 - 0.04 * d - 1.1 * plume(x, y, d) + rng.gauss(0, 0.03),
    },
    {
        "id": "ec", "name": "EC 전기전도도", "unit": "µS/cm", "decimals": 0,
        "threshold": SENSOR_INFO["ec"]["threshold"],
        "read": lambda x, y, d, rng: 320 + 6 * d + 220 * plume(x, y, d) + rng.gauss(0, 4),
    },
```

TELEMETRY의 sensors 리스트 컴프리헨션에 필드 추가 — 기존:

```python
                        {
                            "id": s["id"],
                            "name": s["name"],
                            "unit": s["unit"],
                            "connected": now >= disconnected_until[s["id"]],
                            "value": values[s["id"]] if now >= disconnected_until[s["id"]] else None,
                        }
```

수정:

```python
                        {
                            "id": s["id"],
                            "name": s["name"],
                            "unit": s["unit"],
                            "threshold": s["threshold"],
                            "connected": now >= disconnected_until[s["id"]],
                            "value": values[s["id"]] if now >= disconnected_until[s["id"]] else None,
                        }
```

- [ ] **Step 5: 동작 확인**

포트 8000에서 돌고 있는 기존 서버가 있으면 중지한 뒤 (백그라운드 작업 중지 또는
`Get-NetTCPConnection -LocalPort 8000 | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }`),
`python dashboard_server.py`를 백그라운드로 재시작하고:

```powershell
Start-Sleep 8; Invoke-RestMethod http://localhost:8000/api/telemetry | ConvertTo-Json -Depth 5
```

Expected: `max_depth_m`가 1.5, `depth_m`가 0/0.5/1.0/1.5 중 하나, sensors 각 항목에 `threshold` 존재.

- [ ] **Step 6: 커밋**

```powershell
git add dashboard_server.py && git commit -m @'
feat: 시뮬레이터 측정 프로파일을 수심 3단계·수심당 체류로 변경, 임계값 필드 추가

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 4: dashboard_server.py — CSV 회차 로드 + /api/runs

**Files:**
- Modify: `dashboard_server.py`
- Create: `tests/test_server.py`

**Interfaces:**
- Produces: `load_runs(csv_path) -> (runs, meta)` — runs: `{run_id(int): {(x, y, depth): {sensor_id: [합계, 횟수]}}}`, meta: `[{"id": 1, "date": "2026-06-01", "samples": 1089}, ...]`. `merge_runs(runs) -> dict` (전체 누적, 같은 셀 구조). `resolve_run(run: str) -> (source dict | None, label str | None)`. HTTP `GET /api/runs` → `{"runs": [...meta...]}`. 모듈 전역 `RUNS`, `RUN_META`, `ALL_CELLS` (main()에서 채움).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_server.py`:

```python
# -*- coding: utf-8 -*-
import dashboard_server as srv


def make_csv(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text(
        "run_id,timestamp,x_m,y_m,depth_m,ph,ec\n"
        "1,2026-06-01 09:00:00,0,0,0.5,7.0,300\n"
        "1,2026-06-01 09:00:20,0,0,0.5,6.0,700\n"
        "2,2026-06-02 09:00:00,10,0,0.5,7.1,310\n",
        encoding="utf-8",
    )
    return p


def test_load_runs(tmp_path):
    runs, meta = srv.load_runs(make_csv(tmp_path))
    assert runs[1][(0.0, 0.0, 0.5)]["ph"] == [13.0, 2]
    assert runs[1][(0.0, 0.0, 0.5)]["ec"] == [1000.0, 2]
    assert meta == [
        {"id": 1, "date": "2026-06-01", "samples": 2},
        {"id": 2, "date": "2026-06-02", "samples": 1},
    ]


def test_load_runs_missing_file(tmp_path):
    runs, meta = srv.load_runs(tmp_path / "none.csv")
    assert runs == {} and meta == []


def test_merge_runs():
    runs = {
        1: {(0.0, 0.0, 0.5): {"ph": [7.0, 1]}},
        2: {(0.0, 0.0, 0.5): {"ph": [6.0, 1]}, (10.0, 0.0, 0.5): {"ec": [300.0, 1]}},
    }
    merged = srv.merge_runs(runs)
    assert merged[(0.0, 0.0, 0.5)]["ph"] == [13.0, 2]
    assert merged[(10.0, 0.0, 0.5)]["ec"] == [300.0, 1]
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_server.py -v`
Expected: FAIL — `AttributeError: module 'dashboard_server' has no attribute 'load_runs'`

- [ ] **Step 3: 로드·병합·해석 함수 구현**

`dashboard_server.py`의 import 블록에 `import csv` 추가.
`TELEMETRY = {}` 위쪽(상수 영역)에 추가:

```python
DATA_CSV = Path(__file__).parent / "data" / "measurements.csv"
RUNS = {}       # run_id → {(x, y, depth): {sensor_id: [합계, 횟수]}} — 과거 탐사 집계
RUN_META = []   # [{"id", "date", "samples"}, ...] — 회차 드롭다운용
ALL_CELLS = {}  # 전체 회차 누적 집계
```

`grid_path()` 함수 위에 추가:

```python
def load_runs(csv_path=DATA_CSV):
    """과거 탐사 CSV → (회차별 셀 집계, 회차 메타 목록). 파일이 없으면 빈 결과."""
    runs, meta = {}, {}
    if not Path(csv_path).exists():
        return {}, []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rid = int(row["run_id"])
            key = (float(row["x_m"]), float(row["y_m"]), float(row["depth_m"]))
            cell = runs.setdefault(rid, {}).setdefault(key, {})
            for sid in ("ph", "ec"):
                if row.get(sid):
                    acc = cell.setdefault(sid, [0.0, 0])
                    acc[0] += float(row[sid])
                    acc[1] += 1
            m = meta.setdefault(rid, {"id": rid, "date": row["timestamp"][:10], "samples": 0})
            m["samples"] += 1
    return runs, [meta[k] for k in sorted(meta)]


def merge_runs(runs):
    """모든 회차를 합친 누적 집계."""
    merged = {}
    for cells in runs.values():
        for key, acc in cells.items():
            m = merged.setdefault(key, {})
            for sid, (total, n) in acc.items():
                a = m.setdefault(sid, [0.0, 0])
                a[0] += total
                a[1] += n
    return merged


def resolve_run(run):
    """run 파라미터(live|all|회차 번호) → (셀 집계, 라벨). 모르는 값이면 (None, None)."""
    if run == "live":
        with LOCK:
            snap = {k: {s: list(a) for s, a in v.items()} for k, v in HEATMAP.items()}
        return snap, "실시간"
    if run == "all":
        return ALL_CELLS, "전체 누적"
    try:
        rid = int(run)
    except ValueError:
        return None, None
    return (RUNS[rid], f"{rid}차") if rid in RUNS else (None, None)
```

- [ ] **Step 4: /api/runs 핸들러와 main() 로드 추가**

`Handler.do_GET`의 `elif self.path.startswith("/api/heatmap"):` 앞에 추가:

```python
        elif self.path == "/api/runs":
            body = json.dumps({"runs": RUN_META}, ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
```

`main()` 시작부에 추가:

```python
def main():
    global RUNS, RUN_META, ALL_CELLS
    RUNS, RUN_META = load_runs()
    ALL_CELLS = merge_runs(RUNS)
    threading.Thread(target=simulator, daemon=True).start()
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_server.py -v`
Expected: 3개 전부 PASS

- [ ] **Step 6: API 동작 확인**

서버 재시작 후: `Invoke-RestMethod http://localhost:8000/api/runs | ConvertTo-Json -Depth 4`
Expected: 회차 1~8, 각 `samples` = 1089, `date` = 2026-06-01 ~ 2026-06-08.

- [ ] **Step 7: 커밋**

```powershell
git add dashboard_server.py tests/test_server.py && git commit -m @'
feat: 과거 탐사 CSV 회차별 로드와 /api/runs 추가

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 5: dashboard_server.py — /api/heatmap 회차 선택 + 오염 요약

**Files:**
- Modify: `dashboard_server.py`
- Modify: `tests/test_server.py` (테스트 추가)

**Interfaces:**
- Consumes: `resolve_run`, `thresholds.exceedance`
- Produces: `GET /api/heatmap?sensor=<id>&run=<live|all|N>` 응답에 `sensor.threshold`, `run`, `summary` 추가. `summary` = `{"polluted_cells": int, "worst": {"sensor", "value", "unit", "x", "y", "depth"} | null}` (pH·EC 둘 중 하나라도 초과 기준). 순수 함수 `cells_for(source, sensor_id, decimals) -> list`, `build_summary(source) -> dict`.

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_server.py` 끝에 추가:

```python
def test_cells_for_rounds_mean():
    source = {(0.0, 0.0, 0.5): {"ec": [604.0, 2]}}
    assert srv.cells_for(source, "ec", 0) == [[0.0, 0.0, 0.5, 302.0, 2]]


def test_build_summary_counts_either_sensor():
    source = {
        (0.0, 0.0, 0.5): {"ph": [7.0, 1], "ec": [600.0, 1]},   # EC만 초과 → 오염
        (10.0, 0.0, 0.5): {"ph": [7.0, 1], "ec": [300.0, 1]},  # 정상
    }
    s = srv.build_summary(source)
    assert s["polluted_cells"] == 1
    assert s["worst"]["sensor"] == "EC 전기전도도"
    assert s["worst"]["value"] == 600.0
    assert (s["worst"]["x"], s["worst"]["y"], s["worst"]["depth"]) == (0.0, 0.0, 0.5)


def test_build_summary_clean():
    s = srv.build_summary({(0.0, 0.0, 0.5): {"ph": [7.0, 1]}})
    assert s == {"polluted_cells": 0, "worst": None}
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_server.py -v`
Expected: 새 3개 FAIL (`no attribute 'cells_for'`)

- [ ] **Step 3: 함수 구현**

import에 `exceedance` 추가: `from thresholds import SENSOR_INFO, exceedance`

`resolve_run` 아래에 추가:

```python
def cells_for(source, sensor_id, decimals):
    """셀 집계 → [[x, y, 수심, 평균, 측정 횟수], ...]."""
    return [
        [x, y, d, round(acc[sensor_id][0] / acc[sensor_id][1], decimals), acc[sensor_id][1]]
        for (x, y, d), acc in source.items()
        if sensor_id in acc
    ]


def build_summary(source):
    """pH·EC 둘 중 하나라도 임계값을 넘는 셀 수와 최고 오염 셀."""
    polluted = 0
    worst = None  # (초과 비율, sensor_id, 평균, x, y, 수심)
    for (x, y, d), acc in source.items():
        cell_worst = None
        for sid, (total, n) in acc.items():
            r = exceedance(sid, total / n)
            if r > 0 and (cell_worst is None or r > cell_worst[0]):
                cell_worst = (r, sid, total / n, x, y, d)
        if cell_worst:
            polluted += 1
            if worst is None or cell_worst[0] > worst[0]:
                worst = cell_worst
    if worst is None:
        return {"polluted_cells": 0, "worst": None}
    r, sid, mean, x, y, d = worst
    info = SENSOR_INFO[sid]
    return {
        "polluted_cells": polluted,
        "worst": {
            "sensor": info["name"], "value": round(mean, info["decimals"]),
            "unit": info["unit"], "x": x, "y": y, "depth": d,
        },
    }
```

- [ ] **Step 4: /api/heatmap 핸들러 교체**

기존 `/api/heatmap` 분기 전체를 교체:

```python
        elif self.path.startswith("/api/heatmap"):
            query = parse_qs(urlparse(self.path).query)
            sensor_id = query.get("sensor", [SENSORS[0]["id"]])[0]
            run = query.get("run", ["live"])[0]
            meta = next((s for s in SENSORS if s["id"] == sensor_id), None)
            source, _ = resolve_run(run)
            if meta is None or source is None:
                self._send(404, "text/plain; charset=utf-8", b"unknown sensor or run")
                return
            body = json.dumps(
                {
                    "sensor": {
                        "id": sensor_id, "name": meta["name"], "unit": meta["unit"],
                        "threshold": meta["threshold"],
                    },
                    "run": run,
                    "cells": cells_for(source, sensor_id, meta["decimals"]),
                    "summary": build_summary(source),
                },
                ensure_ascii=False,
            ).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
```

(기존 분기 안의 LOCK 사용 셀 집계 코드는 `resolve_run`/`cells_for`로 대체되어 삭제.)

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_server.py -v`
Expected: 전부 PASS

- [ ] **Step 6: API 동작 확인**

서버 재시작 후:

```powershell
Invoke-RestMethod "http://localhost:8000/api/heatmap?sensor=ec&run=all" | ConvertTo-Json -Depth 4 | Select-Object -First 40
```

Expected: `sensor.threshold.max` = 500, `summary.polluted_cells` > 0, `summary.worst`에 위치·값 존재. `run=3`, `run=live`도 200 응답, `run=99`는 404.

- [ ] **Step 7: 커밋**

```powershell
git add dashboard_server.py tests/test_server.py && git commit -m @'
feat: /api/heatmap 회차 선택·임계값·오염 요약 추가

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 6: dashboard_server.py — /api/export Excel 다운로드

**Files:**
- Modify: `dashboard_server.py`
- Modify: `tests/test_server.py` (테스트 추가)

**Interfaces:**
- Consumes: `resolve_run`, `thresholds.pollution_reason`
- Produces: `GET /api/export?run=<live|all|N>` → xlsx 첨부파일(`hiflow_export_<run>.xlsx`, 시트 "셀별 데이터", 오염 행 빨간 배경). openpyxl이 없으면 CSV(utf-8-sig)로 대체. 순수 함수 `build_export_rows(source, label) -> list`, `export_xlsx(rows) -> bytes`, `export_csv(rows) -> bytes`.

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_server.py` 끝에 추가:

```python
def test_build_export_rows():
    source = {(0.0, 0.0, 0.5): {"ph": [6.0, 1], "ec": [600.0, 1]}}
    rows = srv.build_export_rows(source, "1차")
    assert rows == [["1차", 0.0, 0.0, 0.5, 6.0, 600.0, 1, "오염", "pH·EC"]]


def test_build_export_rows_clean():
    source = {(0.0, 0.0, 0.5): {"ph": [7.0, 1], "ec": [300.0, 1]}}
    rows = srv.build_export_rows(source, "실시간")
    assert rows[0][7] == "정상" and rows[0][8] == ""


def test_export_xlsx_roundtrip():
    import io

    from openpyxl import load_workbook

    rows = [["1차", 0.0, 0.0, 0.5, 6.0, 600.0, 1, "오염", "pH·EC"]]
    wb = load_workbook(io.BytesIO(srv.export_xlsx(rows)))
    ws = wb["셀별 데이터"]
    assert ws.max_row == 2
    assert ws.cell(2, 8).value == "오염"


def test_export_csv_has_bom():
    rows = [["1차", 0.0, 0.0, 0.5, 6.0, 600.0, 1, "오염", "pH·EC"]]
    data = srv.export_csv(rows)
    assert data.startswith(b"\xef\xbb\xbf")  # Excel 한글 인식용 BOM
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_server.py -v`
Expected: 새 4개 FAIL

- [ ] **Step 3: 내보내기 함수 구현**

import 수정: `from thresholds import SENSOR_INFO, exceedance, pollution_reason`

`build_summary` 아래에 추가:

```python
EXPORT_HEADER = ["탐사", "X (m)", "Y (m)", "수심 (m)", "평균 pH", "평균 EC (µS/cm)", "측정 횟수", "판정", "사유"]


def build_export_rows(source, label):
    """셀 집계 → 내보내기 행 목록 (좌표 정렬, 오염 판정 포함)."""
    rows = []
    for (x, y, d), acc in sorted(source.items()):
        ph = round(acc["ph"][0] / acc["ph"][1], 2) if "ph" in acc else None
        ec = round(acc["ec"][0] / acc["ec"][1], 0) if "ec" in acc else None
        n = max((a[1] for a in acc.values()), default=0)
        reason = pollution_reason(ph, ec)
        rows.append([label, x, y, d, ph, ec, n, "오염" if reason else "정상", reason])
    return rows


def export_xlsx(rows):
    """openpyxl 미설치면 ImportError — 호출부에서 CSV로 대체한다."""
    import io

    from openpyxl import Workbook
    from openpyxl.styles import PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "셀별 데이터"
    ws.append(EXPORT_HEADER)
    red = PatternFill("solid", start_color="FFF4CCCC")
    for row in rows:
        ws.append(row)
        if row[7] == "오염":
            for cell in ws[ws.max_row]:
                cell.fill = red
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_csv(rows):
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(EXPORT_HEADER)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")
```

- [ ] **Step 4: /api/export 핸들러 추가**

`/api/heatmap` 분기 다음에 추가:

```python
        elif self.path.startswith("/api/export"):
            query = parse_qs(urlparse(self.path).query)
            run = query.get("run", ["live"])[0]
            source, label = resolve_run(run)
            if source is None:
                self._send(404, "text/plain; charset=utf-8", b"unknown run")
                return
            rows = build_export_rows(source, label)
            try:
                body, ext = export_xlsx(rows), "xlsx"
                ctype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            except ImportError:
                body, ext = export_csv(rows), "csv"
                ctype = "text/csv; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Disposition", f'attachment; filename="hiflow_export_{run}.{ext}"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/ -v`
Expected: 전부 PASS

- [ ] **Step 6: 다운로드 동작 확인**

서버 재시작 후:

```powershell
Invoke-WebRequest "http://localhost:8000/api/export?run=all" -OutFile "$env:TEMP\hiflow_test.xlsx"; (Get-Item "$env:TEMP\hiflow_test.xlsx").Length
```

Expected: 파일 크기 > 5000 바이트. (xlsx는 ZIP — 첫 2바이트가 `PK`.)

- [ ] **Step 7: 커밋**

```powershell
git add dashboard_server.py tests/test_server.py && git commit -m @'
feat: /api/export — 셀별 집계 Excel 다운로드 (오염 행 빨간 강조)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 7: dashboard.html — 회차 드롭다운 + Excel 버튼 + 수심 문구

**Files:**
- Modify: `dashboard.html`

**Interfaces:**
- Consumes: `GET /api/runs`, `GET /api/heatmap?sensor=&run=`, `GET /api/export?run=`
- Produces: 전역 `hmRun`(현재 선택 회차, 기본 "live"), `#hm-run` select, `#hm-export` 버튼 — Task 8이 이 전역을 그대로 사용.

- [ ] **Step 1: CSS — 버튼 스타일 추가**

기존:

```css
  .heatmap-card select {
    background: var(--surface); color: var(--ink); border: 1px solid var(--border);
    border-radius: 6px; padding: 4px 8px; font: inherit; font-size: 13px;
  }
```

수정:

```css
  .heatmap-card select, .heatmap-card button {
    background: var(--surface); color: var(--ink); border: 1px solid var(--border);
    border-radius: 6px; padding: 4px 8px; font: inherit; font-size: 13px;
  }
  .heatmap-card button { cursor: pointer; }
```

- [ ] **Step 2: HTML — 드롭다운·버튼·수심 문구**

히트맵 카드 헤더의 `<span>` 내용 교체. 기존:

```html
      <span>
        <label class="sub">보기 형태
          <select id="hm-view" aria-label="히트맵 보기 형태 선택">
            <option value="bars">막대 (지점별 평균)</option>
            <option value="cells">셀 (수심별 상세)</option>
          </select>
        </label>
        <label class="sub" style="margin-left:10px">표시 항목
          <select id="hm-sensor" aria-label="히트맵 표시 센서 선택"></select>
        </label>
      </span>
```

수정:

```html
      <span>
        <label class="sub">탐사 회차
          <select id="hm-run" aria-label="탐사 회차 선택">
            <option value="live">실시간</option>
          </select>
        </label>
        <label class="sub" style="margin-left:10px">보기 형태
          <select id="hm-view" aria-label="히트맵 보기 형태 선택">
            <option value="bars">막대 (지점별 평균)</option>
            <option value="cells">셀 (수심별 상세)</option>
          </select>
        </label>
        <label class="sub" style="margin-left:10px">표시 항목
          <select id="hm-sensor" aria-label="히트맵 표시 센서 선택"></select>
        </label>
        <button id="hm-export" type="button" style="margin-left:10px">Excel 내보내기</button>
      </span>
```

수심 카드 문구 교체. 기존:

```html
        <div class="sub">최대 <span id="max-depth">—</span> m · 0.5 m 간격 측정</div>
```

수정:

```html
        <div class="sub">최대 <span id="max-depth">—</span> m · 수심당 1분, 지점당 3분 측정</div>
```

- [ ] **Step 3: JS — 회차 상태·목록 로드·내보내기**

`let hmSensor = null;` 아래에 `let hmRun = "live";` 추가.

`hmFetch`의 fetch URL 교체. 기존:

```js
  const r = await fetch(`/api/heatmap?sensor=${hmSensor}`, { cache: "no-store" });
```

수정:

```js
  const r = await fetch(`/api/heatmap?sensor=${hmSensor}&run=${hmRun}`, { cache: "no-store" });
```

`$("hm-sensor").addEventListener(...)` 줄 앞에 추가:

```js
// ── 탐사 회차 선택: /api/runs 로 과거 회차 목록 구성 (CSV 없으면 실시간만) ──
async function loadRuns() {
  try {
    const r = await fetch("/api/runs", { cache: "no-store" });
    if (!r.ok) return;
    const { runs } = await r.json();
    if (!runs.length) return;
    $("hm-run").innerHTML =
      '<option value="live">실시간</option><option value="all">전체 누적</option>' +
      runs.map((x) => `<option value="${x.id}">${x.id}차 (${x.date})</option>`).join("");
    $("hm-run").value = hmRun;
  } catch { /* 서버 미지원·오프라인이면 실시간만 유지 */ }
}
loadRuns();

$("hm-run").addEventListener("change", (e) => { hmRun = e.target.value; hmFetch().catch(() => {}); });
$("hm-export").addEventListener("click", () => { location.href = `/api/export?run=${hmRun}`; });
```

- [ ] **Step 4: Playwright로 동작 확인**

서버가 떠 있는 상태에서 Playwright MCP로 `http://localhost:8000` 접속 →
snapshot에서 "탐사 회차" 드롭다운(실시간/전체 누적/1차~8차)과 "Excel 내보내기" 버튼 확인 →
"전체 누적" 선택 후 히트맵 셀 수가 즉시 늘어나는지(전 지점 채워짐) 확인.
수심 카드에 "수심당 1분, 지점당 3분 측정" 문구 확인.

- [ ] **Step 5: 커밋**

```powershell
git add dashboard.html && git commit -m @'
feat: 대시보드 탐사 회차 드롭다운·Excel 내보내기 버튼 추가

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 8: dashboard.html — 오염 빨간 표시 + 요약 줄 + 막대 경사 강조

**Files:**
- Modify: `dashboard.html`

**Interfaces:**
- Consumes: `/api/heatmap` 응답의 `sensor.threshold`·`summary`, `/api/telemetry` sensors의 `threshold`
- Produces: `overThreshold(t, v)` 헬퍼, `POLLUTED` 색 상수, `#hm-summary` 요약 줄.

- [ ] **Step 1: HTML — 요약 줄 요소 추가**

히트맵 카드의 안내 문구 div 아래에 추가. 기존:

```html
    <div class="sub" style="margin-top:0">
      측정이 누적될수록 셀이 채워진다 · 격자 셀 <span id="hm-count">0</span>개
      · 마우스 드래그로 회전, 셀에 올리면 상세값 표시
    </div>
```

바로 다음 줄에 추가:

```html
    <div class="sub" id="hm-summary" style="margin-top:4px"></div>
```

- [ ] **Step 2: JS — 임계값 헬퍼와 오염색 상수**

`const COLORSCALE = ...` 줄 다음에 추가:

```js
const POLLUTED = "#d03b3b";   // 임계값 초과(오염) 표시색 — Plotly 내부라 CSS 변수 사용 불가
function overThreshold(t, v) {
  return !!t && v !== null && v !== undefined &&
    ((t.min !== undefined && v < t.min) || (t.max !== undefined && v > t.max));
}
```

- [ ] **Step 3: JS — 센서 카드 현재값 빨간 표시**

`renderSensor`의 connected 분기 수정. 기존:

```js
  if (s.connected) {
    c.val.textContent = s.value !== null ? s.value : "—";
    c.dot.style.background = "var(--st-good)";
```

수정:

```js
  if (s.connected) {
    c.val.textContent = s.value !== null ? s.value : "—";
    c.val.style.color = overThreshold(s.threshold, s.value) ? "var(--st-critical)" : "";
    c.dot.style.background = "var(--st-good)";
```

- [ ] **Step 4: JS — renderHeatmap에 요약 줄 렌더링 추가**

기존:

```js
function renderHeatmap(data) {
  const cells = data.cells;
  $("hm-count").textContent = cells.length;
  if (!cells.length) return;
```

수정:

```js
function renderHeatmap(data) {
  const cells = data.cells;
  $("hm-count").textContent = cells.length;
  renderSummary(data.summary);
  if (!cells.length) return;
```

그리고 `renderHeatmap` 함수 아래에 추가:

```js
// ── 오염 요약 한 줄: pH·EC 둘 중 하나라도 임계값을 넘는 셀 기준 ──────
function renderSummary(s) {
  const el = $("hm-summary");
  if (!s || !s.polluted_cells) {
    el.textContent = "오염 셀 없음 · 기준: pH 6.5~8.5 / EC 500 µS/cm 이하";
    el.style.color = "var(--muted)";
    return;
  }
  const w = s.worst;
  el.textContent = `⚠ 오염 셀 ${s.polluted_cells}개 · 최고 ${w.sensor} ${w.value}${w.unit}`
    + ` @ (X ${w.x} m, Y ${w.y} m, 수심 ${w.depth} m)`;
  el.style.color = "var(--st-critical)";
}
```

- [ ] **Step 5: JS — renderBars 교체 (경사 강조 + 오염 빨강)**

`renderBars` 함수 전체와 그 위 주석을 다음으로 교체:

```js
// ── 막대 뷰: (X, Y) 지점별 수심 평균 — 경사 강조·오염 빨강 ──────────
const BAR_EXAGGERATION = 2.5;   // 멱지수 — 클수록 높은 값이 더 가파르게 솟는다

function renderBars(data) {
  const byXY = new Map();
  data.cells.forEach(([x, y, , v, n]) => {
    const key = `${x},${y}`;
    const a = byXY.get(key) || { x, y, sum: 0, depths: 0, samples: 0 };
    a.sum += v; a.depths += 1; a.samples += n;
    byXY.set(key, a);
  });
  const bars = [...byXY.values()].map((a) => ({ ...a, v: a.sum / a.depths }));
  const vals = bars.map((b) => b.v);
  const vmin = Math.min(...vals), vmax = Math.max(...vals), span = vmax - vmin || 1;
  // 경사 강조: 정규화 값에 멱함수 — 낮은 막대는 깔리고 높은 막대는 급하게 솟는다.
  // 최소 2% 높이를 보장해 가장 낮은 지점도 보이게 한다. 툴팁 수치는 실제 값 그대로.
  const barH = (v) => (0.02 + 0.98 * Math.pow((v - vmin) / span, BAR_EXAGGERATION)) * span;
  const th = data.sensor.threshold;

  // Plotly 에는 3D 막대가 없어 지점마다 직육면체를 Mesh3d 로 만든다.
  const W = 3.5;  // 막대 반폭 (격자 10m — 막대 7m + 간격 3m)
  const quads = [[0,1,2,3],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]];
  const mesh = () => ({ X: [], Y: [], Z: [], I: [], J: [], K: [], INT: [] });
  const normal = mesh(), bad = mesh();
  bars.forEach((b) => {
    const m = overThreshold(th, b.v) ? bad : normal;
    const o = m.X.length, h = barH(b.v);
    [[-W,-W,0],[W,-W,0],[W,W,0],[-W,W,0],[-W,-W,h],[W,-W,h],[W,W,h],[-W,W,h]]
      .forEach(([dx, dy, z]) => { m.X.push(b.x + dx); m.Y.push(b.y + dy); m.Z.push(z); m.INT.push(b.v); });
    quads.forEach(([a, c, d, e]) => { m.I.push(o+a, o+a); m.J.push(o+c, o+d); m.K.push(o+d, o+e); });
  });

  const lighting = { ambient: 0.75, diffuse: 0.4, specular: 0.05 };
  const traces = [];
  if (normal.X.length) traces.push({
    type: "mesh3d", x: normal.X, y: normal.Y, z: normal.Z, i: normal.I, j: normal.J, k: normal.K,
    intensity: normal.INT, colorscale: COLORSCALE, cmin: vmin, cmax: vmax,
    flatshading: true, hoverinfo: "skip", lighting,
    colorbar: hmColorbar(`평균 ${data.sensor.name}${data.sensor.unit ? `<br>(${data.sensor.unit})` : ""}`),
  });
  if (bad.X.length) traces.push({   // 임계값 초과 막대 — 빨간색
    type: "mesh3d", x: bad.X, y: bad.Y, z: bad.Z, i: bad.I, j: bad.J, k: bad.K,
    color: POLLUTED, flatshading: true, hoverinfo: "skip", lighting,
  });
  traces.push({ // 막대 상단의 투명 마커 — 호버 툴팁 전용 (실제 측정값 표시)
    type: "scatter3d", mode: "markers",
    x: bars.map((b) => b.x), y: bars.map((b) => b.y), z: bars.map((b) => barH(b.v)),
    customdata: bars.map((b) => [b.v, b.depths, b.samples, overThreshold(th, b.v) ? "⚠ 오염" : "정상"]),
    marker: { size: 14, color: "rgba(0,0,0,0)" },
    hovertemplate: "위치 X: %{x:.0f} m<br>위치 Y: %{y:.0f} m<br>" +
      `평균 ${data.sensor.name}: %{customdata[0]:.2f} ${data.sensor.unit}<br>` +
      "판정: %{customdata[3]}<br>수심 셀 %{customdata[1]}개 · 누적 측정 %{customdata[2]}회<extra></extra>",
    showlegend: false,
  });

  Plotly.react("hm-plot", traces, {
    uirevision: "bars",
    paper_bgcolor: HM_INK.surface,
    font: { family: 'system-ui, "Segoe UI", "Malgun Gothic", sans-serif' },
    scene: {
      xaxis: hmAxis("동서 위치 X (m)", [-5, 105]),
      yaxis: hmAxis("남북 위치 Y (m)", [-5, 105]),
      // 경사 강조로 높이가 실제 값과 다르므로 z축 눈금은 숨긴다 — 값은 색·툴팁으로 읽는다.
      zaxis: { ...hmAxis("", [0, span * 1.1]), showticklabels: false },
      aspectmode: "manual", aspectratio: { x: 1, y: 1, z: 0.6 },
      camera: { eye: { x: 1.6, y: -1.6, z: 0.8 } },
      bgcolor: HM_INK.surface,
    },
    margin: { l: 0, r: 0, t: 6, b: 0 },
  }, { displayModeBar: false, responsive: true });
}
```

- [ ] **Step 6: JS — renderCells 교체 (오염 셀 빨간 다이아몬드)**

`renderCells` 함수 전체와 그 위 주석을 다음으로 교체:

```js
// ── 셀 뷰: (X, Y, 수심) 셀별 평균 — 임계값 초과 셀은 빨간 다이아몬드 ──
function renderCells(data) {
  const cells = data.cells;
  const th = data.sensor.threshold;
  const vals = cells.map((c) => c[3]);
  const min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1;
  const size = (v) => 3 + Math.pow((v - min) / span, 1.5) * 11;
  const normal = cells.filter((c) => !overThreshold(th, c[3]));
  const bad = cells.filter((c) => overThreshold(th, c[3]));
  const base = (cs) => ({
    type: "scatter3d", mode: "markers", showlegend: false,
    x: cs.map((c) => c[0]), y: cs.map((c) => c[1]), z: cs.map((c) => c[2]),
    customdata: cs.map((c) => [c[3], c[4]]),
    hovertemplate: "위치 X: %{x:.0f} m<br>위치 Y: %{y:.0f} m<br>수심: %{z:.1f} m<br>" +
      `평균 ${data.sensor.name}: %{customdata[0]} ${data.sensor.unit}<br>누적 측정: %{customdata[1]}회<extra></extra>`,
  });
  const traces = [];
  if (normal.length) traces.push({
    ...base(normal),
    marker: {
      size: normal.map((c) => size(c[3])), symbol: "square",
      color: normal.map((c) => c[3]), colorscale: COLORSCALE, cmin: min, cmax: max, opacity: 0.85,
      colorbar: hmColorbar(`평균 ${data.sensor.name}${data.sensor.unit ? `<br>(${data.sensor.unit})` : ""}`),
    },
  });
  if (bad.length) traces.push({   // 임계값 초과 셀 — 빨간 다이아몬드
    ...base(bad),
    marker: { size: bad.map((c) => size(c[3]) + 2), symbol: "diamond", color: POLLUTED, opacity: 0.95 },
  });
  Plotly.react("hm-plot", traces, {
    uirevision: "keep",   // 갱신 시 사용자가 돌려놓은 카메라 시점 유지
    paper_bgcolor: HM_INK.surface,
    font: { family: 'system-ui, "Segoe UI", "Malgun Gothic", sans-serif' },
    scene: {
      xaxis: hmAxis("동서 위치 X (m)", [-5, 105]),
      yaxis: hmAxis("남북 위치 Y (m)", [-5, 105]),
      zaxis: hmAxis("수심 (m)", [1.8, 0]),
      aspectmode: "manual", aspectratio: { x: 1, y: 1, z: 0.5 },
      camera: { eye: { x: 1.5, y: -1.5, z: 0.9 } },
      bgcolor: HM_INK.surface,
    },
    margin: { l: 0, r: 0, t: 6, b: 0 },
  }, { displayModeBar: false, responsive: true });
}
```

(주의: z축 범위가 기존 `[5.4, 0]`에서 측정 수심 1.5 m에 맞춘 `[1.8, 0]`으로 바뀐다.
기존 renderCells가 쓰던 지역 `axis` 객체는 `hmAxis` 재사용으로 대체되어 삭제된다.)

- [ ] **Step 7: Playwright로 동작 확인**

`http://localhost:8000` 접속 → "전체 누적" 회차 선택:
1. 막대 뷰에서 오염원 부근 막대가 빨갛고 주변보다 가파르게 솟는지 스크린샷 확인.
2. 요약 줄에 "⚠ 오염 셀 N개 · 최고 …" 빨간 문구 확인.
3. 셀 뷰로 전환 → 빨간 다이아몬드 셀 확인.
4. EC 센서 카드 값이 오염 지점 통과 시 빨간색인지 확인 (실시간 값이라 시점에 따라 다름 — 요약 줄과 히트맵 확인이 우선).

- [ ] **Step 8: 커밋**

```powershell
git add dashboard.html && git commit -m @'
feat: 대시보드 오염 셀 빨간 표시·요약 줄·막대 경사 강조

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 9: visualize_heatmap.py — 회차·센서 드롭다운 + 오염 표시

**Files:**
- Modify: `visualize_heatmap.py` (전체 재작성)

**Interfaces:**
- Consumes: `thresholds.SENSOR_INFO`, `thresholds.is_polluted`, `data/measurements.csv`(ph·ec)
- Produces: `output/heatmap_3d.html` (드롭다운: 회차×센서 조합), `output/heatmap_3d_ph.png`, `output/heatmap_3d_ec.png`. 기존 `output/heatmap_3d.png`는 삭제.

참고: 스펙은 "드롭다운 2개(회차/센서)"라고 했지만 Plotly updatemenus 두 개는 서로의
상태를 알 수 없어 조합 드롭다운 하나("전체 누적 · pH", "1차 · EC", …)로 구현한다 —
기능은 동일(회차·센서 모두 선택 가능).

- [ ] **Step 1: visualize_heatmap.py 전체 재작성**

```python
# -*- coding: utf-8 -*-
"""Hi-Flow 누적 측정 데이터 3D 히트맵 시각화.

data/measurements.csv (run_id, timestamp, x_m, y_m, depth_m, ph, ec) 를
(X, Y, 수심) 격자 셀별 평균으로 집계해
  1) output/heatmap_3d.html — 드롭다운으로 탐사 회차·센서를 고르는 인터랙티브 3D 히트맵
  2) output/heatmap_3d_ph.png, heatmap_3d_ec.png — 전체 누적 기준 보고서용 정적 이미지
를 만든다.

오염 판정(thresholds.py): pH 6.5~8.5 벗어남 또는 EC 500 µS/cm 초과 → 빨간 다이아몬드.
색상: 정상 셀은 단일 색상(파랑) 순차 램프 (밝음 = 낮음 → 어두움 = 높음).
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from matplotlib.colors import LinearSegmentedColormap

from thresholds import SENSOR_INFO, is_polluted

# ── 색상 정의 ────────────────────────────────────────────────────
BLUE_RAMP = [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
    "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b",
]
POLLUTED_COLOR = "#d03b3b"  # 임계값 초과(오염) 표시색
SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"

DATA_PATH = Path(__file__).parent / "data" / "measurements.csv"
OUT_DIR = Path(__file__).parent / "output"
SENSOR_IDS = ["ph", "ec"]


def aggregate(df, sensor_id):
    """(x, y, 수심) 셀별 평균·측정 수 집계 + 오염 판정."""
    agg = (
        df.groupby(["x_m", "y_m", "depth_m"])[sensor_id]
        .agg(mean="mean", n_samples="count")
        .reset_index()
    )
    agg["mean"] = agg["mean"].round(SENSOR_INFO[sensor_id]["decimals"])
    agg["polluted"] = [is_polluted(sensor_id, v) for v in agg["mean"]]
    return agg


def emphasis(sensor_id, values):
    """클수록 '오염에 가까움' — 마커 크기용 강조 지표.

    상한형(EC)은 값 그대로, 범위형(pH)은 정상 범위 중앙에서 멀수록 크게.
    """
    t = SENSOR_INFO[sensor_id]["threshold"]
    v = np.asarray(values, dtype=float)
    if "min" in t and "max" in t:
        return np.abs(v - (t["min"] + t["max"]) / 2)
    return v


def marker_sizes(emph, lo=3.0, hi=16.0):
    span = (emph.max() - emph.min()) or 1.0
    v = (emph - emph.min()) / span
    return lo + v**1.5 * (hi - lo)


def sensor_label(sensor_id):
    info = SENSOR_INFO[sensor_id]
    return f"{info['name']}{f' ({info['unit']})' if info['unit'] else ''}"


def make_traces(agg, sensor_id):
    """조합(회차 x 센서) 하나의 트레이스 2개: 정상(파랑 램프) + 오염(빨간 다이아몬드)."""
    info = SENSOR_INFO[sensor_id]
    sizes = marker_sizes(emphasis(sensor_id, agg["mean"]))
    colorscale = [[i / (len(BLUE_RAMP) - 1), c] for i, c in enumerate(BLUE_RAMP)]
    hover = (
        "위치 X: %{x:.0f} m<br>위치 Y: %{y:.0f} m<br>수심: %{z:.1f} m<br>"
        f"평균 {info['name']}: %{{customdata[0]}}{f' {info['unit']}' if info['unit'] else ''}<br>"
        "누적 측정: %{customdata[1]}회<extra></extra>"
    )

    def scatter(rows, row_sizes, marker_extra, name, showlegend):
        return go.Scatter3d(
            x=rows["x_m"], y=rows["y_m"], z=rows["depth_m"],
            mode="markers", name=name, showlegend=showlegend, visible=False,
            customdata=np.stack([rows["mean"], rows["n_samples"]], axis=-1) if len(rows) else None,
            marker=dict(size=row_sizes, opacity=0.85, **marker_extra),
            hovertemplate=hover,
        )

    normal, bad = agg[~agg["polluted"]], agg[agg["polluted"]]
    return [
        scatter(
            normal, sizes[~agg["polluted"]],
            dict(
                symbol="square", color=normal["mean"], colorscale=colorscale,
                colorbar=dict(
                    title=dict(text=f"평균 {info['name']}" + (f"<br>({info['unit']})" if info["unit"] else ""),
                               font=dict(color=INK_SECONDARY, size=13)),
                    tickfont=dict(color=INK_MUTED, size=12), thickness=14, len=0.6,
                ),
            ),
            "정상", False,
        ),
        scatter(
            bad, sizes[agg["polluted"]] + 2,
            dict(symbol="diamond", color=POLLUTED_COLOR),
            "오염 (임계값 초과)", True,
        ),
    ]


def make_html(df):
    """회차 x 센서 조합 드롭다운이 있는 인터랙티브 HTML."""
    options = [("전체 누적", df)] + [
        (f"{int(rid)}차 탐사", part) for rid, part in df.groupby("run_id")
    ]
    traces, labels = [], []
    for run_label, part in options:
        for sid in SENSOR_IDS:
            traces.extend(make_traces(aggregate(part, sid), sid))
            labels.append(f"{run_label} · {SENSOR_INFO[sid]['name']}")
    traces[0].visible = traces[1].visible = True  # 기본: 전체 누적 · pH

    buttons = [
        dict(label=label, method="update",
             args=[{"visible": [j // 2 == ci for j in range(len(traces))]}])
        for ci, label in enumerate(labels)
    ]

    axis_style = dict(
        gridcolor=GRIDLINE, zerolinecolor=GRIDLINE, backgroundcolor=SURFACE,
        title_font=dict(color=INK_SECONDARY, size=13),
        tickfont=dict(color=INK_MUTED, size=11),
    )
    fig = go.Figure(traces)
    fig.update_layout(
        title=dict(
            text="수질 3D 히트맵 — 누적 측정 데이터<br>"
            "<sup>드롭다운으로 탐사 회차·센서 선택 · 빨간 다이아몬드 = 임계값 초과 오염 셀"
            " (pH 6.5~8.5 / EC 500 µS/cm)</sup>",
            font=dict(color=INK_PRIMARY, size=18), x=0.02,
        ),
        updatemenus=[dict(
            buttons=buttons, x=0.02, y=1.0, xanchor="left", yanchor="top",
            bgcolor=SURFACE, bordercolor=GRIDLINE,
            font=dict(color=INK_SECONDARY, size=13),
        )],
        legend=dict(font=dict(color=INK_SECONDARY), x=0.8, y=0.95),
        scene=dict(
            xaxis=dict(title="동서 위치 X (m)", **axis_style),
            yaxis=dict(title="남북 위치 Y (m)", **axis_style),
            zaxis=dict(title="수심 (m)", autorange="reversed", **axis_style),
            aspectmode="manual",
            aspectratio=dict(x=1, y=1, z=0.5),
            camera=dict(eye=dict(x=1.5, y=-1.5, z=0.9)),
        ),
        paper_bgcolor=SURFACE,
        font=dict(family='system-ui, "Segoe UI", "Malgun Gothic", sans-serif'),
        margin=dict(l=0, r=0, t=90, b=0),
    )

    out = OUT_DIR / "heatmap_3d.html"
    fig.write_html(out, include_plotlyjs="cdn")
    print(f"저장 완료: {out}")


def make_png(df, sensor_id):
    """전체 누적 기준 보고서용 정적 이미지 (센서별 1장)."""
    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False
    info = SENSOR_INFO[sensor_id]
    agg = aggregate(df, sensor_id)
    sizes = marker_sizes(emphasis(sensor_id, agg["mean"]), lo=6, hi=90)
    cmap = LinearSegmentedColormap.from_list("hiflow_blue", BLUE_RAMP)
    normal, bad = agg[~agg["polluted"]], agg[agg["polluted"]]

    fig = plt.figure(figsize=(11, 8), facecolor=SURFACE)
    ax = fig.add_subplot(projection="3d")
    ax.set_facecolor(SURFACE)

    sc = ax.scatter(
        normal["x_m"], normal["y_m"], normal["depth_m"],
        c=normal["mean"], cmap=cmap, s=sizes[~agg["polluted"]],
        marker="s", alpha=0.85, linewidths=0,
    )
    if len(bad):
        ax.scatter(
            bad["x_m"], bad["y_m"], bad["depth_m"],
            c=POLLUTED_COLOR, s=sizes[agg["polluted"]] * 1.2,
            marker="D", alpha=0.95, linewidths=0, label="오염 (임계값 초과)",
        )
        ax.legend(loc="upper right", framealpha=0.9)
    ax.invert_zaxis()  # 아래로 갈수록 깊은 수심
    ax.set_xlabel("동서 위치 X (m)", color=INK_SECONDARY)
    ax.set_ylabel("남북 위치 Y (m)", color=INK_SECONDARY)
    ax.set_zlabel("수심 (m)", color=INK_SECONDARY)
    ax.tick_params(colors=INK_MUTED, labelsize=9)
    ax.set_title(
        f"수질 3D 히트맵 — {sensor_label(sensor_id)} (전체 누적)\n"
        "빨간 다이아몬드 = 임계값 초과 오염 셀 (pH 6.5~8.5 / EC 500 µS/cm)",
        color=INK_PRIMARY, fontsize=13, pad=15,
    )
    cbar = fig.colorbar(sc, ax=ax, shrink=0.55, pad=0.08)
    cbar.set_label(f"평균 {sensor_label(sensor_id)}", color=INK_SECONDARY)
    cbar.ax.tick_params(colors=INK_MUTED)

    out = OUT_DIR / f"heatmap_3d_{sensor_id}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    print(f"저장 완료: {out}")


def main():
    if not DATA_PATH.exists():
        raise SystemExit("data/measurements.csv 가 없습니다. 먼저 generate_data.py 를 실행하세요.")
    df = pd.read_csv(DATA_PATH)
    missing = {"ph", "ec"} - set(df.columns)
    if missing:
        raise SystemExit(f"CSV에 {missing} 컬럼이 없습니다. generate_data.py 를 다시 실행하세요.")
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "heatmap_3d.png").unlink(missing_ok=True)  # 구버전 산출물 제거
    total_cells = len(aggregate(df, "ph"))
    print(f"집계 완료: 격자 셀 {total_cells:,}개 x 회차 {df['run_id'].nunique()}회")
    make_html(df)
    for sid in SENSOR_IDS:
        make_png(df, sid)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 렌더링 실행**

Run: `python visualize_heatmap.py`
Expected: HTML 1개 + PNG 2개 저장 로그, 오류 없음.

- [ ] **Step 3: PNG 육안 확인**

Read 도구로 `output/heatmap_3d_ph.png`, `output/heatmap_3d_ec.png`를 열어:
한글 레이블 정상, 오염원 (65~75, 40) 부근 수심 0.5~1.5 m에 빨간 다이아몬드 군집, 범례 표시 확인.

- [ ] **Step 4: HTML 드롭다운 확인**

Playwright MCP로 `output/heatmap_3d.html` (file:// 경로) 접속 → 드롭다운에서
"3차 탐사 · EC 전기전도도" 선택 → 차트가 바뀌고 빨간 마커가 있는지 확인.
(회차가 지날수록 주 오염원이 동쪽으로 이동 — 1차와 8차의 핫스팟 X 위치가 달라야 함.)

- [ ] **Step 5: 커밋**

```powershell
git add visualize_heatmap.py && git commit -m @'
feat: 오프라인 3D 히트맵 — 회차·센서 드롭다운, 오염 셀 빨간 표시

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 10: export_report.py — Excel 요약 보고서

**Files:**
- Create: `export_report.py`
- Create: `tests/test_export_report.py`

**Interfaces:**
- Consumes: `thresholds` 모듈, `data/measurements.csv`
- Produces: `output/report.xlsx` (시트 "회차별 요약", "오염 셀 목록", "셀별 전체 데이터"). 순수 함수 `cell_means(df) -> DataFrame` (컬럼 run_id, x_m, y_m, depth_m, ph_mean, ec_mean, n, reason, severity), `run_summary(df, cells) -> DataFrame`, `write_report(df, out_path) -> None`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_export_report.py`:

```python
# -*- coding: utf-8 -*-
import pandas as pd

from export_report import cell_means, run_summary, write_report


def make_df():
    return pd.DataFrame(
        {
            "run_id": [1, 1, 1, 2],
            "timestamp": ["2026-06-01 09:00:00"] * 3 + ["2026-06-02 09:00:00"],
            "x_m": [0.0, 0.0, 10.0, 0.0],
            "y_m": [0.0, 0.0, 0.0, 0.0],
            "depth_m": [0.5, 0.5, 0.5, 0.5],
            "ph": [6.0, 6.2, 7.0, 7.1],
            "ec": [600.0, 620.0, 300.0, 310.0],
        }
    )


def test_cell_means_reason():
    cells = cell_means(make_df())
    bad = cells[(cells.run_id == 1) & (cells.x_m == 0.0)].iloc[0]
    assert bad["reason"] == "pH·EC"
    assert bad["n"] == 2
    ok = cells[(cells.run_id == 1) & (cells.x_m == 10.0)].iloc[0]
    assert ok["reason"] == ""


def test_run_summary_counts():
    df = make_df()
    s = run_summary(df, cell_means(df))
    assert list(s["오염 셀 수"]) == [1, 0]
    assert s.iloc[0]["측정일"] == "2026-06-01"
    assert s.iloc[0]["최고 오염 위치"] == "(X 0, Y 0, 수심 0.5 m)"
    assert s.iloc[1]["최고 오염 위치"] == "—"


def test_write_report_sheets(tmp_path):
    from openpyxl import load_workbook

    out = tmp_path / "report.xlsx"
    write_report(make_df(), out)
    wb = load_workbook(out)
    assert wb.sheetnames == ["회차별 요약", "오염 셀 목록", "셀별 전체 데이터"]
    assert wb["오염 셀 목록"].max_row == 2  # 헤더 + 오염 셀 1개
    assert wb["셀별 전체 데이터"].max_row == 4  # 헤더 + 셀 3개
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_export_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'export_report'`

- [ ] **Step 3: export_report.py 구현**

```python
# -*- coding: utf-8 -*-
"""누적 측정 데이터(data/measurements.csv)를 Excel 보고서로 정리한다.

출력: output/report.xlsx — 시트 3개
  1) 회차별 요약    : 회차별 pH·EC 통계, 오염 셀 수, 최고 오염 위치
  2) 오염 셀 목록   : 임계값(pH 6.5~8.5 / EC 500 µS/cm)을 벗어난 셀 상세 (심한 순)
  3) 셀별 전체 데이터: 회차 x 격자 셀별 평균값 전체
오염 셀 행은 빨간 배경으로 강조한다.
"""

from pathlib import Path

import pandas as pd
from openpyxl.styles import PatternFill

from thresholds import exceedance, pollution_reason

DATA_PATH = Path(__file__).parent / "data" / "measurements.csv"
OUT_PATH = Path(__file__).parent / "output" / "report.xlsx"
RED_FILL = PatternFill("solid", start_color="FFF4CCCC")

COL_KR = {
    "run_id": "탐사 회차", "x_m": "X (m)", "y_m": "Y (m)", "depth_m": "수심 (m)",
    "ph_mean": "평균 pH", "ec_mean": "평균 EC (µS/cm)", "n": "측정 횟수", "reason": "판정 사유",
}


def cell_means(df):
    """회차 x (x, y, 수심) 셀별 평균 pH·EC, 측정 수, 오염 판정."""
    g = (
        df.groupby(["run_id", "x_m", "y_m", "depth_m"])
        .agg(ph_mean=("ph", "mean"), ec_mean=("ec", "mean"), n=("ph", "count"))
        .reset_index()
    )
    g["ph_mean"] = g["ph_mean"].round(2)
    g["ec_mean"] = g["ec_mean"].round(0)
    g["reason"] = [pollution_reason(p, e) for p, e in zip(g["ph_mean"], g["ec_mean"])]
    g["severity"] = [
        max(exceedance("ph", p), exceedance("ec", e))
        for p, e in zip(g["ph_mean"], g["ec_mean"])
    ]
    return g


def run_summary(df, cells):
    """회차별 요약 통계 표."""
    rows = []
    for rid, part in df.groupby("run_id"):
        c = cells[cells["run_id"] == rid]
        bad = c[c["reason"] != ""]
        worst = "—"
        if len(bad):
            w = bad.loc[bad["severity"].idxmax()]
            worst = f"(X {w.x_m:.0f}, Y {w.y_m:.0f}, 수심 {w.depth_m} m)"
        rows.append(
            {
                "탐사 회차": int(rid),
                "측정일": str(part["timestamp"].iloc[0])[:10],
                "측정 수": len(part),
                "pH 평균": round(part["ph"].mean(), 2),
                "pH 최소": part["ph"].min(),
                "pH 최대": part["ph"].max(),
                "EC 평균": round(part["ec"].mean(), 0),
                "EC 최소": part["ec"].min(),
                "EC 최대": part["ec"].max(),
                "오염 셀 수": len(bad),
                "최고 오염 위치": worst,
            }
        )
    return pd.DataFrame(rows)


def _fill_red(ws, df, all_rows):
    """오염 행(또는 전체 행)을 빨간 배경으로 강조. 헤더는 1행."""
    for i, (_, row) in enumerate(df.iterrows(), start=2):
        if all_rows or row["판정 사유"] != "":
            for cell in ws[i]:
                cell.fill = RED_FILL


def write_report(df, out_path=OUT_PATH):
    cells = cell_means(df)
    summary = run_summary(df, cells)
    hotspots = (
        cells[cells["reason"] != ""]
        .sort_values("severity", ascending=False)
        .rename(columns=COL_KR)[list(COL_KR.values())]
    )
    detail = cells.rename(columns=COL_KR)[list(COL_KR.values())]
    out_path = Path(out_path)
    out_path.parent.mkdir(exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
        summary.to_excel(xw, sheet_name="회차별 요약", index=False)
        hotspots.to_excel(xw, sheet_name="오염 셀 목록", index=False)
        detail.to_excel(xw, sheet_name="셀별 전체 데이터", index=False)
        _fill_red(xw.book["오염 셀 목록"], hotspots, all_rows=True)
        _fill_red(xw.book["셀별 전체 데이터"], detail, all_rows=False)
    return summary


def main():
    if not DATA_PATH.exists():
        raise SystemExit("data/measurements.csv 가 없습니다. 먼저 generate_data.py 를 실행하세요.")
    df = pd.read_csv(DATA_PATH)
    summary = write_report(df)
    print(f"저장 완료: {OUT_PATH}")
    print(summary.to_string(index=False))
    print(f"\n총 오염 셀 {int(summary['오염 셀 수'].sum())}개 (회차 {len(summary)}회)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_export_report.py -v`
Expected: 3개 전부 PASS

- [ ] **Step 5: 실제 데이터로 실행**

Run: `python export_report.py`
Expected: `output/report.xlsx` 생성, 콘솔에 회차 1~8 요약 표와 오염 셀 수 출력 (매 회차 오염 셀 > 0).

- [ ] **Step 6: 커밋**

```powershell
git add export_report.py tests/test_export_report.py && git commit -m @'
feat: Excel 수치 요약 보고서 생성 스크립트 (시트 3개, 오염 행 강조)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 11: /report 스킬 + 문서 갱신

**Files:**
- Create: `.claude/skills/report/SKILL.md`
- Modify: `.claude/skills/heatmap/SKILL.md`
- Modify: `README.md`

- [ ] **Step 1: report 스킬 작성**

`.claude/skills/report/SKILL.md`:

```markdown
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
```

- [ ] **Step 2: heatmap 스킬 갱신**

`.claude/skills/heatmap/SKILL.md`의 3~5번 항목과 참고 부분을 새 산출물에 맞게 교체:

3번 항목을:

```markdown
3. 출력물이 생성됐는지 확인한다:
   - `output/heatmap_3d.html` — 인터랙티브 (탐사 회차·센서 드롭다운, 회전·확대·호버)
   - `output/heatmap_3d_ph.png`, `output/heatmap_3d_ec.png` — 보고서용 정적 이미지
```

4번 항목의 PNG 확인 대상을 `heatmap_3d_ph.png`와 `heatmap_3d_ec.png` 두 장으로,
확인 포인트에 "빨간 다이아몬드(오염 셀)·범례"를 추가.

5번 항목을 "셀 수·pH/EC 범위·오염 셀 유무를 요약해 보고한다."로 교체.

참고의 컬럼 형식 줄을:

```markdown
- 실측 데이터가 생기면 같은 컬럼 형식으로 `data/measurements.csv`만 교체하면 된다
  (컬럼: run_id, timestamp, x_m, y_m, depth_m, ph, ec).
```

- [ ] **Step 3: README 갱신**

`README.md` 수정 사항:

1. 대시보드 표시 항목 표의 "현재 측정 깊이" 행을:
   `| 현재 측정 깊이 | 수치 + 수심 게이지 (0.5 / 1.0 / 1.5 m — 수심당 1분, 지점당 3분) |`
2. 같은 표의 "실시간 3D 히트맵" 행 끝에 추가:
   ` 탐사 회차(실시간/전체 누적/회차별) 선택, 임계값 초과 오염 셀은 빨간색 표시, Excel 내보내기 버튼 제공` (기존 문구 뒤에 이어 붙임)
3. 결과물 표를:

```markdown
| 파일 | 용도 |
|---|---|
| `output/heatmap_3d.html` | 인터랙티브 3D 히트맵 — 탐사 회차·센서 드롭다운, 마우스로 회전·확대, 셀에 올리면 위치·수심·평균값·누적 측정 횟수 표시 |
| `output/heatmap_3d_ph.png`, `output/heatmap_3d_ec.png` | 정적 3D 히트맵 (전체 누적, 센서별) — 보고서·발표 자료용 |
| `output/report.xlsx` | 수치 요약 보고서 (`python export_report.py`) — 회차별 요약 / 오염 셀 목록 / 셀별 전체 데이터 |
```

4. 데이터 형식 표의 `turbidity_ntu` 행을:

```markdown
| `ph` | pH (6.5~8.5 벗어나면 오염) |
| `ec` | EC 전기전도도 (µS/cm, 500 초과 시 오염) |
```

5. 시각화 설계 절 마지막에 추가:

```markdown
- 오염 판정 임계값(pH 6.5~8.5 / EC 500 µS/cm)은 `thresholds.py` 한 곳에서 관리 —
  임계값을 넘는 셀은 빨간 다이아몬드로 표시
```

6. "탁도" 언급이 남아 있으면 pH·EC 문맥으로 정리
   (센서 확장 예시 코드 블록의 "DO, 탁도 등" 문구는 유지해도 됨 — 확장 가능 센서 예시이므로).

- [ ] **Step 4: 커밋**

```powershell
git add .claude/skills README.md && git commit -m @'
docs: report 스킬 추가, 히트맵 스킬·README를 pH·EC 체계로 갱신

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
'@
```

---

### Task 12: 최종 통합 검증

**Files:** 없음 (검증만)

- [ ] **Step 1: 전체 테스트**

Run: `python -m pytest tests/ -v`
Expected: 전부 PASS

- [ ] **Step 2: 산출물 파이프라인 재실행**

```powershell
python generate_data.py && python visualize_heatmap.py && python export_report.py
```

Expected: 오류 없이 CSV·HTML·PNG 2장·xlsx 생성.

- [ ] **Step 3: 대시보드 종합 확인 (Playwright)**

서버 재시작 후 `http://localhost:8000`:

1. 탐사 회차 "전체 누적" 선택 → 막대 뷰: 오염원 부근 빨간 막대·급한 경사 확인 (스크린샷).
2. 셀 뷰 전환 → 빨간 다이아몬드 확인.
3. 요약 줄 "⚠ 오염 셀 N개 …" 확인.
4. `Invoke-WebRequest "http://localhost:8000/api/export?run=all" -OutFile ...` → xlsx 다운로드 확인.
5. "실시간" 복귀 → 시뮬레이션 진행에 따라 셀 수 증가 확인.

- [ ] **Step 4: superpowers:verification-before-completion 체크 후 완료 보고**

검증 결과(테스트 수, 스크린샷 확인 내용, 산출물 목록)를 정리해 보고한다.
