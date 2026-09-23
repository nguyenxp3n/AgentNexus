from __future__ import annotations
import os
from pathlib import Path
from orch.models.execution import RuntimeEnvironment,TaskAttempt
class RuntimeEnvironmentBuilder:
    def __init__(self,repo_root:Path,allowlist:set[str]|None=None):self.repo=Path(repo_root).resolve();self.allowlist=allowlist or set()
    def build(self,a:TaskAttempt)->RuntimeEnvironment:
        root=self.repo/'.orch'/'runtime'/a.attempt_id
        dirs={n:root/n for n in ('tmp','home','cache','state','artifacts')}
        for d in dirs.values():d.mkdir(parents=True,exist_ok=True)
        env={k:v for k,v in os.environ.items() if k in {'PATH','SYSTEMROOT','COMSPEC','PATHEXT','LANG','LC_ALL'} or k in self.allowlist}
        env.update({'ORCH_RUN_ID':a.run_id,'ORCH_TASK_ID':a.task_id,'ORCH_ATTEMPT_ID':a.attempt_id,'ORCH_WORKTREE':a.worktree_path,'TMPDIR':str(dirs['tmp']),'TEMP':str(dirs['tmp']),'TMP':str(dirs['tmp']),'HOME':str(dirs['home']),'XDG_CACHE_HOME':str(dirs['cache']),'XDG_STATE_HOME':str(dirs['state']),'COVERAGE_FILE':str(root/'coverage'),'PYTHONPYCACHEPREFIX':str(dirs['cache']/'pycache')})
        return RuntimeEnvironment(root=root,env=env)
