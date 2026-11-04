"""Fresh-editor asset reload and optional copied legacy migration validation.

Set ABUM53_ASSET_RELOAD_CONFIG to JSON containing report and assets, an array of
{path, expected_splats, expected_frames}. Optional migrate_from/migrate_to copies
an old asset to a NEW package and saves only that copy in the current format.
Run in UnrealEditor-Cmd with -ExecutePythonScript; NullRHI is sufficient.
"""
import json
import os
from pathlib import Path
import time
import traceback
import unreal


def main():
    config = json.loads(Path(os.environ['ABUM53_ASSET_RELOAD_CONFIG']).read_text(encoding='utf-8'))
    report = {'passed': False, 'assets': [], 'render_test': False}
    try:
        for expected in config['assets']:
            start = time.perf_counter()
            asset = unreal.load_asset(expected['path'])
            elapsed = time.perf_counter() - start
            if asset is None:
                raise RuntimeError('Unable to reload ' + expected['path'])
            result = dict(path=expected['path'], load_seconds=elapsed, splats=asset.get_splat_count(),
                          frames=asset.get_frame_count(), decoded_bytes=asset.get_decoded_bytes())
            report['assets'].append(result)
            if result['splats'] != expected['expected_splats'] or result['frames'] != expected['expected_frames']:
                raise RuntimeError('Reloaded asset data mismatch')
        if config.get('migrate_from'):
            target = config['migrate_to']
            if not target.startswith('/Game/') or unreal.EditorAssetLibrary.does_asset_exist(target):
                raise RuntimeError('Migration requires a NEW /Game/ destination')
            start = time.perf_counter()
            migrated = unreal.EditorAssetLibrary.duplicate_asset(config['migrate_from'], target)
            if migrated is None:
                raise RuntimeError('Could not duplicate legacy asset')
            if not unreal.EditorAssetLibrary.save_loaded_asset(migrated, only_if_is_dirty=False):
                raise RuntimeError('Could not save migrated copy')
            report['migration'] = dict(path=target, copy_and_save_seconds=time.perf_counter()-start,
                                       splats=migrated.get_splat_count(), decoded_bytes=migrated.get_decoded_bytes())
        report['passed'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        unreal.log_error(report['error'])
    output = Path(config['report'])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    unreal.log('ABUM53_ASSET_RELOAD ' + json.dumps(report))
    if not report['passed']:
        raise RuntimeError('Asset reload validation failed')


main()
