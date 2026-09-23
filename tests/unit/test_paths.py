from __future__ import annotations
from pathlib import Path
import os, pytest
from orch.core.locks import normalize_repo_path, classify_path_overlap, Overlap
from orch.errors import PathOwnershipError


def test_nested_exclusive_prefixes_overlap(tmp_path: Path) -> None:
    assert classify_path_overlap(tmp_path,'src/backend/**','src/backend/auth/**') is Overlap.PROVEN_OVERLAP


def test_disjoint_top_level_prefixes_are_proven_disjoint(tmp_path: Path) -> None:
    assert classify_path_overlap(tmp_path,'src/**','tests/**') is Overlap.PROVEN_DISJOINT


def test_ambiguous_exclusive_globs_fail_closed(tmp_path: Path) -> None:
    assert classify_path_overlap(tmp_path,'src/**/models/*.py','src/auth/**/[a-z]*.py') is Overlap.AMBIGUOUS


def test_parent_traversal_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(PathOwnershipError): normalize_repo_path(tmp_path,'../../outside')


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    repo=tmp_path/'repo'; repo.mkdir(); outside=tmp_path/'outside'; outside.mkdir()
    try:
        (repo/'link').symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation not permitted on this platform/user privilege level")
    with pytest.raises(PathOwnershipError): normalize_repo_path(repo,'link/file.py')
