"""PDF-AP Route Shadow Resolver — pure unit tests (Brenham PH5 proof-slice).

Locks the read-only shadow contract proven on 2026-05-29:

- bore_log71 / bore_log72 (print 23,24; LAWNDALE/HUISACHE) resolve to the
  Lawndale/Huisache corridor and MUST NOT yield the hardcoded-wrong route_478.
- bore_log39 (print 24,25; CHERI LN) ABSTAINS with
  ``notes_street_absent_from_plan_set`` and is never force-placed.
- bore_log4 control (print 3,4,5; E Stone) resolves consistently with the
  hardcoded index (no regression).
- Own-sheet is read from the "<n> OF <total>" title-block token (NOT matchline
  "SEE SHEET n"); house-drop lines are excluded as non-corridors; the resolver
  is a pure projection that never mutates its inputs.

Fixture coordinates are anchored to the REAL PH5 proof-slice AP-terminal
centroids (ph5 audit): Lawndale/Huisache ~(30.1517,-96.3850), E Stone
~(30.1530,-96.3859), Carlee ~(30.1570,-96.3866) — ~2,100 ft from Lawndale.
"""

from __future__ import annotations

import copy
import unittest

from backend.app.core.pdf_ap_route_resolver import (
    SCHEMA_VERSION,
    build_plan_pages_from_texts,
    extract_street_names,
    is_proof_slice_source,
    resolve_pdf_ap_routes,
    terminal_nodes_from_point_features,
)


# --- shared synthetic fixtures grounded in the real proof-slice geometry ------

TERMINALS = {
    # sheet 23 (HUISACHE) AP cluster
    "109": (30.15210, -96.38540), "111": (30.15205, -96.38545),
    "113": (30.15215, -96.38535), "120": (30.15200, -96.38550),
    # sheet 24 (LAWNDALE + HUISACHE) AP cluster
    "115": (30.15144, -96.38462), "117": (30.15150, -96.38460), "119": (30.15140, -96.38465),
    # sheet 25 (LAWNDALE) AP cluster
    "116": (30.15178, -96.38247), "118": (30.15180, -96.38250), "122": (30.15175, -96.38245),
    # sheet 3 (E STONE) AP cluster
    "108": (30.15304, -96.38589), "114": (30.15300, -96.38595), "121": (30.15308, -96.38585),
}

TERMINAL_NODES = [{"name": k, "lat": v[0], "lon": v[1]} for k, v in TERMINALS.items()]

PLAN_PAGES = [
    {"page_index": 16, "sheet_number": 3, "ap_ids": [108, 114, 121], "streets": ["E STONE ST"]},
    {"page_index": 36, "sheet_number": 23, "ap_ids": [109, 111, 113, 120], "streets": ["HUISACHE ST"]},
    {"page_index": 37, "sheet_number": 24, "ap_ids": [115, 117, 119], "streets": ["LAWNDALE AVE", "HUISACHE ST"]},
    {"page_index": 38, "sheet_number": 25, "ap_ids": [116, 118, 122], "streets": ["LAWNDALE AVE"]},
]

ROUTE_CATALOG = [
    # Lawndale/Huisache corridor — passes through the sheet 23 + 24 clusters.
    {"route_id": "route_460", "route_name": "Underground Cable", "source_folder": "Connections / underground cable",
     "route_role": "backbone", "length_ft": 900.0,
     "coords": [[30.15210, -96.38540], [30.15170, -96.38500], [30.15144, -96.38462]]},
    # E Stone corridor — id chosen to match hardcoded print 3 -> route_476.
    {"route_id": "route_476", "route_name": "Underground Cable", "source_folder": "Connections / underground cable",
     "route_role": "backbone", "length_ft": 1200.0,
     "coords": [[30.15304, -96.38589], [30.15300, -96.38595]]},
    # Carlee/Mansfield corridor — the hardcoded-wrong target, ~2,100 ft away.
    {"route_id": "route_478", "route_name": "Underground Cable", "source_folder": "Connections / underground cable",
     "route_role": "backbone", "length_ft": 800.0,
     "coords": [[30.15696, -96.38655], [30.15700, -96.38660]]},
    # House drop sitting exactly on the sheet 24 cluster — must be EXCLUDED.
    {"route_id": "route_905", "route_name": "House Drop", "source_folder": "Connections / House Drop",
     "route_role": "drop", "length_ft": 40.0,
     "coords": [[30.15144, -96.38462], [30.15145, -96.38463]]},
]


class TestStreetExtraction(unittest.TestCase):
    def test_strips_house_number_and_keeps_suffix(self):
        self.assertEqual(extract_street_names("902 LAWNDALE AVE"), ["LAWNDALE AVE"])

    def test_cheri_ln_with_trailing_period(self):
        self.assertIn("CHERI LN", extract_street_names("CHERI LN. NEEDS REVIEW: ..."))

    def test_multiword_street(self):
        self.assertIn("E STONE ST", extract_street_names("1305 E STONE ST"))

    def test_no_false_positive_on_matchline(self):
        self.assertEqual(extract_street_names("MATCHLINE STA 6+00 - SEE SHEET 23"), [])


class TestPlanPageBuild(unittest.TestCase):
    def test_own_sheet_from_n_of_total_not_matchline(self):
        texts = [
            "MATCHLINE STA 6+00 - SEE SHEET 23\n902 LAWNDALE AVE\nAP-115\nAP-117\n24 OF 30",
            "MATCHLINE STA 2+07 - SEE SHEET 3\n2001 HUISACHE ST\nAP-109\n23 OF 30",
        ]
        pages = build_plan_pages_from_texts(texts)
        by_sheet = {p["sheet_number"]: p for p in pages}
        self.assertIn(24, by_sheet)
        self.assertIn(23, by_sheet)
        # the "SEE SHEET 23" on the sheet-24 page must NOT become its own sheet
        self.assertEqual(by_sheet[24]["page_index"], 1)
        self.assertEqual(sorted(by_sheet[24]["ap_ids"]), [115, 117])
        self.assertIn("LAWNDALE AVE", by_sheet[24]["streets"])
        self.assertEqual(by_sheet[24]["sheet_total"], 30)

    def test_ap_id_variants(self):
        pages = build_plan_pages_from_texts(["AP-115 AP 117 AP_119\n5 OF 30"])
        self.assertEqual(sorted(pages[0]["ap_ids"]), [115, 117, 119])


class TestTerminalFilter(unittest.TestCase):
    def test_only_numeric_terminal_port_nodes(self):
        feats = [
            {"name": "115", "folder_path": "Nodes / Terminal Port Handhole", "lat": 30.1, "lon": -96.3},
            {"name": "SPLICE LOC 28", "folder_path": "Nodes / Splice HH", "lat": 30.1, "lon": -96.3},
            {"name": "", "folder_path": "Nodes / House", "lat": 30.1, "lon": -96.3},
            {"name": "120", "folder_path": "Nodes / Terminal Port Handhole", "lat": None, "lon": -96.3},
        ]
        out = terminal_nodes_from_point_features(feats)
        self.assertEqual([t["name"] for t in out], ["115"])


class TestResolveTargetLogs(unittest.TestCase):
    def test_bore_log71_resolves_lawndale_not_route_478(self):
        res = resolve_pdf_ap_routes(
            source_file="bore_log71.xlsx", print_tokens=["23", "24"],
            notes_text="LAWNDALE AVE & HUISACHE", plan_pages=PLAN_PAGES,
            terminal_nodes=TERMINAL_NODES, route_catalog=ROUTE_CATALOG,
            hardcoded_allowed_route_ids=["route_478"],
        )
        self.assertEqual(res["pdf_allowed_route_ids"], ["route_460"])
        self.assertNotIn("route_478", res["pdf_allowed_route_ids"])
        self.assertEqual(res["agreement"], "conflict")
        self.assertEqual(res["reason"], "resolved_via_print_token_sheets")
        self.assertEqual(res["pdf_sheets"], [23, 24])
        # house-drop route must not appear as a corridor candidate
        self.assertNotIn("route_905", [r["route_id"] for r in res["nearest_routes"]])

    def test_backbone_preferred_over_nearer_terminal_tail(self):
        # A terminal tail sits ON the AP cluster (~0 ft); the backbone is ~95 ft
        # away. The bore redline belongs on the backbone, not the tail stub.
        catalog = [
            {"route_id": "route_999", "route_name": "Terminal Tail",
             "source_folder": "Connections / Terminal Tail", "route_role": "tail",
             "length_ft": 30.0, "coords": [[30.15144, -96.38462], [30.15145, -96.38463]]},
            {"route_id": "route_460", "route_name": "Underground Cable",
             "source_folder": "Connections / underground cable", "route_role": "backbone",
             "length_ft": 900.0, "coords": [[30.15144, -96.38492], [30.15150, -96.38500]]},
        ]
        res = resolve_pdf_ap_routes(
            source_file="bore_log71.xlsx", print_tokens=["23", "24"],
            notes_text="LAWNDALE AVE", plan_pages=PLAN_PAGES,
            terminal_nodes=TERMINAL_NODES, route_catalog=catalog,
            hardcoded_allowed_route_ids=["route_478"],
        )
        self.assertEqual(res["nearest_routes"][0]["route_id"], "route_999")  # tail strictly closest
        self.assertEqual(res["pdf_allowed_route_ids"], ["route_460"])         # backbone chosen
        self.assertNotIn("route_999", res["pdf_allowed_route_ids"])

    def test_bore_log72_resolves_lawndale_not_route_478(self):
        res = resolve_pdf_ap_routes(
            source_file="bore_log72.xlsx", print_tokens=["23", "24"],
            notes_text="LAWNDALE AVE", plan_pages=PLAN_PAGES,
            terminal_nodes=TERMINAL_NODES, route_catalog=ROUTE_CATALOG,
            hardcoded_allowed_route_ids=["route_478"],
        )
        self.assertEqual(res["pdf_allowed_route_ids"], ["route_460"])
        self.assertNotIn("route_478", res["pdf_allowed_route_ids"])
        self.assertEqual(res["agreement"], "conflict")

    def test_bore_log39_abstains_cheri_absent(self):
        res = resolve_pdf_ap_routes(
            source_file="bore_log39.xlsx", print_tokens=["24", "25"],
            notes_text="CHERI LN. NEEDS REVIEW: form says Job Name 'BREMHAM PH4'",
            plan_pages=PLAN_PAGES, terminal_nodes=TERMINAL_NODES, route_catalog=ROUTE_CATALOG,
            hardcoded_allowed_route_ids=["route_478", "route_475"],
        )
        self.assertEqual(res["pdf_allowed_route_ids"], [])
        self.assertTrue(res["reason"].startswith("notes_street_absent_from_plan_set"))
        self.assertIn("CHERI LN", res["reason"])
        self.assertEqual(res["agreement"], "pdf_empty_abstain")

    def test_bore_log4_control_resolves_estone_consistent(self):
        res = resolve_pdf_ap_routes(
            source_file="bore_log4.xlsx", print_tokens=["3", "4", "5"],
            notes_text="", plan_pages=PLAN_PAGES,
            terminal_nodes=TERMINAL_NODES, route_catalog=ROUTE_CATALOG,
            hardcoded_allowed_route_ids=["route_476", "route_479", "route_480"],
        )
        self.assertEqual(res["pdf_allowed_route_ids"], ["route_476"])
        self.assertEqual(res["agreement"], "overlap")
        self.assertEqual(res["reason"], "resolved_via_print_token_sheets")


class TestResolveEdgeReasons(unittest.TestCase):
    def test_no_numeric_print_tokens(self):
        res = resolve_pdf_ap_routes(
            source_file="bore_log4.xlsx", print_tokens=["WP"], notes_text="",
            plan_pages=PLAN_PAGES, terminal_nodes=TERMINAL_NODES, route_catalog=ROUTE_CATALOG,
        )
        self.assertEqual(res["pdf_allowed_route_ids"], [])
        self.assertEqual(res["reason"], "no_numeric_print_tokens")

    def test_no_plan_pages_for_tokens(self):
        res = resolve_pdf_ap_routes(
            source_file="bore_log4.xlsx", print_tokens=["99"], notes_text="",
            plan_pages=PLAN_PAGES, terminal_nodes=TERMINAL_NODES, route_catalog=ROUTE_CATALOG,
        )
        self.assertTrue(res["reason"].startswith("no_plan_pages_for_print_tokens"))

    def test_no_terminals_resolved(self):
        res = resolve_pdf_ap_routes(
            source_file="bore_log4.xlsx", print_tokens=["3"], notes_text="",
            plan_pages=PLAN_PAGES, terminal_nodes=[], route_catalog=ROUTE_CATALOG,
        )
        self.assertEqual(res["reason"], "no_ap_terminals_resolved")


class TestPurityAndSchema(unittest.TestCase):
    def test_does_not_mutate_inputs(self):
        pp = copy.deepcopy(PLAN_PAGES)
        tn = copy.deepcopy(TERMINAL_NODES)
        rc = copy.deepcopy(ROUTE_CATALOG)
        resolve_pdf_ap_routes(
            source_file="bore_log71.xlsx", print_tokens=["23", "24"],
            notes_text="LAWNDALE AVE", plan_pages=pp, terminal_nodes=tn, route_catalog=rc,
            hardcoded_allowed_route_ids=["route_478"],
        )
        self.assertEqual(pp, PLAN_PAGES)
        self.assertEqual(tn, TERMINAL_NODES)
        self.assertEqual(rc, ROUTE_CATALOG)

    def test_schema_and_required_keys(self):
        res = resolve_pdf_ap_routes(
            source_file="bore_log71.xlsx", print_tokens=["23", "24"], notes_text="LAWNDALE AVE",
            plan_pages=PLAN_PAGES, terminal_nodes=TERMINAL_NODES, route_catalog=ROUTE_CATALOG,
            hardcoded_allowed_route_ids=["route_478"],
        )
        self.assertEqual(res["schema"], SCHEMA_VERSION)
        for key in ("source_file", "print_tokens", "pdf_sheets", "pdf_pages", "ap_ids_found",
                    "ap_terminals_resolved", "centroid", "nearest_routes", "pdf_allowed_route_ids",
                    "hardcoded_allowed_route_ids", "agreement", "reason"):
            self.assertIn(key, res)


class TestProofSliceScope(unittest.TestCase):
    def test_only_four_target_logs(self):
        for s in ["bore_log71.xlsx", "bore_log72", "BORE_LOG39.XLSX", "bore_log4.xlsx"]:
            self.assertTrue(is_proof_slice_source(s))
        for s in ["bore_log16.xlsx", "bore_log40.xlsx", "", None, "bore_log7.xlsx"]:
            self.assertFalse(is_proof_slice_source(s))


if __name__ == "__main__":
    unittest.main()
