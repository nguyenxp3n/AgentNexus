from __future__ import annotations
import shutil,subprocess
from orch.core.harness.base import HarnessCapabilities
def discover_executable(name:str)->HarnessCapabilities:
    path=shutil.which(name)
    if not path:return HarnessCapabilities(False)
    try:
        p=subprocess.run([path,'--version'],text=True,capture_output=True,timeout=5,shell=False);version=(p.stdout or p.stderr).strip().splitlines()[0] if (p.stdout or p.stderr).strip() else None
    except Exception:version=None
    return HarnessCapabilities(True,path,version,headless=True,stdin_prompt=True,prompt_argument=True,supports_streaming=True)
