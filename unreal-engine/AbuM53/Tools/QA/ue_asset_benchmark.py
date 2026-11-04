"""Measure import and package save separately without replacing any existing asset.

Run with -ExecutePythonScript and ABUM53_ASSET_BENCHMARK_CONFIG pointing to a
local JSON file: source, destination (/Game/... new asset), report, expected_splats.
Optional load_existing benchmarks an old package read without modifying it.
Results are local evidence; do not commit private paths or input data.
"""
import json
import os
from pathlib import Path
import time
import traceback
import unreal


def main():
    config = json.loads(Path(os.environ['ABUM53_ASSET_BENCHMARK_CONFIG']).read_text(encoding='utf-8'))
    report = {'passed': False, 'render_test': False}
    destination = config['destination']
    try:
        if not destination.startswith('/Game/') or unreal.EditorAssetLibrary.does_asset_exist(destination):
            raise RuntimeError('Benchmark destination must be a NEW /Game/ asset')
        if config.get('load_existing'):
            start = time.perf_counter()
            old = unreal.load_asset(config['load_existing'])
            report['legacy_load_seconds'] = time.perf_counter() - start
            if old is None or old.get_splat_count() != config['expected_splats']:
                raise RuntimeError('Existing asset could not be read correctly')
            report['legacy_splats'] = old.get_splat_count()
        task = unreal.AssetImportTask()
        task.filename = config['source']
        task.destination_path, task.destination_name = destination.rsplit('/', 1)
        task.automated = True
        task.replace_existing = False
        task.save = False
        start = time.perf_counter()
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        report['import_seconds'] = time.perf_counter() - start
        paths = list(task.imported_object_paths)
        if len(paths) != 1:
            raise RuntimeError('Import did not return exactly one asset')
        asset = unreal.load_asset(paths[0])
        report.update(splats=asset.get_splat_count(), frames=asset.get_frame_count(), decoded_bytes=asset.get_decoded_bytes())
        if report['splats'] != config['expected_splats'] or report['frames'] != 1:
            raise RuntimeError('Imported point/frame count mismatch')
        start = time.perf_counter()
        if not unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False):
            raise RuntimeError('Package save failed')
        report['save_seconds'] = time.perf_counter() - start
        report.update(passed=True, asset=paths[0])
    except Exception:
        report['error'] = traceback.format_exc()
        unreal.log_error(report['error'])
    output = Path(config['report'])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    unreal.log('ABUM53_ASSET_BENCHMARK ' + json.dumps(report))
    if not report['passed']:
        raise RuntimeError('Asset benchmark failed; see report')


main()
