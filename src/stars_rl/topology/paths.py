"""Positive-distance undirected shortest paths, retaining every supplied node."""
from dataclasses import dataclass
import heapq
import math
import re

from stars_rl.models import ISLLink, Record, check_type


@dataclass(frozen=True, slots=True)
class Path(Record):
    nodes: tuple[str, ...]
    distance_m: float

    def __post_init__(self):
        Record.__post_init__(self)
        if not self.nodes or len(set(self.nodes)) != len(self.nodes):
            raise ValueError("path: require nonempty simple node sequence")
        if self.distance_m < 0 or (self.distance_m == 0) != (len(self.nodes) == 1):
            raise ValueError("path: only identity paths have zero distance")


@dataclass(frozen=True, slots=True)
class PathTable(Record):
    node_ids: tuple[str, ...]
    entries: tuple[Path | None, ...]  # row-major, including unavailable pairs

    def __post_init__(self):
        Record.__post_init__(self)
        if not self.node_ids or tuple(sorted(set(self.node_ids))) != self.node_ids:
            raise ValueError("path table: require sorted unique node IDs")
        if len(self.entries) != len(self.node_ids)**2:
            raise ValueError("path table: invalid dimensions")
        for i,a in enumerate(self.node_ids):
            for j,b in enumerate(self.node_ids):
                path=self.entries[i*len(self.node_ids)+j]
                if a==b and path != Path((a,),0):
                    raise ValueError("path table: missing identity path")
                if path is not None:
                    if path.nodes[0] != a or path.nodes[-1] != b or not set(path.nodes) <= set(self.node_ids):
                        raise ValueError("path table: unknown or inconsistent endpoints")
                    reverse=self.entries[j*len(self.node_ids)+i]
                    if reverse != Path(path.nodes[::-1],path.distance_m):
                        raise ValueError("path table: undirected symmetry required")

    def get(self, source_id: str, target_id: str) -> Path | None:
        if source_id not in self.node_ids or target_id not in self.node_ids:
            raise ValueError("unknown path endpoint")
        return self.entries[self.node_ids.index(source_id)*len(self.node_ids)+self.node_ids.index(target_id)]


def all_pairs_shortest_paths(node_ids: tuple[str, ...], links: tuple[ISLLink, ...]) -> PathTable:
    """Exact float costs, no tie tolerance. Lexicographic ties use the smaller
    endpoint as origin; the reverse query returns the reverse of that same path.
    Dijkstra uses positive weights; it is a path calculation, not a placement heuristic.
    """
    check_type(node_ids,tuple[str,...],"node_ids")
    check_type(links,tuple[ISLLink,...],"links")
    if not node_ids or len(set(node_ids)) != len(node_ids):
        raise ValueError("graph: require nonempty unique node IDs")
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*",n) for n in node_ids):
        raise ValueError("graph: malformed stable node ID")
    nodes=tuple(sorted(node_ids));adj={n:[] for n in nodes};seen=set()
    for link in links:
        a,b=link.satellite_a_id,link.satellite_b_id
        if a not in adj or b not in adj:
            raise ValueError("graph: unknown edge endpoint")
        key=tuple(sorted((a,b)))
        if key in seen:
            raise ValueError("graph: duplicate undirected edge")
        seen.add(key)
        adj[a].append((b,link.distance_m));adj[b].append((a,link.distance_m))
    entries=[None]*(len(nodes)**2)
    for i,source in enumerate(nodes):
        best={source:(0.0,(source,))};queue=[(0.0,(source,))]
        while queue:
            cost,seq=heapq.heappop(queue);last=seq[-1]
            if best.get(last) != (cost,seq):
                continue
            for other,weight in sorted(adj[last]):
                if other in seq:
                    continue
                distance=cost+weight
                if not math.isfinite(distance):
                    raise ValueError("path cost outside finite float range")
                candidate=(distance,(*seq,other))
                if other not in best or candidate < best[other]:
                    best[other]=candidate;heapq.heappush(queue,candidate)
        for j in range(i,len(nodes)):
            if nodes[j] in best:
                distance,seq=best[nodes[j]]
                entries[i*len(nodes)+j]=Path(seq,distance)
                entries[j*len(nodes)+i]=Path(seq[::-1],distance)
    return PathTable(nodes,tuple(entries))
