# -*- coding: utf-8 -*-
"""Hi-Flow 실시간 운영 대시보드 서버.

실행:  python dashboard_server.py  →  브라우저에서 http://localhost:8000

구조
- SENSORS: 센서 레지스트리 — DO, 탁도 등 새 센서는 여기에 항목 하나만
  추가하면 대시보드 화면에 카드가 자동으로 생긴다.
- 시뮬레이터 스레드가 드론 운용(이동→안정화→수심별 측정→완료)을 재현하며
  공유 상태(TELEMETRY)를 갱신한다. 실제 드론 연동 시 이 스레드를
  수신 데이터로 TELEMETRY를 갱신하는 코드로 교체하면 화면은 그대로 동작한다.
- GET /api/telemetry : 현재 상태 JSON (프런트엔드가 1초 주기로 폴링)
- GET /api/heatmap?sensor=<id> : 누적 측정값의 (X, Y, 수심) 셀별 평균 —
  측정이 쌓일수록 셀이 채워져 대시보드의 실시간 3D 히트맵이 변화한다.
"""

import json
import math
import random
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PORT = 8000
BASE_LAT, BASE_LON = 37.24560, 127.08590  # 측정 수역 남서쪽 기준점 (예시 좌표)

def plume(x, y, depth):
    """시뮬레이션용 오염 플룸 강도(0~1): 주 오염원(65, 40, 수심 3m) + 보조 오염원(25, 75, 표층).

    센서값에 공간 분포를 만들어 3D 히트맵에서 핫스팟이 보이게 한다.
    """
    p1 = math.exp(-((x - 65) ** 2 + (y - 40) ** 2) / (2 * 18**2) - (depth - 3.0) ** 2 / (2 * 1.2**2))
    p2 = 0.4 * math.exp(-((x - 25) ** 2 + (y - 75) ** 2) / (2 * 12**2) - (depth - 1.5) ** 2 / (2 * 1.0**2))
    return min(p1 + p2, 1.0)


# ── 센서 레지스트리: 새 센서는 여기에 한 줄 추가 ─────────────────────
# read(x, y, depth_m, rng) → 측정값. 실제 연동 시 read 를 하드웨어 읽기 함수로 교체.
SENSORS = [
    {
        "id": "ph", "name": "pH", "unit": "", "decimals": 2,
        "read": lambda x, y, d, rng: 7.10 - 0.04 * d - 1.1 * plume(x, y, d) + rng.gauss(0, 0.03),
    },
    {
        "id": "ec", "name": "EC 전기전도도", "unit": "µS/cm", "decimals": 0,
        "read": lambda x, y, d, rng: 320 + 6 * d + 220 * plume(x, y, d) + rng.gauss(0, 4),
    },
    # 향후 확장 예시 — 주석만 해제하면 화면에 카드와 히트맵 항목이 자동 추가된다:
    # {
    #     "id": "do", "name": "DO 용존산소", "unit": "mg/L", "decimals": 2,
    #     "read": lambda x, y, d, rng: 8.5 - 0.5 * d - 3.0 * plume(x, y, d) + rng.gauss(0, 0.1),
    # },
    # {
    #     "id": "turbidity", "name": "탁도", "unit": "NTU", "decimals": 1,
    #     "read": lambda x, y, d, rng: 2.0 + 0.3 * d + 38 * plume(x, y, d) + rng.gauss(0, 0.3),
    # },
]

# ── 측정 미션 설정 (generate_data.py 와 동일한 격자) ──────────────────
AREA_SIZE = 100.0
GRID_STEP = 10.0
DEPTH_STEP = 0.5
MAX_DEPTH = 5.0
MOVE_SPEED = 3.0      # m/s (데모용 — 히트맵이 채워지는 걸 빠르게 보기 위해 실제보다 빠름)
TICK = 0.5            # 시뮬레이션 주기 (s)

STATE_LABELS = {
    "moving": "이동 중",
    "stabilizing": "정지·안정화 중",
    "measuring": "측정 중",
    "retrieving": "센서 회수 중",
    "done": "지점 측정 완료",
}

TELEMETRY = {}
HEATMAP = {}   # (x, y, depth) → {sensor_id: [값 합계, 측정 횟수]} — 누적 집계
LOCK = threading.Lock()


def grid_path():
    """서펜타인(지그재그) 순서의 측정 지점 목록."""
    coords = [i * GRID_STEP for i in range(int(AREA_SIZE / GRID_STEP) + 1)]
    points = []
    for i, x in enumerate(coords):
        ys = coords if i % 2 == 0 else list(reversed(coords))
        points.extend((x, y) for y in ys)
    return points


def to_gps(x, y):
    lat = BASE_LAT + y / 111320.0
    lon = BASE_LON + x / (111320.0 * math.cos(math.radians(BASE_LAT)))
    return round(lat, 6), round(lon, 6)


def simulator():
    rng = random.Random(7)
    points = grid_path()
    x, y = points[0]
    point_idx = 0
    completed = 0
    state = "moving"
    state_until = 0.0     # 현재 상태가 끝나는 시각 (안정화 등 시간 기반 상태용)
    depth = 0.0
    battery = 100.0
    last_sample_at = None
    started_at = datetime.now()
    disconnected_until = {s["id"]: 0.0 for s in SENSORS}  # 센서별 통신 두절 종료 시각
    values = {s["id"]: None for s in SENSORS}

    while True:
        now = time.time()
        target = points[point_idx]

        if state == "moving":
            dx, dy = target[0] - x, target[1] - y
            dist = math.hypot(dx, dy)
            step = MOVE_SPEED * TICK
            if dist <= step:
                x, y = target
                state, state_until = "stabilizing", now + 3.0
            else:
                x += dx / dist * step
                y += dy / dist * step
            battery -= 0.010
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
        elif state == "retrieving":
            depth = max(depth - DEPTH_STEP * 2, 0.0)
            if depth <= 0:
                state, state_until = "done", now + 2.0
                completed += 1
            battery -= 0.004
        elif state == "done":
            if now >= state_until:
                point_idx = (point_idx + 1) % len(points)
                if point_idx == 0:
                    completed = 0  # 전체 순회 완료 → 다음 회차 시작
                state = "moving"
            battery -= 0.002

        # 드물게 센서 통신 두절 시뮬레이션 (5~12초)
        for s in SENSORS:
            if now >= disconnected_until[s["id"]] and rng.random() < 0.004:
                disconnected_until[s["id"]] = now + rng.uniform(5, 12)

        battery = max(battery, 0.0)
        lat, lon = to_gps(x, y)
        with LOCK:
            TELEMETRY.clear()
            TELEMETRY.update(
                {
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "platform_status": {"id": state, "label": STATE_LABELS[state]},
                    "gps": {"lat": lat, "lon": lon, "x_m": round(x, 1), "y_m": round(y, 1)},
                    "target": {"x_m": target[0], "y_m": target[1]},
                    "area_size_m": AREA_SIZE,
                    "depth_m": round(depth, 1),
                    "max_depth_m": MAX_DEPTH,
                    "battery_pct": round(battery, 1),
                    "measurement_time": {
                        "last_sample": last_sample_at.isoformat(timespec="seconds") if last_sample_at else None,
                        "mission_started": started_at.isoformat(timespec="seconds"),
                    },
                    "mission": {
                        "point_index": point_idx + 1,
                        "total_points": len(points),
                        "completed_points": completed,
                        "point_done": state == "done",
                    },
                    "sensors": [
                        {
                            "id": s["id"],
                            "name": s["name"],
                            "unit": s["unit"],
                            "connected": now >= disconnected_until[s["id"]],
                            "value": values[s["id"]] if now >= disconnected_until[s["id"]] else None,
                        }
                        for s in SENSORS
                    ],
                }
            )
        time.sleep(TICK)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = (Path(__file__).parent / "dashboard.html").read_bytes()
            self._send(200, "text/html; charset=utf-8", body)
        elif self.path == "/api/telemetry":
            with LOCK:
                body = json.dumps(TELEMETRY, ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
        elif self.path.startswith("/api/heatmap"):
            query = parse_qs(urlparse(self.path).query)
            sensor_id = query.get("sensor", [SENSORS[0]["id"]])[0]
            meta = next((s for s in SENSORS if s["id"] == sensor_id), None)
            if meta is None:
                self._send(404, "text/plain; charset=utf-8", b"unknown sensor")
                return
            with LOCK:
                cells = [
                    [x, y, d, round(acc[sensor_id][0] / acc[sensor_id][1], meta["decimals"]), acc[sensor_id][1]]
                    for (x, y, d), acc in HEATMAP.items()
                    if sensor_id in acc
                ]
            body = json.dumps(
                {"sensor": {"id": sensor_id, "name": meta["name"], "unit": meta["unit"]}, "cells": cells},
                ensure_ascii=False,
            ).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
        else:
            self._send(404, "text/plain; charset=utf-8", b"Not Found")

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # 콘솔 로그 억제


def main():
    threading.Thread(target=simulator, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Hi-Flow 대시보드 실행 중: http://localhost:{PORT}  (종료: Ctrl+C)")
    server.serve_forever()


if __name__ == "__main__":
    main()
