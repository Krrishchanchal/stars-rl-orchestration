"""C05 graph answers derived by hand or independent exhaustive simple paths."""
from dataclasses import FrozenInstanceError
from itertools import permutations

import pytest

from stars_rl.models import ISLLink
from stars_rl.topology.paths import all_pairs_shortest_paths


def test_identity_multihop_and_unavailable():
    p=all_pairs_shortest_paths(("c","a","b","isolated"),
        (ISLLink("a","b",3),ISLLink("b","c",4),ISLLink("a","c",10)))
    assert p.node_ids == ("a","b","c","isolated")
    assert p.get("a","a").nodes == ("a",)
    assert p.get("a","a").distance_m == 0
    assert p.get("a","c").nodes == ("a","b","c")
    assert p.get("a","c").distance_m == 7
    assert p.get("c","a").nodes == ("c","b","a")
    assert p.get("a","isolated") is None
    with pytest.raises(ValueError,match="unknown"):
        p.get("missing","a")
    with pytest.raises(FrozenInstanceError):
        p.get("a","c").distance_m=0


def test_ties_are_stable_under_insertion_order_and_direction():
    edges=(ISLLink("a","c",1),ISLLink("c","d",1),ISLLink("a","b",1),ISLLink("b","d",1))
    expected=("a","b","d")
    p=all_pairs_shortest_paths(("d","c","b","a"),edges)
    q=all_pairs_shortest_paths(("a","b","c","d"),tuple(reversed(edges)))
    assert p == q
    assert p.get("a","d").nodes == expected
    assert p.get("d","a").nodes == tuple(reversed(expected))
    # No tolerance may turn a strictly better route into a tie.
    r=all_pairs_shortest_paths(("a","b","c","d"),
        (ISLLink("a","b",1),ISLLink("b","d",1.000000000001),ISLLink("a","c",1),ISLLink("c","d",1)))
    assert r.get("a","d").nodes == ("a","c","d")


def test_against_independent_simple_path_enumeration():
    nodes=("a","b","c","d","x")
    raw=[("a","b",2),("b","c",3),("a","c",8),("c","d",1),("b","d",7)]
    weights={(a,b):w for a,b,w in raw}|{(b,a):w for a,b,w in raw}
    actual=all_pairs_shortest_paths(nodes,tuple(ISLLink(a,b,w) for a,b,w in raw))
    for a in nodes:
        for b in nodes:
            if a==b:
                assert actual.get(a,b).distance_m == 0
                continue
            lo,hi=sorted((a,b));middle=[n for n in nodes if n not in (lo,hi)]
            candidates=[]
            for k in range(len(middle)+1):
                for perm in permutations(middle,k):
                    seq=(lo,*perm,hi)
                    pairs=list(zip(seq,seq[1:]))
                    if all(pair in weights for pair in pairs):
                        candidates.append((sum(weights[pair] for pair in pairs),seq))
            if not candidates:
                assert actual.get(a,b) is None
            else:
                cost,seq=min(candidates)
                assert actual.get(a,b).distance_m == cost
                assert actual.get(a,b).nodes == (seq if a==lo else seq[::-1])


@pytest.mark.parametrize("nodes,links", [
    (("a","a"),()), (("a",),(ISLLink("a","b",1),)),
    (("a","b"),(ISLLink("a","b",1),ISLLink("b","a",1))),
    (("bad id",),()),
])
def test_invalid_graphs(nodes,links):
    with pytest.raises(ValueError): all_pairs_shortest_paths(nodes,links)
