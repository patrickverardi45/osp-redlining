"""GAC Target #5 — backbone corridor CHAIN assembly (shadow-only) tests.

Locks the pure corridor contract of build_backbone_corridor_chain:
- a linear run of EXACT-shared-vertex "underground cable" segments through the
  candidate is returned as a deterministic simple chain (CONNECTIVITY evidence,
  NOT corridor/street identity);
- a degree>=3 fork anywhere in the component abstains (branched_corridor_abstain);
- a cycle abstains (ambiguous_or_cycle);
- max_span gating uses longest_path * 1.10 (chain_too_short when the corridor, even
  at full length, cannot physically hold the bore span — clamp-not-scale);
- a lone backbone vs an isolated-in-a-populated-graph backbone are distinguished
  (single_segment vs no_connected_backbone_chain), and neither is ever mislabelled
  chain_too_short;
- a non-backbone candidate is route_not_backbone;
- the result is ORDER-INDEPENDENT (shuffled + reversed catalog => identical dict);
- emit_backbone_corridor_chain picks the candidate deterministically and
  emit_shadow_for_group is additive + flag-OFF byte-identical.
Lengths are set EXPLICITLY (length_ft) and decoupled from coords; coords only decide
adjacency (exact shared vertex == identical [lat,lon] pair == 0.0 ft). No placement
/ scoring / geometry / STATE is touched.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

from backend.app.core import pdf_ap_route_resolver as R

UG = "Connections / underground cable"   # backbone folder substring -> backbone
HD = "Connections / House Drop"          # non-backbone (excluded from the graph)
TAIL = "Connections / Terminal Tail"     # non-backbone

# Exact shared vertices: REUSING the identical [lat,lon] pair as an endpoint of two
# routes yields exactly 0.0 ft (well within epsilon 2.0). A linear corridor laid
# west->east at lat 30.1500; each junction is the SAME vertex shared by two routes.
V0 = [30.15000, -96.39000]   # west end of route_480
V1 = [30.15000, -96.38900]   # route_480 <-> route_479 junction  (~316 ft east)
VM = [30.15000, -96.38800]   # interior vertex of route_479 (branch taps here)
V2 = [30.15000, -96.38700]   # route_479 <-> route_475 junction
V3 = [30.15000, -96.38500]   # east end of route_475
VB = [30.14900, -96.38900]   # ~365 ft south of V1 — branch-stub far end
# A clearly-DISCONNECTED far cluster (different 2nd-decimal lat AND lon).
W0 = [30.16000, -96.37000]
W1 = [30.16000, -96.36900]
# Cycle vertices (three distinct shared points -> a 3-ring).
P_AB = [30.15000, -96.39000]
P_BC = [30.15000, -96.38800]
P_CA = [30.15000, -96.38600]


def route(rid, folder, coords, length_ft):
    """Catalog route dict in the canonical STATE shape (route_role cosmetic)."""
    return {"route_id": rid, "route_name": rid, "source_folder": folder,
            "route_role": "backbone" if "underground cable" in folder.lower() else "drop",
            "length_ft": float(length_ft), "coords": [list(c) for c in coords]}


# --- the shipped route_480 corridor: 480 -> 479 -> 475, total 3024.0 ft ----------
R480 = route("route_480", UG, [V0, V1], 131.5)
R479 = route("route_479", UG, [V1, V2], 1500.0)
R475 = route("route_475", UG, [V2, V3], 1392.5)
CATALOG_CHAIN = [R480, R479, R475]


class _CacheClearing(unittest.TestCase):
    def setUp(self):
        # build_route_adjacency memoises on (epsilon, sorted-id-set); the helper calls
        # it internally, so a stale cache would silently corrupt order-independence.
        R._ADJ_CACHE.clear()


class TestSimpleChain(_CacheClearing):

    def test_deterministic_simple_chain(self):
        res = R.build_backbone_corridor_chain("route_480", CATALOG_CHAIN)
        self.assertEqual(res["reason"], "deterministic_simple_chain")
        self.assertEqual(set(res["chain_route_ids"]),
                         {"route_480", "route_479", "route_475"})
        self.assertTrue(res["is_simple_path"])
        self.assertEqual(res["branch_node_count"], 0)
        self.assertAlmostEqual(res["total_len_ft"], 3024.0, places=1)
        self.assertAlmostEqual(res["longest_path_len_ft"], 3024.0, places=1)
        # pure linear chain: longest path covers the whole component.
        self.assertEqual(res["total_len_ft"], res["longest_path_len_ft"])
        self.assertEqual(res["candidate_route_id"], "route_480")
        self.assertEqual(res["epsilon_ft"], 2.0)
        self.assertIsNone(res["max_span_ft"])
        self.assertFalse(res["path_truncated"])

    def test_candidate_is_middle_of_chain(self):
        # candidate need not be an endpoint: route_479 (degree 2) yields the same chain.
        res = R.build_backbone_corridor_chain("route_479", CATALOG_CHAIN)
        self.assertEqual(res["reason"], "deterministic_simple_chain")
        self.assertEqual(set(res["chain_route_ids"]),
                         {"route_480", "route_479", "route_475"})
        self.assertAlmostEqual(res["longest_path_len_ft"], 3024.0, places=1)


class TestSpanFit(_CacheClearing):

    def test_fits_with_max_span(self):
        # bore_log43's real file-span outlier 1919 <= 3024 * 1.10 (=3326.4) -> fits.
        res = R.build_backbone_corridor_chain("route_480", CATALOG_CHAIN, max_span_ft=1919.0)
        self.assertEqual(res["reason"], "deterministic_simple_chain")
        self.assertTrue(res["is_simple_path"])
        self.assertEqual(res["max_span_ft"], 1919.0)

    def test_chain_too_short(self):
        # 2-route chain total 990; span 2000 > 990 * 1.10 (=1089) -> too short.
        R1 = route("route_481", UG, [V0, V1], 490.0)
        R2 = route("route_482", UG, [V1, V2], 500.0)
        res = R.build_backbone_corridor_chain("route_481", [R1, R2], max_span_ft=2000.0)
        self.assertEqual(res["reason"], "chain_too_short")
        self.assertAlmostEqual(res["longest_path_len_ft"], 990.0, places=1)
        self.assertEqual(res["max_span_ft"], 2000.0)
        self.assertEqual(res["branch_node_count"], 0)
        # structurally still a linear path, it just cannot hold the span.
        self.assertTrue(res["is_simple_path"])
        self.assertEqual(set(res["chain_route_ids"]), {"route_481", "route_482"})

    def test_span_boundary_just_under_fits(self):
        # longest path 3024; 110% = 3326.4. A span clearly under fits.
        res = R.build_backbone_corridor_chain("route_480", CATALOG_CHAIN, max_span_ft=3320.0)
        self.assertEqual(res["reason"], "deterministic_simple_chain")

    def test_span_boundary_just_over_too_short(self):
        res = R.build_backbone_corridor_chain("route_480", CATALOG_CHAIN, max_span_ft=3330.0)
        self.assertEqual(res["reason"], "chain_too_short")

    def test_too_short_never_fires_for_single_segment(self):
        # An isolated lone backbone with an over-long span is single_segment, NOT
        # chain_too_short (there is no chain to be 'too short').
        only = route("route_480", UG, [V0, V1], 131.5)
        res = R.build_backbone_corridor_chain("route_480", [only], max_span_ft=9999.0)
        self.assertEqual(res["reason"], "single_segment")


class TestAbstainShapes(_CacheClearing):

    def test_branched_corridor_abstain(self):
        # route_479 gets an interior vertex VM; a 4th backbone taps VM only ->
        # degree(route_479)=3, NO cycle (tree). Fork => abstain.
        r479 = route("route_479", UG, [V1, VM, V2], 1500.0)
        r_branch = route("route_900", UG, [VM, VB], 600.0)
        cat = [R480, r479, R475, r_branch]
        res = R.build_backbone_corridor_chain("route_480", cat)
        self.assertEqual(res["reason"], "branched_corridor_abstain")
        self.assertGreaterEqual(res["branch_node_count"], 1)
        self.assertFalse(res["is_simple_path"])

    def test_ambiguous_or_cycle(self):
        # 3-ring A-B-C-A: 3 nodes, 3 edges, every node degree 2 (NOT a branch) -> cycle.
        ra = route("route_A", UG, [P_CA, P_AB], 1000.0)
        rb = route("route_B", UG, [P_AB, P_BC], 1000.0)
        rc = route("route_C", UG, [P_BC, P_CA], 1000.0)
        res = R.build_backbone_corridor_chain("route_A", [ra, rb, rc])
        self.assertEqual(res["reason"], "ambiguous_or_cycle")
        self.assertFalse(res["is_simple_path"])

    def test_single_segment(self):
        only = route("route_480", UG, [V0, V1], 131.5)
        res = R.build_backbone_corridor_chain("route_480", [only])
        self.assertEqual(res["reason"], "single_segment")
        self.assertEqual(res["chain_route_ids"], ["route_480"])
        self.assertAlmostEqual(res["total_len_ft"], 131.5, places=1)
        self.assertEqual(res["branch_node_count"], 0)
        self.assertTrue(res["is_simple_path"])

    def test_no_connected_backbone_chain(self):
        # two backbones that do NOT share a vertex (far clusters) -> isolated candidate.
        cand = route("route_480", UG, [V0, V1], 131.5)
        far = route("route_700", UG, [W0, W1], 800.0)
        res = R.build_backbone_corridor_chain("route_480", [cand, far])
        self.assertEqual(res["reason"], "no_connected_backbone_chain")
        self.assertEqual(res["chain_route_ids"], ["route_480"])
        self.assertEqual(res["branch_node_count"], 0)
        self.assertTrue(res["is_simple_path"])


class TestRouteNotBackbone(_CacheClearing):

    def test_house_drop_candidate(self):
        drop = route("route_905", HD, [V1, [30.15001, -96.38901]], 40.0)
        bb = route("route_479", UG, [V1, V2], 1500.0)
        res = R.build_backbone_corridor_chain("route_905", [drop, bb])
        self.assertEqual(res["reason"], "route_not_backbone")
        self.assertEqual(res["chain_route_ids"], [])
        self.assertEqual(res["branch_node_count"], 0)
        self.assertFalse(res["is_simple_path"])
        self.assertEqual(res["total_len_ft"], 0.0)
        self.assertEqual(res["longest_path_len_ft"], 0.0)
        self.assertEqual(res["candidate_route_id"], "route_905")

    def test_terminal_tail_candidate(self):
        # proves it is the "underground cable" substring check, not a literal folder.
        cat = [route("route_460", TAIL, [V1, V2], 30.0),
               route("route_479", UG, [V2, V3], 1500.0)]
        res = R.build_backbone_corridor_chain("route_460", cat)
        self.assertEqual(res["reason"], "route_not_backbone")

    def test_unknown_candidate(self):
        res = R.build_backbone_corridor_chain("route_999", CATALOG_CHAIN)
        self.assertEqual(res["reason"], "route_not_backbone")

    def test_none_candidate(self):
        res = R.build_backbone_corridor_chain(None, CATALOG_CHAIN)
        self.assertEqual(res["reason"], "route_not_backbone")


class TestOrderIndependence(_CacheClearing):

    def test_shuffle_and_reverse_identical_dict(self):
        base = R.build_backbone_corridor_chain("route_480", CATALOG_CHAIN)
        orders = [
            [R475, R480, R479],
            [R479, R475, R480],
            # reversed list AND reversed coords on every route:
            [route("route_475", UG, list(reversed(R475["coords"])), 1392.5),
             route("route_479", UG, list(reversed(R479["coords"])), 1500.0),
             route("route_480", UG, list(reversed(R480["coords"])), 131.5)],
        ]
        for cat in orders:
            R._ADJ_CACHE.clear()   # force a real recompute per ordering
            got = R.build_backbone_corridor_chain("route_480", cat)
            self.assertEqual(got, base, f"result differs for ordering {[r['route_id'] for r in cat]}")


class TestEmitOrchestrator(_CacheClearing):
    """emit_backbone_corridor_chain candidate selection — no PDF I/O needed."""

    def test_candidate_from_pdf_allowed(self):
        rr = {"reason": "resolved_via_print_token_sheets",
              "pdf_allowed_route_ids": ["route_480"]}
        res = R.emit_backbone_corridor_chain(
            resolve_result=rr, pdf_paths=[], print_tokens=[],
            terminal_nodes=[], route_catalog=CATALOG_CHAIN)
        self.assertEqual(res["candidate_route_id"], "route_480")
        self.assertEqual(res["candidate_source"], "pdf_allowed_route_ids")
        self.assertEqual(res["reason"], "deterministic_simple_chain")
        self.assertEqual(set(res["chain_route_ids"]),
                         {"route_480", "route_479", "route_475"})

    def test_candidate_from_topology_reused(self):
        # reuses an already-computed backbone_via_topology (topology_v2 path).
        rr = {"reason": "nearest_corridor_non_backbone_within_250ft",
              "pdf_allowed_route_ids": [],
              "backbone_via_topology": {"reason": "deterministic_single_backbone",
                                        "backbones": ["route_480"]}}
        res = R.emit_backbone_corridor_chain(
            resolve_result=rr, pdf_paths=[], print_tokens=[],
            terminal_nodes=[], route_catalog=CATALOG_CHAIN)
        self.assertEqual(res["candidate_route_id"], "route_480")
        self.assertEqual(res["candidate_source"], "backbone_via_topology")
        self.assertEqual(res["reason"], "deterministic_simple_chain")

    def test_no_candidate_backbone(self):
        rr = {"reason": "no_ap_ids_on_print_token_sheets", "pdf_allowed_route_ids": []}
        res = R.emit_backbone_corridor_chain(
            resolve_result=rr, pdf_paths=[], print_tokens=[],
            terminal_nodes=[], route_catalog=CATALOG_CHAIN)
        self.assertIsNone(res["candidate_route_id"])
        self.assertIsNone(res["candidate_source"])
        self.assertEqual(res["reason"], "no_candidate_backbone")
        self.assertEqual(res["chain_route_ids"], [])

    def test_topology_ambiguous_yields_no_candidate(self):
        rr = {"reason": "x", "pdf_allowed_route_ids": [],
              "backbone_via_topology": {"reason": "ambiguous_multi_backbone",
                                        "backbones": ["route_480", "route_479"]}}
        res = R.emit_backbone_corridor_chain(
            resolve_result=rr, pdf_paths=[], print_tokens=[],
            terminal_nodes=[], route_catalog=CATALOG_CHAIN)
        self.assertEqual(res["reason"], "no_candidate_backbone")


class TestEmitShadowBackboneChainFlagOff(unittest.TestCase):
    """On the pdf_plan_data_unavailable path (empty pdf_paths) the backbone-chain
    attach is not reached, so flag OFF and ON are both byte-identical (no key).
    Mirrors TestEmitShadowTopologyFlagOff."""

    def setUp(self):
        R._ADJ_CACHE.clear()

    def _emit(self, **over):
        base = dict(source_file="bore_log72.xlsx", print_tokens=["23", "24"], notes_text="",
                    pdf_paths=[], point_features=[], route_catalog=CATALOG_CHAIN,
                    hardcoded_allowed_route_ids=[])
        base.update(over)
        return R.emit_shadow_for_group(**base)

    def test_off_default_no_backbone_chain_key(self):
        off = self._emit(backbone_chain_shadow=False)
        self.assertNotIn("backbone_corridor_chain", off)
        self.assertEqual(off, self._emit())   # param absent == False

    def test_on_without_pdfs_still_no_backbone_chain_key(self):
        self.assertNotIn("backbone_corridor_chain", self._emit(backbone_chain_shadow=True))

    def test_other_subflags_unaffected(self):
        # backbone_chain_shadow ON must not perturb the topology_v2 / extract_v2 keys.
        a = self._emit(topology_v2=True, extract_ap_v2=True, backbone_chain_shadow=False)
        b = self._emit(topology_v2=True, extract_ap_v2=True, backbone_chain_shadow=True)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
