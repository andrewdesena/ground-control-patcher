#!/usr/bin/env python3
"""Read-only public-tree hygiene check. Never prints possible secret values."""
import re,subprocess,sys
from pathlib import Path
files=[p for p in subprocess.check_output(['git','ls-files','-z']).decode().split('\0') if p]
errors=[]
for name in files:
 p=Path(name)
 if not p.is_file():continue
 if p.suffix.lower() in ('.hex','.bak') or name.startswith(('card-staging/','node_modules/')) or p.name in ('.DS_Store','secrets.md'):
  errors.append(name+': local working artifact is tracked')
 if p.suffix in ('.md','.json','.js','.mjs','.cjs','.html','.py','.yaml','.yml'):
  text=p.read_text(errors='replace')
  for pattern in [r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'ghp_[A-Za-z0-9]{30,}',r'AKIA[A-Z0-9]{16}',r'sk_live_[A-Za-z0-9]{16,}']:
   if re.search(pattern,text):errors.append(name+': possible credential pattern (value suppressed)')
if errors:print('\n'.join(errors));sys.exit(1)
print('Public-tree hygiene check passed: no tracked HEX, card staging, backups or recognized credential patterns.')
print('This is a targeted check, not a guarantee that the full Git history contains no sensitive data.')
