"""Independent direct-coordinate physical input checks; no generator imports."""
import math


def verify_window(s,w):
    o=s.orbit;radius=o.earth_radius_m+o.altitude_m;time=w.window_index*s.window_seconds
    speed=math.sqrt(o.gravitational_parameter_m3_s2/radius**3)
    xyz={}
    # Combine RAAN/Earth rotation directly, rather than generator matrix steps.
    for index,sat in enumerate(sorted(n.id for n in s.satellites)):
        p,j=divmod(index,o.satellites_per_plane)
        u=2*math.pi*j/o.satellites_per_plane+2*math.pi*o.phasing_factor*p/(o.planes*o.satellites_per_plane)+speed*time
        a=math.radians(o.raan_degrees[p])-o.rotation_rad_s*time-o.greenwich_angle_at_epoch_rad
        ci=math.cos(math.radians(o.inclination_degrees));si=math.sin(math.radians(o.inclination_degrees))
        xyz[sat]=(radius*(math.cos(a)*math.cos(u)-math.sin(a)*math.sin(u)*ci),
                  radius*(math.sin(a)*math.cos(u)+math.cos(a)*math.sin(u)*ci),radius*math.sin(u)*si)
    def surface(coord):
        a,b=math.radians(coord.latitude_degrees),math.radians(coord.longitude_degrees)
        return (o.earth_radius_m*math.cos(a)*math.cos(b),o.earth_radius_m*math.cos(a)*math.sin(b),o.earth_radius_m*math.sin(a))
    def length(a,b):return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))
    def allowed(a,b):
        d=length(a,b);ratio=sum(x*(y-x) for x,y in zip(a,b))/(o.earth_radius_m*d)
        angle=math.asin(max(-1,min(1,ratio)))
        return angle+o.angular_roundoff_radians>=math.radians(o.elevation_mask_degrees)
    bound=128*math.ulp(radius)  # coordinate arithmetic envelope in metres
    for items,matrix,transpose in ((sorted(s.users,key=lambda x:x.id),w.access_distances_m,False),
                                    (sorted(s.ground_stations,key=lambda x:x.id),w.ground_distances_m,True)):
        for i,item in enumerate(items):
            a=surface(item.coordinates)
            for j,sat in enumerate(w.satellite_ids):
                b=xyz[sat];value=matrix[j][i] if transpose else matrix[i][j]
                if (value is not None)!=allowed(a,b):raise ValueError('physical visibility differs from source geometry')
                if value is not None and abs(value-length(a,b))>bound:raise ValueError('physical slant distance differs from source geometry')
    expected={}
    for a,sa in enumerate(w.satellite_ids):
        p,j=divmod(a,o.satellites_per_plane)
        for b in range(a+1,len(w.satellite_ids)):
            q,k=divmod(b,o.satellites_per_plane)
            if not ((p==q and (j-k)%o.satellites_per_plane in (1,o.satellites_per_plane-1)) or (q==p+1 and j==k)):continue
            sb=w.satellite_ids[b];first,second=xyz[sa],xyz[sb]
            # Equal-radius chord closest distance via the midpoint, independent
            # of the generator's projected segment calculation.
            midpoint=math.sqrt(sum(((x+y)/2)**2 for x,y in zip(first,second)))
            if midpoint>=o.earth_radius_m-16*math.ulp(o.earth_radius_m):expected[(sa,sb)]=length(first,second)
    actual={tuple(sorted((e.satellite_a_id,e.satellite_b_id))):e.distance_m for e in w.isl_links}
    if actual.keys()!=expected.keys() or any(abs(actual[k]-expected[k])>bound for k in actual):raise ValueError('physical ISLs differ from source geometry/edge policy')
    return bound
