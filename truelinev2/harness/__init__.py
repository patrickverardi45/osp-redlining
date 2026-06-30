"""Cold-package evaluation harness (READ-ONLY).

Drives ARBITRARY (never-before-seen) uploaded packages through the SAME product contracts the real API
uses (create project -> create job -> accept_upload -> reviewed-bore-log gate -> run_product_redline), with
an EMPTY (configured, zero-corpora) registry so the recognized-corpus shortcut can never fire — the harness
measures the engine's ACTUAL cold-package behavior, never a memorized render. It RUNS no engine and RENDERS nothing itself; it only
calls the existing contracts and SCORES the decision (ABSTAIN / REVIEW / AUTO) against each fixture's
expected outcome. A correct ABSTAIN (the expected named blocker) is a PASS, not a failure — an honest
abstain is evidence of a real, named missing capability.

Boundaries: no engine/renderer/fixture/anchor/coordinate/contract change; the deterministic frontier is
untouched. Name-free: no customer/project/location/operator literal lives here (fixtures use generic ids and
opaque runtime labels only). Fixture DATA lives gitignored under data/outputs/; this CODE is tracked.
"""
