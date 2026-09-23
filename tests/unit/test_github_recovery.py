from __future__ import annotations
from pathlib import Path
from orch.core.github import GitHubClient, CIState
from orch.core.recovery import RecoveryController, RecoveryKind

class FakeRunner:
    def __init__(self): self.calls=[]
    def run(self, argv, cwd=None):
        self.calls.append(argv)
        class R:
            returncode=0; stdout='[]' if 'list' in argv else '{}'; stderr=''
        return R()


def test_github_ci_requires_exact_head_sha(tmp_path: Path) -> None:
    f=FakeRunner(); c=GitHubClient(tmp_path,runner=f)
    assert c.normalize_checks([{'name':'unit','headSha':'abc','conclusion':'success'}],expected_sha='abc',required={'unit'}) is CIState.PASS
    assert c.normalize_checks([{'name':'unit','headSha':'zzz','conclusion':'success'}],expected_sha='abc',required={'unit'}) is CIState.UNKNOWN


def test_recovery_unknown_item_enters_safe_mode_plan(tmp_path: Path) -> None:
    rc=RecoveryController(tmp_path,None)
    p=rc.plan([{'kind':RecoveryKind.UNKNOWN,'detail':'mystery'}])
    assert p.enter_safe_mode and not p.destructive_actions
