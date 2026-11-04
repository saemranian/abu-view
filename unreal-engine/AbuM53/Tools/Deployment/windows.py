"""Prepare, install and verify a locally built UE 5.8 Win64 plugin. No downloads."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Tools/QA'))
sys.path.insert(0, str(ROOT / 'Tools/Versioning'))
from audit_source import audit
import version


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8', newline='\n')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def source_state():
    value = version.check(ROOT)
    result = audit(ROOT)
    if not result['passed']:
        raise ValueError('Source audit failed: ' + '; '.join(result['violations']))
    files = result['files']
    identity = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {'version': value, 'source_sha256': identity, 'files': files}


def stage(directory):
    directory = directory.resolve()
    if ROOT == directory or ROOT in directory.parents:
        raise ValueError('Build staging must be outside the repository')
    state = source_state()
    # A fresh directory prevents UAT from clearing unrelated existing files.
    directory.mkdir(parents=True, exist_ok=False)
    target = directory / 'Source/AbuM53'
    for item in state['files']:
        source = ROOT / item['path']
        destination = target / item['path']
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if digest(destination) != item['sha256']:
            raise ValueError('Source changed during snapshot: ' + item['path'])
    write(directory / 'source-manifest.json', state)
    return {'snapshot': str(target), 'version': state['version']}


def validate_package(package, state):
    descriptor = load(package / 'AbuM53.uplugin')
    if (package / 'VERSION').read_text().strip() != state['version'] or descriptor['VersionName'] != state['version']:
        raise ValueError('Packaged version does not match source')
    if descriptor['Version'] != version.number(state['version']) or not descriptor.get('Installed'):
        raise ValueError('Expected an installed BuildPlugin package')
    for module in ('Runtime', 'Render', 'Editor'):
        if not (package / f'Binaries/Win64/UnrealEditor-AbuM53{module}.dll').is_file():
            raise ValueError('Missing compiled editor module: ' + module)
    if not (package / 'Binaries/Win64/UnrealEditor.modules').is_file():
        raise ValueError('Missing engine module compatibility manifest')
    # UAT rewrites the descriptor; all other audited source must match exactly.
    for item in state['files']:
        relative = item['path']
        if relative.startswith(('.github/', '.git')) or relative == 'AbuM53.uplugin':
            continue
        path = package / relative
        if not path.is_file() or digest(path) != item['sha256']:
            raise ValueError('Missing or changed packaged source: ' + relative)


def require_untagged_release(release):
    """Fail closed if the release exists or Git cannot establish its absence."""
    tag = subprocess.run(['git', 'show-ref', '--verify', '--quiet', 'refs/tags/' + release], cwd=ROOT)
    if tag.returncode != 1:
        raise ValueError('Same-version replacement requires an untagged local release; tagged releases require a newer version')


def validate_installation_receipt(target, receipt):
    """Check the old copy independently of the new source before replacement."""
    validate_package(target, {'version': receipt['version'], 'files': []})
    descriptor = load(target / 'AbuM53.uplugin')
    if (descriptor.get('FriendlyName') != 'Abu M53' or
        descriptor.get('VersionName') != receipt['version'] or
        descriptor.get('Version') != version.number(receipt['version']) or
        (target / 'VERSION').read_text().strip() != receipt['version']):
        raise ValueError('Installed version does not match its receipt')
    identity = receipt.get('source_sha256')
    if not isinstance(identity, str) or len(identity) != 64 or any(char not in '0123456789abcdef' for char in identity):
        raise ValueError('Installation receipt has no source identity')
    entries = receipt.get('files')
    if not isinstance(entries, list) or not entries:
        raise ValueError('Installation receipt has no file inventory')
    recorded = set()
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get('path'), str) or not isinstance(item.get('sha256'), str):
            raise ValueError('Invalid installation receipt entry')
        relative = item['path']
        path = PurePosixPath(relative)
        if (not relative or path.is_absolute() or '..' in path.parts or
            '\\' in relative or ':' in relative or path.as_posix() != relative or
            relative in recorded or relative == 'AbuM53-installation.json'):
            raise ValueError('Invalid installation receipt path: ' + relative)
        recorded.add(relative)
        installed = target / relative
        if not installed.is_file() or installed.is_symlink() or installed.resolve() != installed:
            raise ValueError('Installed file missing or linked: ' + relative)
        if digest(installed) != item['sha256']:
            raise ValueError('Installed file changed: ' + relative)
    actual = {path.relative_to(target).as_posix() for path in target.rglob('*')
              if path.is_file() and path.relative_to(target).as_posix() != 'AbuM53-installation.json'}
    if actual != recorded:
        raise ValueError('Installed file inventory does not match its receipt')


def install(directory, engine, finalizing_docs=False, replace_unreleased=False):
    state = source_state()
    snapshot = load(directory / 'source-manifest.json')
    if state != snapshot:
        raise ValueError('Source changed after snapshot; rebuild before installing')
    package = directory / 'Package'
    validate_package(package, state)
    engine = engine.resolve()
    build = load(engine / 'Engine/Build/Build.version')
    if (build['MajorVersion'], build['MinorVersion']) != (5, 8):
        raise ValueError('This deployment targets UE 5.8')
    destination = engine / 'Engine/Plugins/Marketplace/AbuM53'
    if destination.is_symlink() or (destination.exists() and destination.resolve() != destination):
        raise ValueError('Refusing to replace a linked installation')
    if replace_unreleased or finalizing_docs:
        require_untagged_release(state['version'])
    if replace_unreleased and not destination.exists():
        raise ValueError('--replace-unreleased requires an existing same-version installation')
    if destination.exists():
        installed = load(destination / 'AbuM53.uplugin')
        if installed.get('FriendlyName') != 'Abu M53':
            raise ValueError('Destination is not a recognized Abu M53 installation')
        receipt = destination / 'AbuM53-installation.json'
        if replace_unreleased and not receipt.is_file():
            raise ValueError('--replace-unreleased requires a verified installation receipt')
        if receipt.exists():
            previous = load(receipt)
            if version.number(previous['version']) > version.number(state['version']):
                raise ValueError('Changed source requires a newer version; downgrade is refused')
            if replace_unreleased:
                if previous['version'] != state['version']:
                    raise ValueError('--replace-unreleased requires an existing same-version installation')
                validate_installation_receipt(destination, previous)
            if finalizing_docs:
                validate_installation_receipt(destination, previous)
            if (previous['source_sha256'] != state['source_sha256'] and previous['version'] == state['version'] and
                not (finalizing_docs or replace_unreleased)):
                raise ValueError('Changed source requires a newer version; use --replace-unreleased only for an untagged candidate')
        # Windows denies write access to image files mapped by a running editor.
        for path in (destination / 'Binaries/Win64').glob('UnrealEditor-AbuM53*.dll'):
            with path.open('r+b'):
                pass
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    # Backups/staging are outside Engine/Plugins so UE never discovers duplicates.
    storage = engine / 'Engine/AbuM53Deployment'
    storage.mkdir(exist_ok=True)
    temporary = storage / ('staging-' + stamp)
    shutil.copytree(package, temporary)
    validate_package(temporary, state)
    files = [{'path': p.relative_to(temporary).as_posix(), 'sha256': digest(p)}
             for p in sorted(temporary.rglob('*')) if p.is_file()]
    receipt = {key: state[key] for key in ('version', 'source_sha256')}
    receipt.update(installed_utc=stamp, engine_build=build, files=files)
    write(temporary / 'AbuM53-installation.json', receipt)
    backup = None
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        backup = storage / ('backup-' + stamp)
        destination.rename(backup)
    try:
        temporary.rename(destination)
    except OSError:
        if backup is not None:
            backup.rename(destination)
        raise
    return {'installed': str(destination), 'version': state['version'],
            'backup': str(backup) if backup else None, 'files': len(files)}


def finalize_docs(directory, engine):
    """Attach actual validation results to an untagged release, without recompiling."""
    state = source_state()
    snapshot = load(directory / 'source-manifest.json')
    if snapshot['version'] != state['version']:
        raise ValueError('Cannot finalize a different version')
    require_untagged_release(state['version'])
    old = {item['path']: item['sha256'] for item in snapshot['files']}
    new = {item['path']: item['sha256'] for item in state['files']}
    changed = {path for path in old.keys() | new.keys() if old.get(path) != new.get(path)}
    if any(not (path.startswith('Docs/') or path in ('README.md', 'CHANGELOG.md', 'AGENTS.md')) for path in changed):
        raise ValueError('Non-documentation changed; rebuild before installing')
    if old.keys() - new.keys():
        raise ValueError('Documentation removal requires a fresh package')
    target = engine.resolve() / 'Engine/Plugins/Marketplace/AbuM53'
    if target.exists():
        previous = load(target / 'AbuM53-installation.json')
        if previous['version'] != snapshot['version'] or previous['source_sha256'] != snapshot['source_sha256']:
            raise ValueError('Installed copy does not match this untagged build snapshot')
        validate_installation_receipt(target, previous)
    for relative in changed:
        for base in (directory / 'Source/AbuM53', directory / 'Package'):
            destination = base / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
    write(directory / 'source-manifest.json', state)
    return install(directory, engine, finalizing_docs=True)


def verify(engine):
    state = source_state()
    target = engine.resolve() / 'Engine/Plugins/Marketplace/AbuM53'
    receipt = load(target / 'AbuM53-installation.json')
    if any(receipt[k] != state[k] for k in ('version', 'source_sha256')):
        raise ValueError('Installed release is out of date; rebuild and install')
    validate_package(target, state)
    for item in receipt['files']:
        if digest(target / item['path']) != item['sha256']:
            raise ValueError('Installed file changed: ' + item['path'])
    return {'passed': True, 'version': state['version'], 'installed': str(target), 'verified_files': len(receipt['files'])}


def project(directory, engine):
    # Never replace an existing project or its assets.
    directory = directory.resolve()
    if directory.name != 'abu_M53_Test_01':
        raise ValueError('Expected project folder abu_M53_Test_01')
    directory.mkdir(parents=True, exist_ok=False)
    plugins = [{'Name': name, 'Enabled': True} for name in
               ('AbuM53', 'PythonScriptPlugin', 'EditorScriptingUtilities')]
    for path in sorted((engine / 'Engine/Plugins/Marketplace').glob('**/*.uplugin')):
        if path.stem != 'AbuM53':
            plugins.append({'Name': path.stem, 'Enabled': False})
    write(directory / 'abu_M53_Test_01.uproject', {
        'FileVersion': 3, 'EngineAssociation': '5.8', 'Category': 'Tests',
        'Description': 'Persistent Abu M53 static and animated splat development project',
        'Plugins': plugins})
    config = directory / 'Config'
    config.mkdir()
    (config / 'DefaultEngine.ini').write_text(
        '[/Script/EngineSettings.GameMapsSettings]\n'
        'EditorStartupMap=/Game/AbuM53QA/ShellQA\nGameDefaultMap=/Game/AbuM53QA/ShellQA\n\n'
        '[/Script/WindowsTargetPlatform.WindowsTargetSettings]\n'
        'DefaultGraphicsRHI=DefaultGraphicsRHI_DX12\n'
        '-D3D12TargetedShaderFormats=PCD3D_SM5\n+D3D12TargetedShaderFormats=PCD3D_SM6\n\n'
        '[/Script/Engine.RendererSettings]\n'
        'r.DefaultFeature.AutoExposure=False\nr.DefaultFeature.MotionBlur=False\n'
        'r.AntiAliasingMethod=0\nr.DynamicGlobalIlluminationMethod=0\nr.ReflectionMethod=0\n', encoding='utf-8')
    write(directory / 'AbuM53-development.json', {'source_repository': str(ROOT),
        'installed_plugin': str(engine / 'Engine/Plugins/Marketplace/AbuM53'),
        'purpose': 'Local development paths only; not included in the public plugin repository.'})
    (directory / 'README.md').write_text(
        '# abu_M53_Test_01\n\nPersistent UE 5.8 Abu M53 test project.\n\n'
        'Open `abu_M53_Test_01.uproject`. The default ShellQA map contains a static synthetic shell. '
        'The AnimationQA map contains its three-frame animated version. Enable viewport Realtime '
        'to preview animation, or press Play. Test assets are in Content/AbuM53QA.\n\n'
        'For development updates, close this editor and run the source repository deployment script '
        '`Tools/Deployment/update_windows.ps1` after bumping/documenting the release. '
        'This project uses the engine installation; do not add a project-local AbuM53 copy. '
        'Saved/AbuM53QA holds local reports.\n', encoding='utf-8')
    return {'project': str(directory / 'abu_M53_Test_01.uproject')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('stage', 'install', 'verify', 'project', 'finalize-docs'))
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--engine', type=Path, default=Path('C:/Program Files/Epic Games/UE_5.8'))
    parser.add_argument('--replace-unreleased', action='store_true',
                        help='Explicitly replace a verified same-version installation before its Git release tag exists')
    args = parser.parse_args()
    if args.replace_unreleased and args.command != 'install':
        parser.error('--replace-unreleased applies only to install')
    try:
        if args.command == 'verify':
            result = verify(args.engine)
        elif args.directory is None:
            parser.error('--directory is required')
        elif args.command == 'stage':
            result = stage(args.directory)
        elif args.command == 'install':
            result = install(args.directory, args.engine, replace_unreleased=args.replace_unreleased)
        elif args.command == 'finalize-docs':
            result = finalize_docs(args.directory, args.engine)
        else:
            result = project(args.directory, args.engine)
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
