"""Contract tests: the customer_project isolation root. Pure stdlib + tmp_path; no engine/render/wiring.

All ids/labels here are GENERIC placeholders — no real customer/project/person/location strings.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from truelinev2.contracts.customer_project import (
    CUSTOMER_PROJECTS_SUBDIR,
    PROJECT_RECORD_FILENAME,
    CrossProjectAccessError,
    InvalidProjectIdError,
    ProjectNotFoundError,
    assert_same_project,
    create_customer_project,
    load_customer_project,
    project_root,
    validate_customer_project_id,
)

AT = "2026-06-20T00:00:00Z"


def test_valid_and_invalid_ids():
    assert validate_customer_project_id("cp-0001") == "cp-0001"
    for bad in ["", "../escape", "Has Space", "UPPER", "a/b", "c:evil", "..", None, 5, "x" * 64]:
        with pytest.raises(InvalidProjectIdError):
            validate_customer_project_id(bad)


def test_scoped_path_stays_in_root(tmp_path):
    pr = project_root(tmp_path, "cp-0001")
    assert pr == Path(tmp_path) / CUSTOMER_PROJECTS_SUBDIR / "cp-0001"
    assert str(pr).startswith(str(tmp_path))


def test_create_and_load_record(tmp_path):
    rec = create_customer_project(tmp_path, "cp-0001", "Opaque Display Label", AT)
    assert rec["id"] == "cp-0001"
    assert rec["display_name"] == "Opaque Display Label"  # opaque runtime data, stored verbatim
    assert load_customer_project(tmp_path, "cp-0001") == rec
    p = Path(tmp_path) / CUSTOMER_PROJECTS_SUBDIR / "cp-0001" / PROJECT_RECORD_FILENAME
    assert p.is_file() and json.loads(p.read_text())["id"] == "cp-0001"


def test_missing_record_raises(tmp_path):
    with pytest.raises(ProjectNotFoundError):
        load_customer_project(tmp_path, "cp-absent")


def test_cross_project_access_denied():
    assert_same_project("cp-0001", "cp-0001")  # same -> ok (returns None)
    with pytest.raises(CrossProjectAccessError):
        assert_same_project("cp-0001", "cp-0002")


def test_two_projects_are_isolated(tmp_path):
    a = create_customer_project(tmp_path, "cp-a", "Label A", AT)
    b = create_customer_project(tmp_path, "cp-b", "Label B", AT)
    assert a["id"] != b["id"]
    pa = Path(tmp_path) / CUSTOMER_PROJECTS_SUBDIR / "cp-a"
    pb = Path(tmp_path) / CUSTOMER_PROJECTS_SUBDIR / "cp-b"
    assert pa.is_dir() and pb.is_dir()
    # distinct sibling scopes — neither project's dir is nested under the other
    assert pa != pb and pa.parent == pb.parent
    # each record only knows its own id (no shared/global state)
    assert load_customer_project(tmp_path, "cp-a")["id"] == "cp-a"
    assert load_customer_project(tmp_path, "cp-b")["id"] == "cp-b"
