from __future__ import annotations
import asyncio, sys
from pathlib import Path
import pytest
from orch.core.process import ProcessSupervisor
from orch.core.harness.generic_cli import GenericCLIAdapter

@pytest.mark.asyncio
async def test_supervisor_captures_stdout_stderr_and_exit_code(tmp_path: Path) -> None:
    sup=ProcessSupervisor(tmp_path)
    r=await sup.spawn_and_wait(task_id='T',attempt_id='A',argv=[sys.executable,'-c','import sys; print("out"); print("err",file=sys.stderr)'],cwd=tmp_path,env={})
    assert r.exit_code==0
    assert 'out' in r.stdout_path.read_text() and 'err' in r.stderr_path.read_text()
    assert r.process_identity.pid > 0 and r.command_fingerprint

@pytest.mark.asyncio
async def test_supervisor_times_out_process(tmp_path: Path) -> None:
    sup=ProcessSupervisor(tmp_path)
    r=await sup.spawn_and_wait(task_id='T',attempt_id='A',argv=[sys.executable,'-c','import time; time.sleep(2)'],cwd=tmp_path,env={},timeout_seconds=0.1)
    assert r.timed_out and r.exit_code != 0


def test_generic_adapter_uses_argv_not_shell(tmp_path: Path) -> None:
    a=GenericCLIAdapter(command=['python','-c','print(1)'], prompt_delivery='stdin')
    p=a.prepare(prompt='x',cwd=tmp_path,env={})
    assert p.argv[:2]==['python','-c'] and p.stdin_text=='x'

@pytest.mark.asyncio
async def test_supervisor_redacts_secret_before_persisting(tmp_path: Path) -> None:
    sup=ProcessSupervisor(tmp_path)
    secret='ghp_123456789012345678901234567890123456'
    r=await sup.spawn_and_wait(task_id='T',attempt_id='S',argv=[sys.executable,'-c',f'print("{secret}")'],cwd=tmp_path,env={})
    assert secret not in r.stdout_path.read_text()
    assert '[REDACTED]' in r.stdout_path.read_text()
