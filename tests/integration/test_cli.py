from __future__ import annotations
import json, subprocess
from pathlib import Path
from typer.testing import CliRunner
from orch.cli.main import app

runner=CliRunner()

def init_repo(path: Path) -> None:
    subprocess.run(['git','init','-b','main'],cwd=path,check=True,capture_output=True)
    subprocess.run(['git','config','user.email','x@y'],cwd=path,check=True); subprocess.run(['git','config','user.name','X'],cwd=path,check=True)
    (path/'README').write_text('x'); subprocess.run(['git','add','.'],cwd=path,check=True); subprocess.run(['git','commit','-m','base'],cwd=path,check=True,capture_output=True)


def test_help_registers_required_commands() -> None:
    r=runner.invoke(app,['--help']); assert r.exit_code==0
    for name in ['init','plan','spawn','lock','audit','merge','pr','recover','doctor','logs','version']:
        assert name in r.stdout


def test_init_is_idempotent(tmp_path: Path) -> None:
    init_repo(tmp_path)
    first=runner.invoke(app,['init','--repo',str(tmp_path)]); second=runner.invoke(app,['init','--repo',str(tmp_path)])
    assert first.exit_code==second.exit_code==0
    assert (tmp_path/'.orch/state.db').exists() and (tmp_path/'.orch/config.yaml').exists()


def test_plan_validate_and_activate(tmp_path: Path) -> None:
    init_repo(tmp_path); runner.invoke(app,['init','--repo',str(tmp_path)])
    plan=tmp_path/'tasks.yaml'; plan.write_text('version: 1\nproject: {name: x}\ntasks:\n  - id: A\n    title: A\n    description: x\n    role: core_backend\n    dependencies: []\n    ownership: {allowed_paths: ["src/**"]}\n    resources: {}\n    acceptance: {criteria: []}\n    timeout_seconds: 60\n    max_attempts: 1\n    priority: 0\n    allow_noop: true\n')
    r=runner.invoke(app,['plan','validate',str(plan),'--repo',str(tmp_path),'--json']); assert r.exit_code==0; data=json.loads(r.stdout); assert data['success']
    r2=runner.invoke(app,['plan','validate',str(plan),'--repo',str(tmp_path),'--activate','--json']); assert r2.exit_code==0; assert json.loads(r2.stdout)['run_id']
