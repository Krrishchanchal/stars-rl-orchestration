"""O-UNITS: expectations derived with powers of ten, not production inverses.

20 dBm gives 10**((20-30)/10)=0.1 W; -30 gives 10**(-6) W.
40 dBi gives 10**4; -10 gives 10**(-1). ms -> s multiplies by
10**(-3), s -> ms by 10**3; mega -> base multiplies by 10**6,
base -> mega by 10**(-6); km -> m by 10**3, m -> km by 10**(-3).
"""
import pytest

from stars_rl.physics import units


@pytest.mark.parametrize("name,value,expected", [
    ("dbm_to_watts",20,.1), ("dbm_to_watts",0,.001), ("dbm_to_watts",-30,1e-6),
    ("dbi_to_linear",40,10000), ("dbi_to_linear",-10,.1),
    ("milliseconds_to_seconds",35,.035), ("seconds_to_milliseconds",.05,50),
    ("mbps_to_bps",2,2000000), ("bps_to_mbps",20000000,20),
    ("mips_to_ips",100,100000000), ("ips_to_mips",50000000,50),
    ("kilometers_to_meters",500,500000), ("meters_to_kilometers",100000,100),
])
def test_independent_conversions(name,value,expected):
    assert getattr(units,name)(value) == pytest.approx(expected,rel=1e-14)


@pytest.mark.parametrize("value", [float("nan"),float("inf"),-float("inf"),True,"20"])
def test_invalid_numeric_values(value):
    for name in ["dbm_to_watts","dbi_to_linear","milliseconds_to_seconds","seconds_to_milliseconds",
                 "mbps_to_bps","bps_to_mbps","mips_to_ips","ips_to_mips",
                 "kilometers_to_meters","meters_to_kilometers"]:
        with pytest.raises(ValueError): getattr(units,name)(value)


def test_zero_conversions_and_negative_physical_units():
    for name in ["milliseconds_to_seconds","seconds_to_milliseconds","mbps_to_bps","bps_to_mbps",
                 "mips_to_ips","ips_to_mips","kilometers_to_meters","meters_to_kilometers"]:
        assert getattr(units,name)(0) == 0
        with pytest.raises(ValueError): getattr(units,name)(-1)


@pytest.mark.parametrize("value", [1e308,-1e308])
def test_unrepresentable_db_values_are_rejected(value):
    with pytest.raises(ValueError): units.dbm_to_watts(value)
    with pytest.raises(ValueError): units.dbi_to_linear(value)


def test_conversion_overflow_is_not_exported_as_infinity():
    for name in ["mbps_to_bps","mips_to_ips","seconds_to_milliseconds","kilometers_to_meters"]:
        with pytest.raises(ValueError): getattr(units,name)(1e308)
