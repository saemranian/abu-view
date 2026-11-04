# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Abu Align contributors
"""Detect M54 source/dependency drift so its human-reviewed About record stays current.

Hashes detect change, not authorship or legal clearance. Refresh only after the
Markdown provenance document and file-specific origin/license scopes are reviewed.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
RECORD='docs/M54_PROVENANCE_RECORD.json'
DOCUMENT='docs/M54_PROVENANCE_AND_LICENSES.md'
SUPPORT=(
    'abu_m54_launcher.cs','m54_provenance.py','fast_viewer.py','workspace_3d.py',
    'viewer_workspace.py','native_inspection.py','rig_designer_ui.py','desktop_ui.py',
    'control_points_comparison.py','control_points_workspace.py','control_points_logging.py',
    'control_points_3d.py','control_points_model.py','manual_camera_geometry.py',
    'manual_ui_lifecycle.py','refined_exports.py','abucam_dataset.py','version_manager.py',
    'pyproject.toml','installer/requirements-core.in','installer/requirements-core.lock',
    'installer/core-files.json','installer/public-files.json','installer/build_core.py',
    'LICENSE.txt','THIRD_PARTY_NOTICES.md','licenses/M54-GAUSSIAN-NOTICE.txt',
    'licenses/M54-GAUSSIAN-APACHE-2.0.txt','.github/workflows/release.yml',DOCUMENT,
)


def fingerprints(root=ROOT):
    root=Path(root)
    names=set(SUPPORT)|{p.name for p in root.glob('abu_m54*.py')}
    # Git may materialize CRLF on Windows and LF on Linux. Hash canonical text
    # bytes so the same reviewed source passes in exported multi-OS builds.
    return {name:hashlib.sha256((root/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for name in sorted(names)}


def check_inventory(root=ROOT):
    root=Path(root)
    record=json.loads((root/RECORD).read_text(encoding='utf-8'))
    actual=fingerprints(root);stored=record['sha256']
    changed=sorted(name for name in set(actual)|set(stored) if actual.get(name)!=stored.get(name))
    if changed:raise ValueError('M54 About provenance review required for: '+', '.join(changed))
    return record


def refresh(root,review_date,reviewer,note):
    from datetime import date
    date.fromisoformat(review_date)
    if not reviewer.strip() or not note.strip():raise ValueError('A reviewer and meaningful review note are required.')
    root=Path(root);doc=(root/DOCUMENT).read_text(encoding='utf-8')
    if review_date not in doc:raise ValueError('Put the review date in the provenance document before refreshing.')
    record={'schema_version':1,'review_date':review_date,'reviewer':reviewer,'review_note':note,
            'scope':'M54 sources, shared support and packaging inputs; fingerprints detect drift, not ownership or license compatibility.',
            'document':DOCUMENT,'sha256':fingerprints(root)}
    (root/RECORD).write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--check',action='store_true');mode.add_argument('--refresh',action='store_true')
    parser.add_argument('--review-date');parser.add_argument('--reviewer');parser.add_argument('--note')
    args=parser.parse_args()
    try:
        if args.check:record=check_inventory()
        else:
            if not all((args.review_date,args.reviewer,args.note)):parser.error('--refresh needs --review-date, --reviewer and --note')
            record=refresh(ROOT,args.review_date,args.reviewer,args.note)
    except (ValueError,OSError,KeyError) as error:parser.exit(1,str(error)+'\n')
    print(f"M54 provenance current: {len(record['sha256'])} files; reviewed {record['review_date']}")


if __name__=='__main__':main()
