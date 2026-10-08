#!/usr/bin/env python3
"""Conservative public-source audit. Report locations only, never matching content."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(rb"pbkdf2-sha256\$[0-9]{4,}\$[a-f0-9]{16,}\$[a-f0-9]{32,}"),
)
FORBIDDEN_SUFFIXES = {'.pem', '.key', '.jks', '.keystore', '.hash', '.sqlite', '.sqlite3', '.db', '.apk', '.aab'}


def findings(path, content):
    if path.suffix.lower() in FORBIDDEN_SUFFIXES or path.name == '.env':
        return [f'{path}: runtime/private artifact must not be published']
    if b'\0' in content:
        return []
    hits = []
    for line_number, line in enumerate(content.splitlines(), 1):
        if any(pattern.search(line) for pattern in PATTERNS):
            hits.append(f'{path}:{line_number}: possible secret')
    return hits


def main():
    names = subprocess.check_output(
        ['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT
    ).decode().split('\0')
    problems = []
    for name in sorted(set(filter(None, names))):
        path = ROOT / name
        if path.is_file() and not path.is_symlink():
            problems.extend(findings(Path(name), path.read_bytes()))
    if problems:
        print('\n'.join(problems), file=sys.stderr)
        return 1
    print('Public-source secret audit passed (heuristic; review remains required).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
