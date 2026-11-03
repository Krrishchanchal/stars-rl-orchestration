"""Independent circular/rotational geometry, limb and mask oracles."""
import cmath
import math
import pytest

from stars_rl.models import PhysicalOrbit
from stars_rl.topology.geometry import surface_ecef,elevation,earth_clear,distance
from stars_rl.topology.orbits import period,position_eci,eci_to_ecef
from stars_rl.topology.visibility import visible,candidate_pairs


def test_circular_period_radius_and_quarter_orbit():
    o=PhysicalOrbit();r=6871000.;mu=3.986004418e14
    expected=2*math.pi*r/math.sqrt(mu/r)
    assert period(r,mu)==pytest.approx(expected,rel=1e-15)
    assert position_eci(o,0,0,0)==(6871000,0,0)
    x,y,z=position_eci(o,0,0,expected/4)
    assert x==pytest.approx(0,abs=1e-8)
    assert y==pytest.approx(r*math.cos(math.radians(88)),abs=1e-8)
    assert z==pytest.approx(r*math.sin(math.radians(88)),abs=1e-8)
    assert position_eci(o,0,0,expected)==pytest.approx((r,0,0),abs=1e-8)


@pytest.mark.parametrize('plane,index,time',[(0,0,0),(1,7,60),(3,14,780)])
def test_coordinate_against_independent_complex_rotation(plane,index,time):
    o=PhysicalOrbit();r=6871000.
    angle=2*math.pi*index/15+2*math.pi*plane/60+math.sqrt(3.986004418e14/r**3)*time
    horizontal=r*complex(math.cos(angle),math.cos(math.radians(88))*math.sin(angle))
    horizontal*=cmath.exp(1j*(math.radians((0,45,90,135)[plane])-7.2921150e-5*time))
    expected=(horizontal.real,horizontal.imag,r*math.sin(math.radians(88))*math.sin(angle))
    actual=eci_to_ecef(position_eci(o,plane,index,time),time)
    assert actual==pytest.approx(expected,rel=0,abs=2e-8)
    assert sum(x*x for x in actual)==pytest.approx(r*r,rel=5e-16)


def test_earth_rotation_sign_and_position_continuity():
    rate=7.2921150e-5
    assert eci_to_ecef((1,0,0),math.pi/(2*rate))==pytest.approx((0,-1,0),abs=1e-15)
    o=PhysicalOrbit();a=position_eci(o,2,5,60);b=position_eci(o,2,5,60.001)
    speed=math.sqrt(3.986004418e14/6871000)
    assert distance(a,b)==pytest.approx(speed*.001,rel=1e-8)


def test_overhead_below_horizon_and_elevation_boundary():
    o=PhysicalOrbit();surface=(6371000,0,0)
    assert surface_ecef(0,0)==surface
    assert math.degrees(elevation(surface,(6871000,0,0)))==90
    assert math.degrees(elevation(surface,(-6871000,0,0)))==-90
    assert visible(surface,(6871000,0,0),o) and not visible(surface,(-6871000,0,0),o)
    theta=math.acos(6371000/6871000*math.cos(math.radians(10)))-math.radians(10)
    for delta,expected in [(-1e-8,True),(0,True),(1e-8,False)]:
        point=(6871000*math.cos(theta+delta),6871000*math.sin(theta+delta),0)
        assert visible(surface,point,o)==expected


def test_isl_earth_occlusion_symmetry_and_tangent():
    r=6871000;earth=6371000;angle=math.acos(earth/r)
    for delta,expected in [(-1e-6,True),(0,True),(1e-6,False)]:
        a=(r*math.cos(angle+delta),r*math.sin(angle+delta),0);b=(a[0],-a[1],0)
        assert earth_clear(a,b)==earth_clear(b,a)==expected
        assert distance(a,b)==distance(b,a)
    assert not earth_clear((r,0,0),(-r,0,0))


def test_candidates_degree_four_with_no_plane_end_wrap():
    o=PhysicalOrbit();ids=tuple(f's{k:02d}' for k in range(60));edges=candidate_pairs(o,ids)
    degree={s:0 for s in ids}
    for a,b in edges:degree[a]+=1;degree[b]+=1
    assert max(degree.values())==4 and degree['s00']==degree['s45']==3
    assert ('s00','s14') in edges and ('s00','s45') not in edges


@pytest.mark.parametrize('kwargs',[{'altitude_m':600000},{'raan_degrees':(0,90,180,270)},{'elevation_mask_degrees':9}])
def test_frozen_geometry_cannot_be_silently_changed(kwargs):
    with pytest.raises(ValueError,match='frozen'):PhysicalOrbit(**kwargs)
