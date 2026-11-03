"""Spherical geometry in metres/radians, independent of model decisions."""
import math


def finite(value):
    if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('finite numeric coordinate required')
    return value


def norm(v):return math.sqrt(math.fsum(finite(x)**2 for x in v))
def dot(a,b):return math.fsum(x*y for x,y in zip(a,b))
def distance(a,b):return norm(tuple(x-y for x,y in zip(a,b)))


def surface_ecef(latitude_degrees,longitude_degrees,radius_m=6371000):
    lat,lon=map(math.radians,(finite(latitude_degrees),finite(longitude_degrees)))
    if not -math.pi/2<=lat<=math.pi/2 or not -math.pi<=lon<=math.pi or finite(radius_m)<=0:raise ValueError('invalid surface position')
    return (radius_m*math.cos(lat)*math.cos(lon),radius_m*math.cos(lat)*math.sin(lon),radius_m*math.sin(lat))


def central_angle(a,b):
    # atan2 is stable for the small separation used by layout rejection.
    cross=(a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    if norm(a)==0 or norm(b)==0:raise ValueError('nonzero position required')
    return math.atan2(norm(cross),dot(a,b))


def elevation(surface,satellite):
    ray=tuple(y-x for x,y in zip(surface,satellite));length=norm(ray);radius=norm(surface)
    if length==0 or radius==0:raise ValueError('undefined line of sight')
    return math.asin(max(-1,min(1,dot(surface,ray)/(radius*length))))


def earth_clear(a,b,radius_m=6371000):
    delta=tuple(y-x for x,y in zip(a,b));length2=dot(delta,delta)
    if finite(radius_m)<=0 or length2==0:return False
    fraction=max(0,min(1,-dot(a,delta)/length2))
    closest=tuple(x+fraction*d for x,d in zip(a,delta))
    # Tangency is retained; this is numerical roundoff, not a visibility expansion.
    return norm(closest)>=radius_m-16*math.ulp(radius_m)
