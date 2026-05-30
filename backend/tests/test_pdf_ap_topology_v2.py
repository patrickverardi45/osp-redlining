"""GAC Target #2 — tail->backbone route topology V2 (shadow-only) tests.

Locks the pure connectivity contract:
- trace_backbone_via_topology returns the SINGLE connected backbone; abstains on
  >=2 (never a nearest-distance tie-break) and on connected-only-to-non-backbone;
- it follows CONNECTIVITY, not nearest-distance (returns the connected backbone
  even when a non-connected backbone is geometrically nearer);
- build_route_adjacency is order-independent (shuffled input => identical graph);
- emit_shadow_for_group is additive + flag-OFF byte-identical.
No placement / scoring / geometry is touched.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

from backend.app.core import pdf_ap_route_resolver as R

# ~1 ft in latitude degrees at lat 30 (lon held constant in fixtures).
FT = 1.0 / 364567.0
T_LAT, T_LON = 30.0, -96.0           # terminal
J = (T_LAT + 300 * FT, T_LON)        # junction, 300 ft north of terminal
B_FAR = (T_LAT + 600 * FT, T_LON)
D_NEAR = (T_LAT + 50 * FT, T_LON)    # 50 ft from terminal (NEARER than J)


def route(rid, folder, coords):
    return {"route_id": rid, "route_name": rid, "source_folder": folder, "coords": coords}


# Stub A (terminal tail): terminal -> J ; Backbone B: J -> B_FAR (shares J).
A = route("A", "Connections / Terminal Tail", [[T_LAT, T_LON], list(J)])
B = route("B", "Connections / underground cable", [list(J), list(B_FAR)])
# Backbone C also shares J (creates a 2-backbone ambiguity at hop 1).
C = route("C", "Connections / underground cable", [list(J), [J[0], J[1] - 0.001]])
# Backbone D: a vertex 50 ft from the terminal (NEARER than B's J) but shares no
# vertex with A/B -> not connected.
D = route("D", "Connections / underground cable", [list(D_NEAR), [D_NEAR[0], D_NEAR[1] - 0.001]])
# House-drop stub touching the terminal, connected to another house drop, no bb.
HA = route("HA", "Connections / House Drop", [[T_LAT, T_LON], list(J)])
HB = route("HB", "Connections / House Drop", [list(J), list(B_FAR)])


class TestTraceBackbone(unittest.TestCase):

    def setUp(self):
        R._ADJ_CACHE.clear()

    def test_single_connected_backbone(self):
        res = R.trace_backbone_via_topology(T_LAT, T_LON, [A, B])
        self.assertEqual(res["backbone_route_id"], "B")
        self.assertEqual(res["reason"], "deterministic_single_backbone")
        self.assertEqual(res["hops"], 1)

    def test_two_connected_backbones_abstain(self):
        res = R.trace_backbone_via_topology(T_LAT, T_LON, [A, B, C])
        self.assertIsNone(res["backbone_route_id"])
        self.assertTrue(res["reason"].startswith("ambiguous_multi_backbone"))
        self.assertIn("B", res["reason"])
        self.assertIn("C", res["reason"])

    def test_connectivity_beats_nearest_distance(self):
        # D's vertex is 50 ft from the terminal (nearer than B's J at 300 ft), but
        # D shares no vertex with the stub -> trace must return the CONNECTED B.
        res = R.trace_backbone_via_topology(T_LAT, T_LON, [A, B, D])
        self.assertEqual(res["backbone_route_id"], "B")

    def test_only_house_drops_abstain(self):
        res = R.trace_backbone_via_topology(T_LAT, T_LON, [HA, HB])
        self.assertIsNone(res["backbone_route_id"])
        self.assertEqual(res["reason"], "no_backbone_reachable")

    def test_no_stub_at_terminal(self):
        # terminal far from every stub vertex.
        res = R.trace_backbone_via_topology(31.0, -97.0, [A, B])
        self.assertIsNone(res["backbone_route_id"])
        self.assertEqual(res["reason"], "no_stub_at_terminal")


class TestAdjacencyOrderIndependent(unittest.TestCase):

    def test_shuffle_and_reverse_coords_identical(self):
        R._ADJ_CACHE.clear()
        adj1 = {k: set(v) for k, v in R.build_route_adjacency([A, B, C, D]).items()}
        R._ADJ_CACHE.clear()
        # shuffle route order + reverse each route's coords
        shuffled = [
            route("D", D["source_folder"], list(reversed(D["coords"]))),
            route("B", B["source_folder"], list(reversed(B["coords"]))),
            route("A", A["source_folder"], list(reversed(A["coords"]))),
            route("C", C["source_folder"], list(reversed(C["coords"]))),
        ]
        adj2 = {k: set(v) for k, v in R.build_route_adjacency(shuffled).items()}
        self.assertEqual(adj1, adj2)
        # A connects to B and C (shared J); D connects to nothing.
        self.assertEqual(adj1["A"], {"B", "C"})
        self.assertEqual(adj1["D"], set())


class TestEmitShadowTopologyFlagOff(unittest.TestCase):
    """On the pdf_plan_data_unavailable path (empty pdf_paths) the topology attach
    is not reached, so flag OFF and ON are both byte-identical (no key)."""

    def _emit(self, **over):
        base = dict(source_file="bore_log67.xlsx", print_tokens=["19", "20"], notes_text="",
                    pdf_paths=[], point_features=[], route_catalog=[A, B],
                    hardcoded_allowed_route_ids=[])
        base.update(over)
        return R.emit_shadow_for_group(**base)

    def test_off_default_no_topology_key(self):
        off = self._emit(topology_v2=False)
        self.assertNotIn("backbone_via_topology", off)
        self.assertEqual(off, self._emit())  # param absent == False

    def test_on_without_pdfs_still_no_topology_key(self):
        self.assertNotIn("backbone_via_topology", self._emit(topology_v2=True))


if __name__ == "__main__":
    unittest.main()
