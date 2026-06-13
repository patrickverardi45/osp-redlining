"""M9.8 -- Structure-Identity Binder Phase-0 tests (offline; pure helpers + posture).

Pin the per-candidate-frame terminal-identity binder on SYNTHETIC plan text through the
real BRENHAM_TERMINUS_PROFILE grammar -- no PDF, no fixtures. The LIVE Brenham facts
(log12 BIND@s3 / AP-121; the 10 pick-cards ABSTAIN; verdict FEASIBLE_YIELD_1) are gated
INSIDE the proof (run_structure_identity_binder_phase0, G1-G11).

The load-bearing tests: exactly-one terminal FULL_PAIR identity is the ONLY bind path;
AP-only / splice-only / wrong-class / run-callout / a nearest-but-noteless decoy all yield
NO identity (ABSTAIN); two identities ABSTAIN as a fork.
"""
from truelinev2.extract.terminus_profile import BRENHAM_TERMINUS_PROFILE as PROF
from truelinev2.proof import run_structure_identity_binder_phase0 as p8

STA = "4+51"


def _terminal(sta=STA, ap=999, splice=99):
    return [f"STA {sta}", f"PORT HH AP-{ap} SPLICE LOC {splice}"]

def _run_callout(sta=STA):
    return [f"STA {sta} TO STA 9+99 - 1.25\" HDPE"]


# ---- bind_verdict (pure) ----------------------------------------------------

def test_bind_verdict_exactly_one_binds():
    v, bound = p8.bind_verdict([(3, 121, "SPLICE LOC 28", None)], False)
    assert v == p8.BIND and bound[0] == 3


def test_bind_verdict_zero_abstains():
    assert p8.bind_verdict([], False)[0] == p8.ABSTAIN_NONE


def test_bind_verdict_two_is_fork():
    assert p8.bind_verdict([(2, 1, "a", None), (3, 2, "b", None)], False)[0] == p8.ABSTAIN_FORK


def test_bind_verdict_contradiction_abstains():
    assert p8.bind_verdict([], True)[0] == p8.ABSTAIN_CONTRA
    # a contradiction abstains even if an identity is present
    assert p8.bind_verdict([(3, 1, "a", None)], True)[0] == p8.ABSTAIN_CONTRA


# ---- frame_terminal_identities (real BRENHAM grammar, synthetic lines) -------

def test_exactly_one_terminal_identity_binds():
    ids, contra = p8.frame_terminal_identities(STA, {3: _terminal(ap=121), 2: _run_callout()}, PROF)
    assert not contra and len(ids) == 1 and ids[0][0] == 3 and ids[0][1] == 121
    assert p8.bind_verdict(ids, contra)[0] == p8.BIND


def test_no_terminal_note_abstains():
    ids, contra = p8.frame_terminal_identities(STA, {2: _run_callout(), 5: _run_callout()}, PROF)
    assert ids == [] and p8.bind_verdict(ids, contra)[0] == p8.ABSTAIN_NONE


def test_two_terminal_identities_fork():
    ids, _ = p8.frame_terminal_identities(STA, {2: _terminal(ap=111), 3: _terminal(ap=222)}, PROF)
    assert len(ids) == 2 and p8.bind_verdict(ids, False)[0] == p8.ABSTAIN_FORK


def test_ap_only_is_not_an_identity():
    ids, _ = p8.frame_terminal_identities(STA, {3: ["STA " + STA, "PORT HH AP-999"]}, PROF)
    assert ids == []


def test_splice_only_is_not_an_identity():
    ids, _ = p8.frame_terminal_identities(STA, {3: ["STA " + STA, "PORT HH SPLICE LOC 99"]}, PROF)
    assert ids == []


def test_non_terminal_class_is_not_an_identity():
    # INSTALLER HH is a FULL_PAIR but the WRONG class -> never a terminal identity.
    ids, _ = p8.frame_terminal_identities(STA, {3: ["STA " + STA, "INSTALLER HH AP-999 SPLICE LOC 99"]}, PROF)
    assert ids == []


def test_nearest_noteless_decoy_never_binds():
    # a frame with no terminal note is never an identity, however "near" -- only printed
    # terminal-class FULL_PAIR identity binds (no proximity/length/nearest).
    ids, contra = p8.frame_terminal_identities(STA, {99: _run_callout()}, PROF)
    assert ids == [] and p8.bind_verdict(ids, contra)[0] == p8.ABSTAIN_NONE


# ---- _code_only helper ------------------------------------------------------

def test_code_only_strips_docstring_and_comments():
    src = 'def f():\n    """no proximity, no length, no nearest"""\n    x = 1  # nearest\n    return x\n'
    out = p8._code_only(src)
    assert "proximity" not in out and "nearest" not in out and "x = 1" in out


# ---- banked constants -------------------------------------------------------

def test_banked_constants():
    assert p8.POSITIVE_CONTROL == "log12"
    assert set(p8.PARALLEL_RUN_CANDIDATES) == {"log5", "log11", "log36", "log59", "log66"}
    assert set(p8.MULTI_FRAME_CANDIDATES) == {"log6", "log41", "log58", "log63", "log64"}
    assert p8.EXPECT_DRAWABLE == 30
    assert p8.HONEST_NEGATIVE == "HONEST_NEGATIVE_NO_SAFE_YIELD"
    assert p8.BLOCKED == "BLOCKED_NEEDS_SOURCE_REREAD"
    assert p8.FEASIBLE == "STRUCTURE_IDENTITY_BINDER_FEASIBLE_YIELD_N"


# ---- posture ----------------------------------------------------------------

def test_binder_reuses_m931_and_has_no_placement():
    import inspect
    code = p8._code_only(inspect.getsource(p8.frame_terminal_identities)
                         + inspect.getsource(p8.bind_verdict))
    assert "detect_endpoint_note" in code and "attribute_endpoint" in code
    for forbidden in ("run_match", "resolve_bore", "render", "proximit", "nearest", "length", "Status"):
        assert forbidden not in code
