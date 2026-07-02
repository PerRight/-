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
