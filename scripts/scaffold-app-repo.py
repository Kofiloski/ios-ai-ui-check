#!/usr/bin/env python3

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import plistlib
import re
import shlex
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NoReturn


APPLICATION_PRODUCT_TYPE = "com.apple.product-type.application"
UI_TEST_PRODUCT_TYPE = "com.apple.product-type.bundle.ui-testing"
DEFAULT_SCENARIO_FILE_NAME = "verify-primary-flow.json"
DEFAULT_SIMULATOR_NAME = "iPhone 17 Pro"
DEFAULT_SIMULATOR_RUNTIME = "26.2"
DEFAULT_SOURCE_REPO = "<owner>/ios-ai-ui-check"


@dataclass(frozen=True)
class PlannedFile:
    path: Path
    relative_path: str
    content: str
    executable: bool = False
    customizable: bool = False


@dataclass(frozen=True)
class FileAction:
    relative_path: str
    state: str
    customizable: bool


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    action_repo_root = Path(__file__).resolve().parent.parent
    project_path = resolve_project_path(repo_root, args.project)
    project_relative_path = project_path.relative_to(repo_root).as_posix()
    scheme_name = args.scheme
    app_target_name = args.app_target or scheme_name
    ui_test_target_name = args.ui_test_target or f"{app_target_name}UITests"
    simulator_name = args.simulator_name
    simulator_runtime = args.simulator_runtime
    scenario_relative_path = Path(".github/ai-ui") / args.scenario_file_name
    scaffold_manifest_relative_path = Path(".github/ai-ui/scaffold-manifest.json")
    template_dir = action_repo_root / "templates"
    source_repo = resolve_github_repo_slug(action_repo_root)
    source_commit = resolve_git_commit(action_repo_root)
    refresh_command = build_refresh_command(
        script_path=action_repo_root / "scripts" / "scaffold-app-repo.py",
        repo_root=repo_root,
        project_relative_path=project_relative_path,
        args=args,
        app_target_name=app_target_name,
        ui_test_target_name=ui_test_target_name,
    )
    managed_files = [
        f"Tests/{ui_test_target_name}/ScenarioRunnerUITests.swift",
        "scripts/run-ai-ui-scenario.sh",
        "scripts/local-ai-ui-check.sh",
        "scripts/plan-ai-ui-scenario.sh",
        "scripts/ai_ui_contract.py",
        scaffold_manifest_relative_path.as_posix(),
    ]
    customizable_files = [
        ".github/ai-ui/planner-context.md",
        scenario_relative_path.as_posix(),
    ]
    generated_files = managed_files + customizable_files
    if not args.skip_workflow:
        managed_files.append(".github/workflows/ai-ui-check.yml")
        generated_files.append(".github/workflows/ai-ui-check.yml")

    scaffold_headers = build_scaffold_headers(
        manifest_relative_path=scaffold_manifest_relative_path.as_posix(),
        source_commit=source_commit,
    )
    scaffold_manifest = build_scaffold_manifest(
        repo_root=repo_root,
        action_repo_root=action_repo_root,
        project_relative_path=project_relative_path,
        scheme_name=scheme_name,
        app_target_name=app_target_name,
        ui_test_target_name=ui_test_target_name,
        simulator_name=simulator_name,
        simulator_runtime=simulator_runtime,
        scenario_relative_path=scenario_relative_path,
        scaffold_manifest_relative_path=scaffold_manifest_relative_path,
        refresh_command=refresh_command,
        source_repo=source_repo,
        source_commit=source_commit,
        generated_files=generated_files,
        args=args,
    )

    project_file = project_path / "project.pbxproj"
    plist, original_project_xml = load_project(project_file)
    objects = plist["objects"]

    app_target_id = find_target_id(objects, app_target_name, APPLICATION_PRODUCT_TYPE)
    if app_target_id is None:
        fail(f"Could not find application target '{app_target_name}' in {project_relative_path}")

    ui_target_id = ensure_ui_test_target(
        plist=plist,
        project_path=project_path,
        app_target_id=app_target_id,
        app_target_name=app_target_name,
        ui_test_target_name=ui_test_target_name,
    )
    patch_scheme_tree = patch_scheme(
        project_path=project_path,
        scheme_name=scheme_name,
        ui_test_target_id=ui_target_id,
        ui_test_target_name=ui_test_target_name,
    )
    planned_files = build_planned_files(
        repo_root=repo_root,
        action_repo_root=action_repo_root,
        template_dir=template_dir,
        scaffold_headers=scaffold_headers,
        project_relative_path=project_relative_path,
        scheme_name=scheme_name,
        ui_test_target_name=ui_test_target_name,
        scenario_relative_path=scenario_relative_path,
        simulator_name=simulator_name,
        simulator_runtime=simulator_runtime,
        source_repo=source_repo,
        args=args,
        scaffold_manifest=scaffold_manifest,
        scaffold_manifest_relative_path=scaffold_manifest_relative_path,
    )
    scaffold_manifest = with_manifest_hashes(
        scaffold_manifest=scaffold_manifest,
        planned_files=planned_files,
        scaffold_manifest_relative_path=scaffold_manifest_relative_path,
    )
    planned_files = replace_planned_file_content(
        planned_files=planned_files,
        relative_path=scaffold_manifest_relative_path.as_posix(),
        content=json_dumps(scaffold_manifest),
    )

    project_changed = serialize_plist(plist) != original_project_xml
    scheme_path = project_path / "xcshareddata" / "xcschemes" / f"{scheme_name}.xcscheme"
    scheme_changed = serialize_xml_tree(patch_scheme_tree) != scheme_path.read_bytes()
    file_actions = apply_planned_files(
        planned_files,
        preserve_customizable_files=args.preserve_customizable_files,
        dry_run=args.dry_run,
    )

    if not args.dry_run:
        if project_changed:
            save_project(project_file, plist)
        if scheme_changed:
            save_scheme(scheme_path, patch_scheme_tree)

    print_scaffold_summary(
        args=args,
        project_relative_path=project_relative_path,
        scheme_name=scheme_name,
        ui_test_target_name=ui_test_target_name,
        scenario_relative_path=scenario_relative_path,
        scaffold_manifest_relative_path=scaffold_manifest_relative_path,
        project_changed=project_changed,
        scheme_path=scheme_path.relative_to(repo_root).as_posix(),
        scheme_changed=scheme_changed,
        file_actions=file_actions,
    )

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scaffold the repo-local files needed by ios-ai-ui-check."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Path to the app repository root. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--project",
        type=Path,
        help="Relative or absolute path to the .xcodeproj file. If omitted and only one project exists, it is used.",
    )
    parser.add_argument(
        "--scheme",
        required=True,
        help="Shared Xcode scheme that should build the app and generated UI test target.",
    )
    parser.add_argument(
        "--app-target",
        help="Application target name. Defaults to the scheme name.",
    )
    parser.add_argument(
        "--ui-test-target",
        help="UI test target name. Defaults to <app-target>UITests.",
    )
    parser.add_argument(
        "--scenario-file-name",
        default=DEFAULT_SCENARIO_FILE_NAME,
        help=f"Scenario file name written under .github/ai-ui/. Default: {DEFAULT_SCENARIO_FILE_NAME}",
    )
    parser.add_argument(
        "--scenario-template",
        type=Path,
        help="Optional path to a scenario JSON file to copy into the repo instead of the generic stub.",
    )
    parser.add_argument(
        "--planner-context-template",
        type=Path,
        help="Optional path to a planner-context markdown file to copy into the repo instead of the generic stub.",
    )
    parser.add_argument(
        "--simulator-name",
        default=DEFAULT_SIMULATOR_NAME,
        help="Default simulator name for the generated local runner and workflow.",
    )
    parser.add_argument(
        "--simulator-runtime",
        default=DEFAULT_SIMULATOR_RUNTIME,
        help="Default iOS Simulator runtime version for the generated local runner and workflow.",
    )
    parser.add_argument(
        "--skip-workflow",
        action="store_true",
        help="Do not generate .github/workflows/ai-ui-check.yml.",
    )
    parser.add_argument(
        "--preserve-customizable-files",
        action="store_true",
        help="Leave existing planner-context and scenario files untouched while refreshing managed scaffold files.",
    )
    parser.add_argument(
        "--dry-run",
        "--preview",
        action="store_true",
        help="Preview project, scheme, and file changes without writing them.",
    )
    return parser.parse_args()


def resolve_project_path(repo_root: Path, explicit_project: Path | None) -> Path:
    if explicit_project is not None:
        project_path = explicit_project
        if not project_path.is_absolute():
            project_path = repo_root / project_path
        if project_path.suffix != ".xcodeproj":
            fail(f"--project must point to a .xcodeproj directory: {project_path}")
        if not project_path.exists():
            fail(f"Project not found: {project_path}")
        return project_path.resolve()

    projects = sorted(repo_root.glob("*.xcodeproj"))
    if len(projects) == 1:
        return projects[0].resolve()

    if not projects:
        fail(f"No .xcodeproj files found under {repo_root}")

    names = ", ".join(project.name for project in projects)
    fail(f"Multiple .xcodeproj files found under {repo_root}: {names}. Pass --project explicitly.")


def load_project(project_file: Path) -> tuple[dict, bytes]:
    project_bytes = project_file.read_bytes()
    try:
        return plistlib.loads(project_bytes), project_bytes
    except plistlib.InvalidFileException:
        pass

    completed = subprocess.run(
        ["plutil", "-convert", "xml1", "-o", "-", str(project_file)],
        check=True,
        capture_output=True,
    )
    project_xml = completed.stdout
    return plistlib.loads(project_xml), project_xml


def save_project(project_file: Path, plist: dict) -> None:
    with project_file.open("wb") as handle:
        handle.write(serialize_plist(plist))


def save_scheme(scheme_path: Path, tree: ET.ElementTree) -> None:
    scheme_path.write_bytes(serialize_xml_tree(tree))


def find_target_id(objects: dict, target_name: str, product_type: str) -> str | None:
    for object_id, payload in objects.items():
        if payload.get("isa") != "PBXNativeTarget":
            continue
        if payload.get("name") == target_name and payload.get("productType") == product_type:
            return object_id
    return None


def ensure_ui_test_target(
    *,
    plist: dict,
    project_path: Path,
    app_target_id: str,
    app_target_name: str,
    ui_test_target_name: str,
) -> str:
    objects = plist["objects"]
    root_object = objects[plist["rootObject"]]
    main_group_id = root_object["mainGroup"]
    main_group = objects[main_group_id]
    products_group_id = find_group_id(objects, name="Products") or fail("Could not locate the Products group.")
    frameworks_group_id = find_group_id(objects, name="Frameworks")
    if frameworks_group_id is None:
        frameworks_group_id = make_id(objects)
        objects[frameworks_group_id] = {
            "isa": "PBXGroup",
            "children": [],
            "name": "Frameworks",
            "sourceTree": "<group>",
        }
        main_group.setdefault("children", []).append(frameworks_group_id)

    tests_group_path = f"Tests/{ui_test_target_name}"
    tests_group_id = find_group_id(objects, path=tests_group_path)
    if tests_group_id is None:
        tests_group_id = make_id(objects)
        objects[tests_group_id] = {
            "isa": "PBXGroup",
            "children": [],
            "path": tests_group_path,
            "sourceTree": "<group>",
        }
        insert_before_group(objects, main_group_id, tests_group_id, "Products")

    scenario_runner_file_ref_id = ensure_file_reference(
        objects=objects,
        group_id=tests_group_id,
        path="ScenarioRunnerUITests.swift",
        last_known_file_type="sourcecode.swift",
    )
    product_file_ref_id = ensure_product_file_reference(
        objects=objects,
        products_group_id=products_group_id,
        path=f"{ui_test_target_name}.xctest",
    )
    xctest_framework_ref_id = ensure_xctest_framework_reference(
        objects=objects,
        frameworks_group_id=frameworks_group_id,
    )

    ui_target_id = find_target_id(objects, ui_test_target_name, UI_TEST_PRODUCT_TYPE)
    if ui_target_id is None:
        config_list_id = create_ui_test_configurations(
            objects=objects,
            app_target_id=app_target_id,
            app_target_name=app_target_name,
            ui_test_target_name=ui_test_target_name,
        )
        sources_phase_id = make_id(objects)
        frameworks_phase_id = make_id(objects)
        proxy_id = make_id(objects)
        dependency_id = make_id(objects)
        ui_target_id = make_id(objects)

        objects[sources_phase_id] = {
            "isa": "PBXSourcesBuildPhase",
            "buildActionMask": "2147483647",
            "files": [],
            "runOnlyForDeploymentPostprocessing": "0",
        }
        objects[frameworks_phase_id] = {
            "isa": "PBXFrameworksBuildPhase",
            "buildActionMask": "2147483647",
            "files": [],
            "runOnlyForDeploymentPostprocessing": "0",
        }
        objects[proxy_id] = {
            "isa": "PBXContainerItemProxy",
            "containerPortal": plist["rootObject"],
            "proxyType": "1",
            "remoteGlobalIDString": app_target_id,
            "remoteInfo": app_target_name,
        }
        objects[dependency_id] = {
            "isa": "PBXTargetDependency",
            "target": app_target_id,
            "targetProxy": proxy_id,
        }
        objects[ui_target_id] = {
            "isa": "PBXNativeTarget",
            "buildConfigurationList": config_list_id,
            "buildPhases": [sources_phase_id, frameworks_phase_id],
            "buildRules": [],
            "dependencies": [dependency_id],
            "name": ui_test_target_name,
            "packageProductDependencies": [],
            "productName": ui_test_target_name,
            "productReference": product_file_ref_id,
            "productType": UI_TEST_PRODUCT_TYPE,
        }
        root_object.setdefault("targets", []).append(ui_target_id)
    else:
        target_payload = objects[ui_target_id]
        target_payload["productReference"] = product_file_ref_id
        sources_phase_id = find_phase_id(objects, target_payload["buildPhases"], "PBXSourcesBuildPhase")
        frameworks_phase_id = find_phase_id(objects, target_payload["buildPhases"], "PBXFrameworksBuildPhase")
        if sources_phase_id is None:
            sources_phase_id = make_id(objects)
            objects[sources_phase_id] = {
                "isa": "PBXSourcesBuildPhase",
                "buildActionMask": "2147483647",
                "files": [],
                "runOnlyForDeploymentPostprocessing": "0",
            }
            target_payload.setdefault("buildPhases", []).append(sources_phase_id)
        if frameworks_phase_id is None:
            frameworks_phase_id = make_id(objects)
            objects[frameworks_phase_id] = {
                "isa": "PBXFrameworksBuildPhase",
                "buildActionMask": "2147483647",
                "files": [],
                "runOnlyForDeploymentPostprocessing": "0",
            }
            target_payload.setdefault("buildPhases", []).append(frameworks_phase_id)

    ensure_build_file_in_phase(
        objects=objects,
        phase_id=sources_phase_id,
        file_ref_id=scenario_runner_file_ref_id,
        comment="ScenarioRunnerUITests.swift in Sources",
    )
    ensure_build_file_in_phase(
        objects=objects,
        phase_id=frameworks_phase_id,
        file_ref_id=xctest_framework_ref_id,
        comment="XCTest.framework in Frameworks",
    )

    return ui_target_id


def create_ui_test_configurations(
    *,
    objects: dict,
    app_target_id: str,
    app_target_name: str,
    ui_test_target_name: str,
) -> str:
    app_target = objects[app_target_id]
    app_config_list = objects[app_target["buildConfigurationList"]]
    app_config_ids = list(app_config_list["buildConfigurations"])
    ui_config_ids: list[str] = []

    for app_config_id in app_config_ids:
        app_config = objects[app_config_id]
        app_settings = app_config.get("buildSettings", {})
        config_name = app_config["name"]
        debug_like = "debug" in config_name.lower()
        bundle_id = str(app_settings.get("PRODUCT_BUNDLE_IDENTIFIER", f"com.example.{slugify(app_target_name)}"))
        ui_settings: dict[str, object] = {
            "CODE_SIGN_STYLE": str(app_settings.get("CODE_SIGN_STYLE", "Automatic")),
            "CURRENT_PROJECT_VERSION": str(app_settings.get("CURRENT_PROJECT_VERSION", "1")),
            "GENERATE_INFOPLIST_FILE": "YES",
            "IPHONEOS_DEPLOYMENT_TARGET": str(app_settings.get("IPHONEOS_DEPLOYMENT_TARGET", "17.0")),
            "PRODUCT_BUNDLE_IDENTIFIER": f"{bundle_id}UITests",
            "PRODUCT_NAME": "$(TARGET_NAME)",
            "SDKROOT": str(app_settings.get("SDKROOT", "iphoneos")),
            "SUPPORTED_PLATFORMS": str(app_settings.get("SUPPORTED_PLATFORMS", "iphoneos iphonesimulator")),
            "SWIFT_VERSION": str(app_settings.get("SWIFT_VERSION", "5.1")),
            "TARGETED_DEVICE_FAMILY": str(app_settings.get("TARGETED_DEVICE_FAMILY", "1,2")),
            "TEST_TARGET_NAME": app_target_name,
            "USES_XCTRUNNER": "YES",
        }

        for key in ("CODE_SIGN_STYLE", "CURRENT_PROJECT_VERSION", "DEVELOPMENT_TEAM", "MARKETING_VERSION"):
            if key in app_settings:
                ui_settings[key] = str(app_settings[key])

        if debug_like:
            ui_settings["SWIFT_ACTIVE_COMPILATION_CONDITIONS"] = "DEBUG"
            ui_settings["SWIFT_OPTIMIZATION_LEVEL"] = "-Onone"
        else:
            ui_settings["SWIFT_COMPILATION_MODE"] = "wholemodule"
            ui_settings["SWIFT_OPTIMIZATION_LEVEL"] = "-O"

        config_id = make_id(objects)
        objects[config_id] = {
            "isa": "XCBuildConfiguration",
            "buildSettings": ui_settings,
            "name": config_name,
        }
        ui_config_ids.append(config_id)

    config_list_id = make_id(objects)
    objects[config_list_id] = {
        "isa": "XCConfigurationList",
        "buildConfigurations": ui_config_ids,
        "defaultConfigurationIsVisible": "0",
        "defaultConfigurationName": app_config_list.get("defaultConfigurationName", "Debug"),
    }
    return config_list_id


def ensure_file_reference(*, objects: dict, group_id: str, path: str, last_known_file_type: str) -> str:
    for object_id, payload in objects.items():
        if payload.get("isa") != "PBXFileReference":
            continue
        if payload.get("path") == path and payload.get("lastKnownFileType") == last_known_file_type:
            ensure_group_child(objects, group_id, object_id)
            return object_id

    file_ref_id = make_id(objects)
    objects[file_ref_id] = {
        "isa": "PBXFileReference",
        "lastKnownFileType": last_known_file_type,
        "path": path,
        "sourceTree": "<group>",
    }
    ensure_group_child(objects, group_id, file_ref_id)
    return file_ref_id


def ensure_product_file_reference(*, objects: dict, products_group_id: str, path: str) -> str:
    for object_id, payload in objects.items():
        if payload.get("isa") != "PBXFileReference":
            continue
        if payload.get("path") == path and payload.get("explicitFileType") == "wrapper.cfbundle":
            ensure_group_child(objects, products_group_id, object_id)
            return object_id

    file_ref_id = make_id(objects)
    objects[file_ref_id] = {
        "isa": "PBXFileReference",
        "explicitFileType": "wrapper.cfbundle",
        "includeInIndex": "0",
        "path": path,
        "sourceTree": "BUILT_PRODUCTS_DIR",
    }
    ensure_group_child(objects, products_group_id, file_ref_id)
    return file_ref_id


def ensure_xctest_framework_reference(*, objects: dict, frameworks_group_id: str) -> str:
    for object_id, payload in objects.items():
        if payload.get("isa") != "PBXFileReference":
            continue
        if payload.get("name") == "XCTest.framework" or payload.get("path") == "System/Library/Frameworks/XCTest.framework":
            ensure_group_child(objects, frameworks_group_id, object_id)
            return object_id

    file_ref_id = make_id(objects)
    objects[file_ref_id] = {
        "isa": "PBXFileReference",
        "lastKnownFileType": "wrapper.framework",
        "name": "XCTest.framework",
        "path": "System/Library/Frameworks/XCTest.framework",
        "sourceTree": "SDKROOT",
    }
    ensure_group_child(objects, frameworks_group_id, file_ref_id)
    return file_ref_id


def ensure_build_file_in_phase(*, objects: dict, phase_id: str, file_ref_id: str, comment: str) -> None:
    phase = objects[phase_id]
    for build_file_id in phase.get("files", []):
        build_file = objects[build_file_id]
        if build_file.get("fileRef") == file_ref_id:
            return

    build_file_id = make_id(objects)
    objects[build_file_id] = {
        "isa": "PBXBuildFile",
        "fileRef": file_ref_id,
    }
    phase.setdefault("files", []).append(build_file_id)


def ensure_group_child(objects: dict, group_id: str, child_id: str) -> None:
    group = objects[group_id]
    children = group.setdefault("children", [])
    if child_id not in children:
        children.append(child_id)


def insert_before_group(objects: dict, parent_group_id: str, child_id: str, before_group_name: str) -> None:
    parent = objects[parent_group_id]
    children = parent.setdefault("children", [])
    if child_id in children:
        return

    for index, candidate_id in enumerate(children):
        candidate = objects.get(candidate_id, {})
        if candidate.get("isa") == "PBXGroup" and (candidate.get("name") == before_group_name or candidate.get("path") == before_group_name):
            children.insert(index, child_id)
            return

    children.append(child_id)


def find_phase_id(objects: dict, phase_ids: list[str], isa: str) -> str | None:
    for phase_id in phase_ids:
        phase = objects.get(phase_id, {})
        if phase.get("isa") == isa:
            return phase_id
    return None


def find_group_id(objects: dict, *, name: str | None = None, path: str | None = None) -> str | None:
    for object_id, payload in objects.items():
        if payload.get("isa") != "PBXGroup":
            continue
        if name is not None and payload.get("name") == name:
            return object_id
        if path is not None and payload.get("path") == path:
            return object_id
    return None


def patch_scheme(
    *,
    project_path: Path,
    scheme_name: str,
    ui_test_target_id: str,
    ui_test_target_name: str,
) -> ET.ElementTree:
    scheme_path = project_path / "xcshareddata" / "xcschemes" / f"{scheme_name}.xcscheme"
    if not scheme_path.exists():
        fail(f"Shared scheme not found: {scheme_path}. Share the scheme in Xcode before scaffolding.")

    tree = ET.parse(scheme_path)
    root = tree.getroot()
    container_ref = f"container:{project_path.name}"
    buildable_name = f"{ui_test_target_name}.xctest"

    build_action_entries = root.find("./BuildAction/BuildActionEntries")
    if build_action_entries is None:
        fail(f"Could not locate BuildActionEntries in {scheme_path}")

    if not scheme_has_buildable(build_action_entries, ui_test_target_id):
        build_action_entry = ET.SubElement(
            build_action_entries,
            "BuildActionEntry",
            {
                "buildForTesting": "YES",
                "buildForRunning": "NO",
                "buildForProfiling": "NO",
                "buildForArchiving": "NO",
                "buildForAnalyzing": "YES",
            },
        )
        ET.SubElement(
            build_action_entry,
            "BuildableReference",
            {
                "BuildableIdentifier": "primary",
                "BlueprintIdentifier": ui_test_target_id,
                "BuildableName": buildable_name,
                "BlueprintName": ui_test_target_name,
                "ReferencedContainer": container_ref,
            },
        )

    test_action = root.find("./TestAction")
    if test_action is None:
        fail(f"Could not locate TestAction in {scheme_path}")

    testables = test_action.find("Testables")
    if testables is None:
        testables = ET.SubElement(test_action, "Testables")

    if not scheme_has_buildable(testables, ui_test_target_id):
        testable_reference = ET.SubElement(
            testables,
            "TestableReference",
            {
                "skipped": "NO",
                "parallelizable": "NO",
            },
        )
        ET.SubElement(
            testable_reference,
            "BuildableReference",
            {
                "BuildableIdentifier": "primary",
                "BlueprintIdentifier": ui_test_target_id,
                "BuildableName": buildable_name,
                "BlueprintName": ui_test_target_name,
                "ReferencedContainer": container_ref,
            },
        )

    return tree


def scheme_has_buildable(parent: ET.Element, blueprint_id: str) -> bool:
    for buildable in parent.iter("BuildableReference"):
        if buildable.attrib.get("BlueprintIdentifier") == blueprint_id:
            return True
    return False


def render_template(template_path: Path, values: dict[str, str]) -> str:
    content = template_path.read_text(encoding="utf-8")
    for key, value in values.items():
        content = content.replace(f"__{key}__", value)
    return content


def write_file(path: Path, content: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        path.chmod(0o755)


def json_dumps(payload: dict[str, object]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def with_manifest_hashes(
    *,
    scaffold_manifest: dict[str, object],
    planned_files: list[PlannedFile],
    scaffold_manifest_relative_path: Path,
) -> dict[str, object]:
    hashed_files = {
        planned_file.relative_path: sha256_text(planned_file.content)
        for planned_file in planned_files
        if planned_file.relative_path != scaffold_manifest_relative_path.as_posix()
    }

    manifest = dict(scaffold_manifest)
    manifest["manifest_version"] = 2
    manifest["hash_algorithm"] = "sha256"
    manifest["hashed_files_excluded"] = [scaffold_manifest_relative_path.as_posix()]
    manifest["file_hashes"] = dict(sorted(hashed_files.items()))
    return manifest


def replace_planned_file_content(
    *,
    planned_files: list[PlannedFile],
    relative_path: str,
    content: str,
) -> list[PlannedFile]:
    updated: list[PlannedFile] = []
    for planned_file in planned_files:
        if planned_file.relative_path == relative_path:
            updated.append(
                PlannedFile(
                    path=planned_file.path,
                    relative_path=planned_file.relative_path,
                    content=content,
                    executable=planned_file.executable,
                    customizable=planned_file.customizable,
                )
            )
        else:
            updated.append(planned_file)
    return updated


def serialize_plist(plist: dict) -> bytes:
    return plistlib.dumps(plist, fmt=plistlib.FMT_XML, sort_keys=False)


def serialize_xml_tree(tree: ET.ElementTree) -> bytes:
    tree_copy = ET.ElementTree(ET.fromstring(ET.tostring(tree.getroot(), encoding="utf-8")))
    ET.indent(tree_copy, space="   ")
    buffer = BytesIO()
    tree_copy.write(buffer, encoding="UTF-8", xml_declaration=True)
    return buffer.getvalue()


def resolve_git_commit(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def resolve_github_repo_slug(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "remote", "get-url", "origin"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return DEFAULT_SOURCE_REPO

    remote_url = completed.stdout.strip()
    if not remote_url:
        return DEFAULT_SOURCE_REPO

    match = re.search(r"github\.com[:/](?P<slug>[^/\s]+/[^/\s]+?)(?:\.git)?$", remote_url)
    if match is None:
        return DEFAULT_SOURCE_REPO
    return match.group("slug")


def build_refresh_command(
    *,
    script_path: Path,
    repo_root: Path,
    project_relative_path: str,
    args: argparse.Namespace,
    app_target_name: str,
    ui_test_target_name: str,
) -> str:
    parts = [
        "python3",
        str(script_path),
        "--repo-root",
        str(repo_root),
        "--project",
        project_relative_path,
        "--scheme",
        args.scheme,
    ]

    if args.app_target is not None:
        parts.extend(["--app-target", app_target_name])
    if args.ui_test_target is not None:
        parts.extend(["--ui-test-target", ui_test_target_name])
    if args.scenario_file_name != DEFAULT_SCENARIO_FILE_NAME:
        parts.extend(["--scenario-file-name", args.scenario_file_name])
    if args.scenario_template is not None:
        parts.extend(["--scenario-template", str(args.scenario_template.resolve())])
    if args.planner_context_template is not None:
        parts.extend(
            ["--planner-context-template", str(args.planner_context_template.resolve())]
        )
    if args.simulator_name != DEFAULT_SIMULATOR_NAME:
        parts.extend(["--simulator-name", args.simulator_name])
    if args.simulator_runtime != DEFAULT_SIMULATOR_RUNTIME:
        parts.extend(["--simulator-runtime", args.simulator_runtime])
    if args.skip_workflow:
        parts.append("--skip-workflow")

    return " ".join(shlex.quote(part) for part in parts)


def build_scaffold_headers(*, manifest_relative_path: str, source_commit: str) -> dict[str, str]:
    commit_text = source_commit[:12] if source_commit != "unknown" else "unknown"
    lines = [
        "Generated by ios-ai-ui-check scaffold.",
        f"Source commit: {commit_text}.",
        f"Refresh command: see {manifest_relative_path}.",
    ]

    return {
        "shell": "\n".join(f"# {line}" for line in lines) + "\n",
        "swift": "\n".join(f"// {line}" for line in lines) + "\n",
        "yaml": "\n".join(f"# {line}" for line in lines) + "\n",
        "markdown": "<!--\n" + "\n".join(lines) + f"\nManifest: {manifest_relative_path}.\n-->\n\n",
    }


def build_scaffold_manifest(
    *,
    repo_root: Path,
    action_repo_root: Path,
    project_relative_path: str,
    scheme_name: str,
    app_target_name: str,
    ui_test_target_name: str,
    simulator_name: str,
    simulator_runtime: str,
    scenario_relative_path: Path,
    scaffold_manifest_relative_path: Path,
    refresh_command: str,
    source_repo: str,
    source_commit: str,
    generated_files: list[str],
    args: argparse.Namespace,
) -> dict[str, object]:
    generated_at = (
        datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )

    return {
        "manifest_version": 2,
        "tool": "ios-ai-ui-check",
        "source_repo": source_repo,
        "source_repo_path": str(action_repo_root),
        "source_commit": source_commit,
        "generated_at_utc": generated_at,
        "repo_root": str(repo_root),
        "project_path": project_relative_path,
        "scheme": scheme_name,
        "app_target": app_target_name,
        "ui_test_target": ui_test_target_name,
        "scenario_path": scenario_relative_path.as_posix(),
        "planner_context_path": ".github/ai-ui/planner-context.md",
        "scaffold_manifest_path": scaffold_manifest_relative_path.as_posix(),
        "simulator_name": simulator_name,
        "simulator_runtime": simulator_runtime,
        "scenario_template": str(args.scenario_template.resolve()) if args.scenario_template else None,
        "planner_context_template": (
            str(args.planner_context_template.resolve())
            if args.planner_context_template
            else None
        ),
        "workflow_generated": not args.skip_workflow,
        "managed_files": managed_files_for_manifest(
            ui_test_target_name=ui_test_target_name,
            workflow_generated=not args.skip_workflow,
        ),
        "customizable_files": customizable_files_for_manifest(
            scenario_relative_path=scenario_relative_path,
        ),
        "refresh_command": refresh_command,
        "generated_files": generated_files,
    }


def managed_files_for_manifest(*, ui_test_target_name: str, workflow_generated: bool) -> list[str]:
    managed_files = [
        f"Tests/{ui_test_target_name}/ScenarioRunnerUITests.swift",
        "scripts/run-ai-ui-scenario.sh",
        "scripts/local-ai-ui-check.sh",
        "scripts/plan-ai-ui-scenario.sh",
        "scripts/ai_ui_contract.py",
        ".github/ai-ui/scaffold-manifest.json",
    ]
    if workflow_generated:
        managed_files.append(".github/workflows/ai-ui-check.yml")
    return managed_files


def customizable_files_for_manifest(*, scenario_relative_path: Path) -> list[str]:
    return [
        ".github/ai-ui/planner-context.md",
        scenario_relative_path.as_posix(),
    ]


def build_planned_files(
    *,
    repo_root: Path,
    action_repo_root: Path,
    template_dir: Path,
    scaffold_headers: dict[str, str],
    project_relative_path: str,
    scheme_name: str,
    ui_test_target_name: str,
    scenario_relative_path: Path,
    simulator_name: str,
    simulator_runtime: str,
    source_repo: str,
    args: argparse.Namespace,
    scaffold_manifest: dict[str, object],
    scaffold_manifest_relative_path: Path,
) -> list[PlannedFile]:
    planner_context_content = (
        render_template(
            template_dir / "planner-context.md.tpl",
            {
                "SCHEME": scheme_name,
                "SCENARIO_PATH": scenario_relative_path.as_posix(),
                "SCAFFOLD_HEADER_MARKDOWN": scaffold_headers["markdown"],
            },
        )
        if args.planner_context_template is None
        else scaffold_headers["markdown"] + args.planner_context_template.read_text(encoding="utf-8")
    )

    scenario_payload = (
        render_template(template_dir / "scenario.json.tpl", {})
        if args.scenario_template is None
        else args.scenario_template.read_text(encoding="utf-8")
    )

    planned_files = [
        PlannedFile(
            path=repo_root / "Tests" / ui_test_target_name / "ScenarioRunnerUITests.swift",
            relative_path=f"Tests/{ui_test_target_name}/ScenarioRunnerUITests.swift",
            content=render_template(
                template_dir / "ScenarioRunnerUITests.swift.tpl",
                {"SCAFFOLD_HEADER_SWIFT": scaffold_headers["swift"]},
            ),
        ),
        PlannedFile(
            path=repo_root / "scripts" / "run-ai-ui-scenario.sh",
            relative_path="scripts/run-ai-ui-scenario.sh",
            content=render_template(
                template_dir / "run-ai-ui-scenario.sh.tpl",
                {
                    "PROJECT_PATH": project_relative_path,
                    "SCHEME": scheme_name,
                    "SCENARIO_PATH": scenario_relative_path.as_posix(),
                    "SIMULATOR_NAME": simulator_name,
                    "SIMULATOR_RUNTIME": simulator_runtime,
                    "UI_TEST_TARGET": ui_test_target_name,
                    "SCAFFOLD_HEADER_SHELL": scaffold_headers["shell"],
                },
            ),
            executable=True,
        ),
        PlannedFile(
            path=repo_root / "scripts" / "local-ai-ui-check.sh",
            relative_path="scripts/local-ai-ui-check.sh",
            content=render_template(
                template_dir / "local-ai-ui-check.sh.tpl",
                {
                    "SCENARIO_PATH": scenario_relative_path.as_posix(),
                    "SIMULATOR_NAME": simulator_name,
                    "SIMULATOR_RUNTIME": simulator_runtime,
                    "SCAFFOLD_HEADER_SHELL": scaffold_headers["shell"],
                },
            ),
            executable=True,
        ),
        PlannedFile(
            path=repo_root / "scripts" / "plan-ai-ui-scenario.sh",
            relative_path="scripts/plan-ai-ui-scenario.sh",
            content=render_template(
                template_dir / "plan-ai-ui-scenario.sh.tpl",
                {
                    "SCHEME": scheme_name,
                    "SCENARIO_PATH": scenario_relative_path.as_posix(),
                    "SCAFFOLD_HEADER_SHELL": scaffold_headers["shell"],
                },
            ),
            executable=True,
        ),
        PlannedFile(
            path=repo_root / "scripts" / "ai_ui_contract.py",
            relative_path="scripts/ai_ui_contract.py",
            content=(action_repo_root / "scripts" / "ai_ui_contract.py").read_text(encoding="utf-8"),
            executable=True,
        ),
        PlannedFile(
            path=repo_root / ".github" / "ai-ui" / "planner-context.md",
            relative_path=".github/ai-ui/planner-context.md",
            content=planner_context_content,
            customizable=True,
        ),
        PlannedFile(
            path=repo_root / scenario_relative_path,
            relative_path=scenario_relative_path.as_posix(),
            content=scenario_payload,
            customizable=True,
        ),
        PlannedFile(
            path=repo_root / scaffold_manifest_relative_path,
            relative_path=scaffold_manifest_relative_path.as_posix(),
            content=json_dumps(scaffold_manifest),
        ),
    ]

    if not args.skip_workflow:
        planned_files.append(
            PlannedFile(
                path=repo_root / ".github" / "workflows" / "ai-ui-check.yml",
                relative_path=".github/workflows/ai-ui-check.yml",
                content=render_template(
                    template_dir / "workflow.yml.tpl",
                    {
                        "PROJECT_PATH": project_relative_path,
                        "SCHEME": scheme_name,
                        "SCENARIO_PATH": scenario_relative_path.as_posix(),
                        "SIMULATOR_NAME": simulator_name,
                        "SIMULATOR_RUNTIME": simulator_runtime,
                        "ACTION_REPOSITORY": source_repo,
                        "SCAFFOLD_HEADER_YAML": scaffold_headers["yaml"],
                    },
                ),
            )
        )

    return planned_files


def classify_file_action(path: Path, content: str, *, executable: bool) -> str:
    if not path.exists():
        return "create"
    existing_content = path.read_text(encoding="utf-8")
    executable_matches = True
    if executable:
        executable_matches = bool(path.stat().st_mode & 0o111)
    if existing_content == content and executable_matches:
        return "unchanged"
    return "update"


def apply_planned_files(
    planned_files: list[PlannedFile],
    *,
    preserve_customizable_files: bool,
    dry_run: bool,
) -> list[FileAction]:
    actions: list[FileAction] = []

    for planned_file in planned_files:
        if (
            planned_file.customizable
            and preserve_customizable_files
            and planned_file.path.exists()
        ):
            actions.append(
                FileAction(
                    relative_path=planned_file.relative_path,
                    state="preserve",
                    customizable=True,
                )
            )
            continue

        state = classify_file_action(
            planned_file.path,
            planned_file.content,
            executable=planned_file.executable,
        )
        actions.append(
            FileAction(
                relative_path=planned_file.relative_path,
                state=state,
                customizable=planned_file.customizable,
            )
        )
        if not dry_run and state != "unchanged":
            write_file(
                planned_file.path,
                planned_file.content,
                executable=planned_file.executable,
            )

    return actions


def print_scaffold_summary(
    *,
    args: argparse.Namespace,
    project_relative_path: str,
    scheme_name: str,
    ui_test_target_name: str,
    scenario_relative_path: Path,
    scaffold_manifest_relative_path: Path,
    project_changed: bool,
    scheme_path: str,
    scheme_changed: bool,
    file_actions: list[FileAction],
) -> None:
    heading = "Scaffold preview:" if args.dry_run else "Scaffolded iOS AI UI files:"
    print(heading)
    print(f"- Project: {project_relative_path}")
    print(f"- Scheme: {scheme_name}")
    print(f"- UI test target: {ui_test_target_name}")
    print(f"- Scenario: {scenario_relative_path.as_posix()}")
    print(f"- Scaffold manifest: {scaffold_manifest_relative_path.as_posix()}")
    if args.skip_workflow:
        print("- Workflow: skipped")
    else:
        print("- Workflow: .github/workflows/ai-ui-check.yml")
    print(f"- Project file change: {'would update' if args.dry_run and project_changed else 'updated' if project_changed else 'unchanged'}")
    print(f"- Scheme change ({scheme_path}): {'would update' if args.dry_run and scheme_changed else 'updated' if scheme_changed else 'unchanged'}")

    if file_actions:
        print("- File actions:")
        for action in file_actions:
            label = action.state
            if action.customizable:
                label += " (customizable)"
            print(f"  - {label}: {action.relative_path}")


def slugify(value: str) -> str:
    cleaned = []
    for character in value.lower():
        if character.isalnum():
            cleaned.append(character)
        elif character in {" ", "-", "_"}:
            cleaned.append("-")
    slug = "".join(cleaned).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "ios-ai-ui-check"


def make_id(objects: dict) -> str:
    while True:
        candidate = uuid.uuid4().hex.upper()[:24]
        if candidate not in objects:
            return candidate


def fail(message: str) -> "NoReturn":
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    raise SystemExit(main())
