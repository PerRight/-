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
