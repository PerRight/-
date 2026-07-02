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
