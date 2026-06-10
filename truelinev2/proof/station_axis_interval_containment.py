"""M8.7 module path -- re-exports the solver re-homed into match/ for the M8.8
default-OFF wiring (the M8.2k -> M8.2l / M8.5 precedent). The proof runner and
M8.7 tests keep importing from here; the engine imports from match/."""
from truelinev2.match.station_axis_interval import (  # noqa: F401
    CLUSTER_GAP_FT,
    DISCONTINUITY,
    FOOTAGE_MISMATCH,
    FRAME_CONFLICT,
    PICK_CARD,
    READY,
    TICK_INTERVAL_FT,
    TICK_NOT_FOUND,
    VERDICTS,
    StationAxisContext,
    TickCluster,
    build_ladder,
    coverage_walk,
    frame_ambiguous_seeds,
    intervals_in_ladder,
    prove_interval_path,
    solve_interval_path,
    tick_clusters,
)
