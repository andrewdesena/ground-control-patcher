#!/usr/bin/env python3
"""
build_v1.py — assemble the shipped poly bundle (V1) for index.html.

  python3 tools/build_v1.py [out.json] [out.hex] [--check-html]

Starts from the known-good 10-site bundle recorded at tag `known-good-poly`
(mods/v1-poly-known-good.json) and merges the source bundles listed in EXTRA on
top of it by address, so a new behavior is always expressed as one small source
file and the base stays byte-identical everywhere else.

--check-html proves the patcher's embedded V1 (index.html) is byte-identical to
the built bundle, which is what users actually flash.
"""
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASE = os.path.join(ROOT, 'mods', 'v1-poly-known-good.json')
HTML = os.path.join(ROOT, 'index.html')
# Extra source bundles merged on top of the base, keyed by patch address.
EXTRA = [os.path.join(ROOT, 'mods', 'poly-commit-reload.source.json')]


def build(out_path=None, hex_path=None):
    sys.path.insert(0, HERE)
    import asm
    bundle = json.load(open(BASE))
    patches = [dict(p) for p in bundle['patches']]
    for path in EXTRA:
        built = asm.build(json.load(open(path)))
        for site in built['patches']:
            addr = int(site['addr'], 16)
            for i, cur in enumerate(patches):
                if int(cur['addr'], 16) == addr:
                    patches[i] = dict(site)
                    break
            else:
                patches.append(dict(site))
    patches.sort(key=lambda p: int(p['addr'], 16))

    out = {
        'name': 'Polyphony',
        'version': os.environ.get('GC_VERSION', '1.2'),
        'status': 'experimental',
        'description': ('Known-good v1.1 polyphony build plus a post-switch reload: after the commit '
                        'installs the incoming patterns and letters, each melodic track republishes '
                        'its own poly sidecar into the chord bank. FR_NO_FILE zeroes the bank; any '
                        'other FRESULT leaves it untouched.'),
        'requires': dict(bundle.get('requires', {})),
        'patches': patches,
    }
    out['requires']['blank'] = ['0x08046810', '0x0804A000']
    if out_path:
        json.dump(out, open(out_path, 'w'), indent=2)
        print('wrote', out_path, len(patches), 'sites')
    if hex_path:
        assert out_path, 'need an out.json to build a hex'
        subprocess.run([sys.executable, os.path.join(HERE, 'apply.py'), out_path, hex_path],
                       check=True)
        h = hashlib.sha256(open(hex_path, 'rb').read()).hexdigest()
        print('hex   ', hex_path)
        print('sha256', h)
        print('size  ', os.path.getsize(hex_path))
    return out


def embedded(html_text):
    """Pull the patcher's embedded V1 patch list out of index.html (JS object literal)."""
    body = html_text.split('  var V1 = ', 1)[1].split(';\n  var mods', 1)[0]
    patches = [{'addr': a, 'bytes': b.lower()} for a, b in
               re.findall(r"addr: '(0x[0-9a-fA-F]+)', bytes: '([0-9a-fA-F]+)'", body)]
    name = re.search(r"name: '([^']*)'", body)
    version = re.search(r"version: '([^']*)'", body)
    return {'name': name.group(1) if name else '', 'version': version.group(1) if version else '',
            'patches': patches}


def check_html(bundle):
    emb = embedded(open(HTML).read())
    want = [{'addr': p['addr'], 'bytes': p['bytes'].lower()} for p in bundle['patches']]
    if emb['patches'] != want:
        got = {p['addr'].lower(): p['bytes'] for p in emb['patches']}
        for p in want:
            if got.get(p['addr'].lower()) != p['bytes']:
                raise SystemExit(f"index.html V1 diverges at {p['addr']}: "
                                 f"{len(got.get(p['addr'].lower(), '')) // 2} bytes vs "
                                 f"{len(p['bytes']) // 2}")
        raise SystemExit('index.html V1 has a different patch set')
    print(f"OK index.html V1 matches the built bundle ({len(want)} sites, "
          f"'{emb['name']}' {emb['version']})")


def write_html(bundle, filename=None):
    """Rewrite index.html's embedded V1 to match the built bundle, then verify it."""
    text = open(HTML).read()
    head = '  var V1 = '
    start = text.index(head) + len(head)
    end = text.index(';\n  var mods', start)
    desc = bundle['description'].replace('\\', '\\\\').replace("'", "\\'")
    lines = ["{",
             "    name: '%s v%s', version: '%s', status: 'experimental', enabled: true,"
             % (bundle['name'], bundle['version'], bundle['version']),
             "    description: '%s'," % desc,
             "    patches: ["]
    for i, p in enumerate(bundle['patches']):
        comma = ',' if i < len(bundle['patches']) - 1 else ''
        lines.append("      { addr: '%s', bytes: '%s' }%s" % (p['addr'], p['bytes'].lower(), comma))
    lines += ["    ]", "  }"]
    text = text[:start] + '\n'.join(lines) + text[end:]
    if filename:
        m = re.search(r"'gc-v3\.26_poly-v[0-9.]+\.hex'", text)
        if m:
            text = text[:m.start()] + "'%s'" % filename + text[m.end():]
    open(HTML, 'w').write(text)
    check_html(bundle)
    print('wrote index.html V1 (%s)' % filename)


if __name__ == '__main__':
    # any extra source bundles named on the command line stack on top of EXTRA
    EXTRA.extend(a for a in sys.argv[1:] if a.endswith('.source.json'))
    args = [a for a in sys.argv[1:] if not a.startswith('--') and not a.endswith('.source.json')]
    o = args[0] if args else os.path.join(ROOT, 'mods', 'v1-poly-full-gated.json')
    h = args[1] if len(args) > 1 else None
    built = build(o, h)
    if '--check-html' in sys.argv:
        check_html(built)
    if '--write-html' in sys.argv:
        write_html(built, 'gc-v3.26_poly-v%s.hex' % built['version'])
