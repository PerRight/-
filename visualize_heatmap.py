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

import sys
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
    if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔에서 µ 등 출력 보장
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
