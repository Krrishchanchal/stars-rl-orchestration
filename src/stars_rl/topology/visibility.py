"""Elevation masks and fixed candidate ISLs; never add links for feasibility."""
import math
from stars_rl.models import ISLLink
from .geometry import distance,elevation,earth_clear


def visible(surface,satellite,orbit):
    return elevation(surface,satellite)+orbit.angular_roundoff_radians>=math.radians(orbit.elevation_mask_degrees)


def candidate_pairs(orbit,satellite_ids):
    n=orbit.satellites_per_plane;pairs=set()
    for p in range(orbit.planes):
        for j in range(n):
            current=satellite_ids[p*n+j]
            pairs.add(tuple(sorted((current,satellite_ids[p*n+(j+1)%n]))))
            if p+1<orbit.planes:pairs.add(tuple(sorted((current,satellite_ids[(p+1)*n+j]))))
    return tuple(sorted(pairs))


def isl_links(orbit,satellite_ids,position):
    return tuple(ISLLink(a,b,distance(position[a],position[b])) for a,b in candidate_pairs(orbit,satellite_ids)
                 if earth_clear(position[a],position[b],orbit.earth_radius_m))
