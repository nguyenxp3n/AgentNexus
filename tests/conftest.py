from __future__ import annotations
import subprocess
from pathlib import Path
import pytest

@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / 'repo'
    repo.mkdir()
    def run(*args: str) -> str:
        p = subprocess.run(['git', *args], cwd=repo, text=True, capture_output=True, check=True)
        return p.stdout.strip()
    run('init', '-b', 'main')
    run('config', 'user.email', 'test@example.com')
    run('config', 'user.name', 'Test User')
    (repo / 'README.md').write_text('base\n')
    run('add', 'README.md')
    run('commit', '-m', 'base')
    (repo / '.worktrees').mkdir()
    (repo / '.gitignore').write_text('.worktrees/\n.orch/\n')
    run('add', '.gitignore')
    run('commit', '-m', 'ignore runtime')
    return repo
