"""Circular two-body Walker-star-style snapshots at a synthetic ECI/ECEF epoch."""
import math
from .geometry import finite


def period(radius_m,mu_m3_s2):
    if finite(radius_m)<=0 or finite(mu_m3_s2)<=0:raise ValueError('positive radius/mu required')
    return 2*math.pi*math.sqrt(radius_m**3/mu_m3_s2)


def position_eci(orbit,plane,index,seconds):
    if type(plane) is not int or not 0<=plane<orbit.planes or type(index) is not int or not 0<=index<orbit.satellites_per_plane:raise ValueError('invalid orbital index')
    finite(seconds)
    radius=orbit.earth_radius_m+orbit.altitude_m
    angle=2*math.pi*index/orbit.satellites_per_plane+2*math.pi*orbit.phasing_factor*plane/(orbit.planes*orbit.satellites_per_plane)
    angle+=2*math.pi*seconds/period(radius,orbit.gravitational_parameter_m3_s2)
    inclination=math.radians(orbit.inclination_degrees);raan=math.radians(orbit.raan_degrees[plane])
    x=radius*math.cos(angle);y=radius*math.sin(angle)*math.cos(inclination);z=radius*math.sin(angle)*math.sin(inclination)
    return (x*math.cos(raan)-y*math.sin(raan),x*math.sin(raan)+y*math.cos(raan),z)


def eci_to_ecef(position,seconds,rotation_rad_s=7.2921150e-5,epoch_angle=0):
    angle=finite(rotation_rad_s)*finite(seconds)+finite(epoch_angle)
    x,y,z=position
    return (math.cos(angle)*x+math.sin(angle)*y,-math.sin(angle)*x+math.cos(angle)*y,z)


def positions(orbit,seconds,satellite_ids):
    if len(satellite_ids)!=orbit.planes*orbit.satellites_per_plane:raise ValueError('satellite count differs from orbit')
    return {s:eci_to_ecef(position_eci(orbit,k//orbit.satellites_per_plane,k%orbit.satellites_per_plane,seconds),seconds,
                          orbit.rotation_rad_s,orbit.greenwich_angle_at_epoch_rad) for k,s in enumerate(satellite_ids)}
