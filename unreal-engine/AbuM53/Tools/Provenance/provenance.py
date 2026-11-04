"""Check reviewed origins/hashes; refresh only explicitly classified implementation files.

refresh --agent <name> --date YYYY-MM-DD [--declare origin[,origin]=path] [--remove path]
Review origins, upstream licenses and the narrative/history BEFORE refreshing.
This detects drift, not plagiarism, contribution rights or legal compatibility.
"""
import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
RECORD = 'Docs/Legal/CodeOrigins.json'
DOCUMENT = 'Docs/Legal/Repository_Origins_and_Licensing.md'
SCOPE = ('.github', 'Config', 'Core', 'Shaders', 'Source', 'Tests', 'ThirdParty', 'Tools')
IGNORED = {'.git', '__pycache__', 'binaries', 'intermediate', 'saved', 'build', '.vs'}
START, END = '<!-- provenance-review:start -->', '<!-- provenance-review:end -->'


def implementation(root):
    result = {}
    for prefix in SCOPE:
        base = root / prefix
        if not base.exists():
            continue
        for directory, dirs, names in os.walk(base, followlinks=False):
            paths = [Path(directory)] + [Path(directory) / name for name in dirs + names]
            for path in paths:
                if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
                    raise ValueError('Provenance scope contains a link: ' + str(path))
            dirs[:] = [name for name in dirs if name.lower() not in IGNORED]
            for name in names:
                path = Path(directory) / name
                if path.suffix.lower() in ('.md', '.pyc'):
                    continue
                result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(sorted(result.items()))


def fingerprint(files):
    return hashlib.sha256('\n'.join(path + '\0' + digest for path, digest in sorted(files.items())).encode()).hexdigest()


def metadata(record):
    return (f'Reviewed release: **{record["reviewed_version"]}**. Review date: **{record["reviewed_date"]}**. '
            f'Reviewing contributor: **{record["reviewer"]}**.\n\n'
            f'Reviewed implementation files: **{len(record["files"])}**. '
            f'Implementation fingerprint (SHA-256): `{record["implementation_sha256"]}`.\n\n'
            'The file ledger is a reviewed provenance declaration and drift check; it is not automated legal clearance.')


def validate(root):
    errors = []
    try:
        record = json.loads((root / RECORD).read_text(encoding='utf-8'))
        version = (root / 'VERSION').read_text(encoding='utf-8').strip()
        document = (root / DOCUMENT).read_text(encoding='utf-8')
        if record.get('schema') != 1 or record.get('reviewed_version') != version:
            errors.append('Provenance review version differs from VERSION')
        date.fromisoformat(record['reviewed_date'])
        if not record['reviewer'].strip() or record.get('scope') != list(SCOPE):
            errors.append('Provenance reviewer/scope is missing or invalid')
        actual = implementation(root)
        declared = record['files']
        for origin, details in record['origins'].items():
            if not all(isinstance(details.get(key), str) and details[key].strip() for key in ('name', 'license', 'source')):
                errors.append('Origin lacks name, license or source: ' + origin)
        for path in sorted(actual.keys() | declared.keys()):
            item = declared.get(path)
            if item is None:
                errors.append('Undeclared implementation file: ' + path)
            elif path not in actual:
                errors.append('Removed implementation file still declared: ' + path)
            else:
                origins = item.get('origins', [])
                if not origins or any(origin not in record['origins'] for origin in origins):
                    errors.append('Unknown/missing origin declaration: ' + path)
                if item.get('sha256') != actual[path]:
                    errors.append('Implementation changed since provenance review: ' + path)
        if record.get('implementation_sha256') != fingerprint(actual):
            errors.append('Implementation fingerprint is stale')
        if document.count(START) != 1 or document.count(END) != 1:
            errors.append('Missing/duplicated provenance document review block')
        elif document.split(START, 1)[1].split(END, 1)[0].strip() != metadata(record):
            errors.append('Provenance document review metadata is stale')
        if not re.search(r'^- \*\*' + re.escape(version) + r'\b', document, flags=re.M):
            errors.append('Provenance document has no current-release review history')
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        errors.append('Invalid provenance record: ' + str(error))
    return errors


def refresh(root, agent, reviewed_date, declarations=(), removals=()):
    date.fromisoformat(reviewed_date)
    if not agent.strip() or any(char in agent for char in '\r\n'):
        raise ValueError('An actual single-line reviewing contributor/agent is required')
    record = json.loads((root / RECORD).read_text(encoding='utf-8'))
    actual = implementation(root)
    for entry in declarations:
        origin_text, path = entry.split('=', 1)
        origins = origin_text.split(',')
        if path not in actual or not origins or any(origin not in record['origins'] for origin in origins):
            raise ValueError('Explicit declaration has invalid path/origin: ' + entry)
        record['files'][path] = {'origins': origins}
    for path in removals:
        if path in actual or path not in record['files']:
            raise ValueError('Removal must name a deleted, previously declared file: ' + path)
        del record['files'][path]
    if actual.keys() != record['files'].keys():
        raise ValueError('Review and explicitly declare new files/remove deleted entries before refreshing')
    for path, digest in actual.items():
        record['files'][path]['sha256'] = digest
    record.update(reviewed_version=(root / 'VERSION').read_text().strip(), reviewed_date=reviewed_date,
                  reviewer=agent, implementation_sha256=fingerprint(actual))
    document = (root / DOCUMENT).read_text(encoding='utf-8')
    if document.count(START) != 1 or document.count(END) != 1:
        raise ValueError('Document needs one review block')
    before, after = document.split(START, 1)
    _, after = after.split(END, 1)
    if not re.search(r'^- \*\*' + re.escape(record['reviewed_version']) + r'\b', document, flags=re.M):
        raise ValueError('Update the document review history for the current release before refreshing')
    document = before + START + '\n' + metadata(record) + '\n' + END + after
    (root / RECORD).write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8', newline='\n')
    (root / DOCUMENT).write_text(document, encoding='utf-8', newline='\n')
    errors = validate(root)
    if errors:
        raise ValueError('; '.join(errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('check', 'refresh'))
    parser.add_argument('--agent')
    parser.add_argument('--date')
    parser.add_argument('--declare', action='append', default=[])
    parser.add_argument('--remove', action='append', default=[])
    args = parser.parse_args()
    try:
        if args.command == 'refresh':
            if not args.agent or not args.date:
                parser.error('refresh requires --agent and --date after a provenance review')
            refresh(ROOT, args.agent, args.date, args.declare, args.remove)
        errors = validate(ROOT)
        if errors:
            parser.exit(1, '\n'.join(errors) + '\n')
        print('PASS provenance review, origin coverage, implementation hashes and document/version consistency')
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
