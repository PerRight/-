# -*- coding: utf-8 -*-
"""Hi-Flow 누적 측정 데이터 3D 히트맵 시각화.

data/measurements.csv 의 누적 측정값을 (X, Y, 수심) 격자 셀별로 평균 집계한 뒤
  1) output/heatmap_3d.html — Plotly 인터랙티브 3D 히트맵 (회전·확대·호버 지원)
  2) output/heatmap_3d.png  — matplotlib 정적 3D 히트맵 (보고서용)
두 가지로 출력한다.

색상: 탁도는 크기(magnitude) 데이터이므로 단일 색상(파랑) 순차 램프를 사용한다.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from matplotlib.colors import LinearSegmentedColormap

# ── 색상 정의 (순차 파랑 램프: 밝음 = 낮음 → 어두움 = 높음) ─────────
BLUE_RAMP = [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
    "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b",
]
SURFACE = "#fcfcfb"      # 차트 배경
INK_PRIMARY = "#0b0b0b"  # 제목
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"    # 축 레이블
GRIDLINE = "#e1e0d9"

DATA_PATH = Path(__file__).parent / "data" / "measurements.csv"
OUT_DIR = Path(__file__).parent / "output"


def load_aggregated():
    """누적 측정값을 격자 셀(x, y, 수심)별 평균 탁도와 측정 횟수로 집계한다."""
    df = pd.read_csv(DATA_PATH)
    agg = (
        df.groupby(["x_m", "y_m", "depth_m"])["turbidity_ntu"]
        .agg(mean_ntu="mean", n_samples="count")
        .reset_index()
    )
    agg["mean_ntu"] = agg["mean_ntu"].round(2)
    return agg


def marker_sizes(values, lo=3.0, hi=16.0):
    """탁도가 높은 셀일수록 큰 마커 — 낮은 셀은 작게 물러나 내부 핫스팟이 보이게 한다."""
    v = (values - values.min()) / (values.max() - values.min())
    return lo + v**1.5 * (hi - lo)


def make_plotly(agg):
    colorscale = [[i / (len(BLUE_RAMP) - 1), c] for i, c in enumerate(BLUE_RAMP)]
    fig = go.Figure(
        go.Scatter3d(
            x=agg["x_m"],
            y=agg["y_m"],
            z=agg["depth_m"],
            mode="markers",
            marker=dict(
                size=marker_sizes(agg["mean_ntu"]),
                symbol="square",
                color=agg["mean_ntu"],
                colorscale=colorscale,
                opacity=0.85,
                colorbar=dict(
                    title=dict(text="평균 탁도<br>(NTU)", font=dict(color=INK_SECONDARY, size=13)),
                    tickfont=dict(color=INK_MUTED, size=12),
                    thickness=14,
                    len=0.6,
                ),
            ),
            customdata=agg["n_samples"],
            hovertemplate=(
                "위치 X: %{x:.0f} m<br>"
                "위치 Y: %{y:.0f} m<br>"
                "수심: %{z:.1f} m<br>"
                "평균 탁도: %{marker.color:.2f} NTU<br>"
                "누적 측정 횟수: %{customdata}회"
                "<extra></extra>"
            ),
        )
    )

    axis_style = dict(
        gridcolor=GRIDLINE,
        zerolinecolor=GRIDLINE,
        backgroundcolor=SURFACE,
        title_font=dict(color=INK_SECONDARY, size=13),
        tickfont=dict(color=INK_MUTED, size=11),
    )
    fig.update_layout(
        title=dict(
            text="수질 3D 히트맵 — 누적 측정 데이터<br>"
            "<sup>격자 셀별 평균 탁도 · 마커가 크고 진할수록 오염도 높음 · 드래그로 회전</sup>",
            font=dict(color=INK_PRIMARY, size=18),
            x=0.02,
        ),
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
        margin=dict(l=0, r=0, t=70, b=0),
    )

    out = OUT_DIR / "heatmap_3d.html"
    fig.write_html(out, include_plotlyjs="cdn")
    print(f"저장 완료: {out}")


def make_matplotlib(agg):
    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False
    cmap = LinearSegmentedColormap.from_list("hiflow_blue", BLUE_RAMP)

    fig = plt.figure(figsize=(11, 8), facecolor=SURFACE)
    ax = fig.add_subplot(projection="3d")
    ax.set_facecolor(SURFACE)

    sc = ax.scatter(
        agg["x_m"], agg["y_m"], agg["depth_m"],
        c=agg["mean_ntu"], cmap=cmap,
        s=marker_sizes(agg["mean_ntu"], lo=6, hi=90),
        marker="s", alpha=0.85, linewidths=0,
    )
    ax.invert_zaxis()  # 아래로 갈수록 깊은 수심
    ax.set_xlabel("동서 위치 X (m)", color=INK_SECONDARY)
    ax.set_ylabel("남북 위치 Y (m)", color=INK_SECONDARY)
    ax.set_zlabel("수심 (m)", color=INK_SECONDARY)
    ax.tick_params(colors=INK_MUTED, labelsize=9)
    ax.set_title(
        "수질 3D 히트맵 — 누적 측정 데이터\n격자 셀별 평균 탁도 (마커가 크고 진할수록 오염도 높음)",
        color=INK_PRIMARY, fontsize=13, pad=15,
    )
    cbar = fig.colorbar(sc, ax=ax, shrink=0.55, pad=0.08)
    cbar.set_label("평균 탁도 (NTU)", color=INK_SECONDARY)
    cbar.ax.tick_params(colors=INK_MUTED)

    out = OUT_DIR / "heatmap_3d.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    print(f"저장 완료: {out}")


def main():
    if not DATA_PATH.exists():
        raise SystemExit("data/measurements.csv 가 없습니다. 먼저 generate_data.py 를 실행하세요.")
    OUT_DIR.mkdir(exist_ok=True)
    agg = load_aggregated()
    print(f"집계 완료: 격자 셀 {len(agg):,}개 (셀당 평균 {agg['n_samples'].mean():.0f}회 측정 누적)")
    make_plotly(agg)
    make_matplotlib(agg)


if __name__ == "__main__":
    main()
