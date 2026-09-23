from __future__ import annotations
import argparse,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--behavior',default='success');p.add_argument('--sleep',type=float,default=0);args=p.parse_args()
if args.sleep:time.sleep(args.sleep)
print('fake-agent-start')
if args.behavior=='crash':raise SystemExit(17)
if args.behavior in {'success','dirty'}:
    Path('src').mkdir(exist_ok=True);Path('src/agent.py').write_text('value = 1\n')
    if args.behavior=='success':
        subprocess.run(['git','add','.'],check=True);subprocess.run(['git','commit','-m','agent change'],check=True,stdout=subprocess.DEVNULL)
if args.behavior=='secret':
    Path('src').mkdir(exist_ok=True);Path('src/secret.py').write_text('TOKEN="ghp_123456789012345678901234567890123456"\n');subprocess.run(['git','add','.'],check=True);subprocess.run(['git','commit','-m','secret'],check=True,stdout=subprocess.DEVNULL)
print('fake-agent-end')
