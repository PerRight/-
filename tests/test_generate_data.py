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
