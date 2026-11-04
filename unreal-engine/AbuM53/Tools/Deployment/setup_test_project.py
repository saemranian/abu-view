"""Run once with UE editor Python in a NEW abu_M53_Test_01 project.

Creates original test assets/maps. Refuses to reset an initialized project.
Re-run Tools/QA/ue_smoke.py separately for destructive fixture reimport tests.
"""
from pathlib import Path
import json
import runpy
import unreal

ROOT = Path(__file__).resolve().parents[2]
PROJECT = Path(unreal.Paths.project_dir()).resolve()
REPORT = PROJECT / 'Saved/AbuM53QA/project-setup.json'
if Path(unreal.Paths.get_project_file_path()).stem != 'abu_M53_Test_01':
    raise RuntimeError('This setup is restricted to abu_M53_Test_01')
if REPORT.exists() or unreal.EditorAssetLibrary.does_asset_exist('/Game/AbuM53QA/ShellQA'):
    raise RuntimeError('Test project already initialized; preserving existing maps and assets')
if 'AbuM53' not in unreal.PluginBlueprintLibrary.get_enabled_plugin_names():
    raise RuntimeError('Abu M53 is not enabled')
plugin_dir = Path(unreal.PluginBlueprintLibrary.get_plugin_base_dir('AbuM53')).resolve()
descriptor = json.loads((plugin_dir / 'AbuM53.uplugin').read_text(encoding='utf-8'))
if descriptor['VersionName'] != (ROOT / 'VERSION').read_text().strip():
    raise RuntimeError('Loaded plugin version differs from development source')
if not descriptor.get('Installed') or 'Marketplace' not in plugin_dir.parts:
    raise RuntimeError('Expected the installed engine plugin')
runpy.run_path(str(ROOT / 'Tools/QA/ue_smoke.py'), run_name='__main__')
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
if not levels.new_level('/Game/AbuM53QA/AnimationQA'):
    raise RuntimeError('Could not create animation test map')
actor = actors.spawn_actor_from_class(unreal.AbuM53Actor, unreal.Vector(0, 0, 0))
actor.set_actor_label('Abu M53 animated synthetic shell - 3 frames')
component = actor.get_editor_property('splat_component')
component.set_asset(unreal.load_asset('/Game/AbuM53QA/ShellSequence'))
component.set_editor_property('loop', True)
component.play()
location = unreal.Vector(330, 0, 100)
rotation = unreal.MathLibrary.find_look_at_rotation(location, unreal.Vector(0, 0, 0))
camera = actors.spawn_actor_from_class(unreal.CameraActor, location, rotation)
camera.set_actor_label('Abu M53 test camera')
camera.set_editor_property('auto_activate_for_player', unreal.AutoReceiveInput.PLAYER0)
camera.get_component_by_class(unreal.CameraComponent).set_field_of_view(55.0)
unreal.EditorLevelLibrary.set_level_viewport_camera_info(location, rotation)
if not levels.save_current_level():
    raise RuntimeError('Could not save animation map')
if not levels.load_level('/Game/AbuM53QA/ShellQA'):
    raise RuntimeError('Could not reload startup map')
unreal.EditorLevelLibrary.set_level_viewport_camera_info(location, rotation)
report = {'passed': True, 'project': PROJECT.name, 'version': descriptor['VersionName'],
          'loaded_plugin': str(plugin_dir), 'static_map': '/Game/AbuM53QA/ShellQA',
          'animated_map': '/Game/AbuM53QA/AnimationQA', 'animation_frames': 3,
          'note': 'Import, actor and map setup only; GPU rendering checked separately.'}
REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
unreal.log('ABUM53_TEST_PROJECT ' + json.dumps(report))
