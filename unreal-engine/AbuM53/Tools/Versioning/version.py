"""Check or prepare the four-part release counter. Never commits, tags or pushes."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
LABELS = ('README.md', 'Docs/CurrentScope.md', 'Docs/ImplementationStatus.md')


def number(value):
    match = re.fullmatch(r'v(0|[1-9][0-9]*)\.([0-9])\.([0-9])\.([0-9])', value)
    if not match:
        raise ValueError('Expected vA.B.C.D; B/C/D are single digits, with no leading zeroes')
    a, b, c, d = map(int, match.groups())
    result = a * 1000 + b * 100 + c * 10 + d
    if not 1 <= result <= 2147483647:
        raise ValueError('Version must fit a positive Unreal int32')
    return result


def next_version(value):
    n = number(value) + 1
    result = f'v{n // 1000}.{n // 100 % 10}.{n // 10 % 10}.{n % 10}'
    number(result)
    return result


def read(root, path):
    return (root / path).read_text(encoding='utf-8')


def check(root):
    value = read(root, 'VERSION').strip()
    descriptor = json.loads(read(root, 'AbuM53.uplugin'))
    if descriptor['VersionName'] != value or descriptor['Version'] != number(value):
        raise ValueError('Plugin metadata differs from VERSION')
    if f'project(AbuM53Core VERSION {value[1:]} LANGUAGES CXX)' not in read(root, 'Core/CMakeLists.txt'):
        raise ValueError('CMake version differs from VERSION')
    for path in LABELS:
        if value not in read(root, path):
            raise ValueError('Missing current version in ' + path)
    if value not in read(root, f'Docs/Changes/{value}.md'):
        raise ValueError('Missing change record version')
    if f'## {value} ' not in read(root, 'CHANGELOG.md'):
        raise ValueError('Missing changelog entry')
    return value


def prepare(root, summary, details, validation):
    old = check(root)
    new = next_version(old)
    if not all(s.strip() for s in (summary, details, validation)):
        raise ValueError('Summary, implementation details and actual validation are required')
    if '\n' in summary or '\r' in summary:
        raise ValueError('Summary must be one line')
    record = f'Docs/Changes/{new}.md'
    if (root / record).exists():
        raise ValueError('Refusing to overwrite an existing release record')
    # Prepare all content before writing; Git is the recovery/history mechanism.
    updates = {'VERSION': new + '\n'}
    descriptor = json.loads(read(root, 'AbuM53.uplugin'))
    descriptor.update(Version=number(new), VersionName=new)
    updates['AbuM53.uplugin'] = json.dumps(descriptor, indent=2) + '\n'
    updates['Core/CMakeLists.txt'] = read(root, 'Core/CMakeLists.txt').replace(
        f'project(AbuM53Core VERSION {old[1:]} LANGUAGES CXX)',
        f'project(AbuM53Core VERSION {new[1:]} LANGUAGES CXX)', 1)
    for path in LABELS:
        updates[path] = read(root, path).replace(old, new, 1)
    date = datetime.now(timezone.utc).date().isoformat()
    updates[record] = (f'# {new} — {summary}\n\nDate: {date} (UTC). Previous: {old}.\n\n'
        f'## Steps and implementation\n\n1. {details.strip()}\n2. Updated release metadata from {old} to {new}.\n\n'
        f'## Validation\n\n{validation.strip()}\n\n'
        '## Files, limitations and migration\n\nBefore committing, enumerate affected files and document limitations and migration requirements.\n')
    log = read(root, 'CHANGELOG.md')
    index = log.index('## ')
    entry = (f'## {new} — {summary}\n\n- {details.strip()}\n- Validation: {validation.strip()}\n'
        f'- [Step-by-step record](Docs/Changes/{new}.md).\n\n')
    updates['CHANGELOG.md'] = log[:index] + entry + log[index:]
    for path, content in updates.items():
        (root / path).write_text(content, encoding='utf-8', newline='\n')
    check(root)
    return new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('check')
    commands.add_parser('next')
    bump = commands.add_parser('bump')
    for field in ('summary', 'details', 'validation'):
        bump.add_argument('--' + field, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'bump':
            print(prepare(ROOT, args.summary, args.details, args.validation))
            print('Prepared only. Review docs/diff, run checks, then commit and tag.')
        elif args.command == 'next':
            print(next_version(check(ROOT)))
        else:
            print('PASS version consistency: ' + check(ROOT))
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
