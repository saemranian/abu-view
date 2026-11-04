#!/usr/bin/env python3
"""Export compact owned-test results, excluding machine paths and engine logs."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--automation", default="work/AbuM53AutomationFinal/index.json")
    parser.add_argument("--automation-output", default="ue-automation-final.json", help="Simple JSON filename inside the evidence directory")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[2] / "Docs/Evidence")
    args = parser.parse_args()
    if Path(args.automation_output).name != args.automation_output or not args.automation_output.endswith(".json"):
        parser.error("automation-output must be a simple JSON filename")
    workspace = args.workspace.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    saved = workspace / "work/AbuM53Host/Saved/AbuM53QA"
    written = []

    def write(name, report):
        text = json.dumps(report, indent=2, allow_nan=False) + "\n"
        if re.search(r"[A-Za-z]:[\\/]", text) or re.search(r"[/\\](?:Users|home)[/\\]", text):
            raise ValueError("Machine path found in evidence: " + name)
        (args.output / name).write_text(text, encoding="utf-8")
        written.append(name)

    portable_log = workspace / "work/AbuM53CoreBuild/final-security-test.log"
    ctest_log = workspace / "work/AbuM53CoreBuild/final-ctest.log"
    portable = re.search(r"PASS (\d+) checks", portable_log.read_text(encoding="utf-8-sig"))
    ctest = re.search(r"100% tests passed, 0 tests failed out of (\d+)", ctest_log.read_text(encoding="utf-8-sig"))
    if not portable or not ctest:
        raise ValueError("Portable logs do not contain successful completion")
    write("portable-core.json", {"schema": 1, "date": "2026-10-25", "passed": True,
          "configuration": "Windows Release portable core, zlib enabled", "assertion_checks": int(portable[1]),
          "ctest_tests_passed": int(ctest[1]), "ctest_tests_failed": 0,
          "source_reports": [{"path": str(portable_log.relative_to(workspace).as_posix()), "sha256": digest(portable_log)},
                             {"path": str(ctest_log.relative_to(workspace).as_posix()), "sha256": digest(ctest_log)}],
          "limitations": "Portable parser/math/renderer tests; no Unreal rendering or frame-rate claim."})

    automation_path = workspace / args.automation
    automation = read_json(automation_path)
    tests = []
    for test in automation["tests"]:
        if not test["fullTestPath"].startswith("AbuM53."):
            continue
        record = {"name": test["fullTestPath"], "state": test["state"], "duration_seconds": test["duration"],
                  "warnings": test["warnings"], "errors": test["errors"]}
        own_events = []
        for entry in test.get("entries", []):
            message = entry.get("event", {}).get("message", "")
            # Only the project's explicit numerical comparison summaries are retained.
            if message.startswith("Compared ") and re.fullmatch(r"[A-Za-z0-9 ,/.-]+", message):
                own_events.append(message)
        if own_events:
            record["numerical_checks"] = own_events
        tests.append(record)
    devices = [{key: device.get(key) for key in ("platform", "oSVersion", "gPU", "cPUModel", "rAMInGB", "renderMode", "rHI")}
               for device in automation.get("devices", [])]
    write(args.automation_output, {"schema": 1, "engine": "Unreal Engine 5.8.2",
          "reported_timestamp": automation["reportCreatedOn"], "tests_passed": sum(t["state"] == "Success" for t in tests),
          "tests_not_successful": sum(t["state"] != "Success" for t in tests), "tests": tests, "test_hardware": devices,
          "source_report": args.automation.replace("\\", "/"), "source_report_sha256": digest(automation_path),
          "sanitization": "Machine/instance names, identifiers, paths, artifacts and engine log text omitted.",
          "limitations": "Only listed AbuM53 tests on this hardware/configuration; not cross-vendor certification or benchmark FPS."})

    for filename in ("import-smoke.json", "spz-import-smoke.json", "backend-image-comparison.json"):
        source = saved / filename
        report = read_json(source)
        report["evidence_source"] = "work/AbuM53Host/Saved/AbuM53QA/" + filename
        report["evidence_source_sha256"] = digest(source)
        write(filename, report)
    shipping_path = workspace / "work/AbuM53_shipping_validation.json"
    if shipping_path.is_file():
        shipping = read_json(shipping_path)
        report = {key: shipping[key] for key in ("engine", "configuration", "platform", "result", "buildSeconds",
                  "executableSha256", "abuM53UhtModules", "editorModuleInLink", "unrealEdInLink", "cookedOrLaunched")}
        report.update({"schema": 1, "executable_filename": re.split(r"[/\\]", shipping["executable"])[-1],
                       "source_snapshot_difference_count": len(shipping["sourceSnapshotDifferences"]),
                       "source_report": "work/AbuM53_shipping_validation.json", "source_report_sha256": digest(shipping_path),
                       "scope": "Shipping compile/link results; cooked launch/render evidence is recorded separately in shipping-cook.json."})
        write("shipping-compile.json", report)
    cook_path = workspace / "work/AbuM53_shipping_cook_validation.json"
    if cook_path.is_file():
        report = read_json(cook_path)
        report["source_report"] = "work/AbuM53_shipping_cook_validation.json"
        report["source_report_sha256"] = digest(cook_path)
        write("shipping-cook.json", report)
    benchmark_path = workspace / "work/AbuM53Benchmark/final-results/benchmark.json"
    if benchmark_path.is_file():
        benchmark = read_json(benchmark_path)
        # Keep the owned measurements and settings; replace machine filesystem
        # locations by filenames. Raw engine CSV/log contents are not exported.
        omitted = {"project_log_directory", "unsaved_asset_path", "gpu_identity", "gpu_identity_evidence"}
        def sanitize(value):
            if isinstance(value, dict):
                return {key: sanitize(item) for key, item in value.items() if key not in omitted}
            if isinstance(value, list):
                return [sanitize(item) for item in value]
            if isinstance(value, str) and re.match(r"^[A-Za-z]:[\\/]", value):
                return re.split(r"[/\\]", value)[-1]
            return value
        report = sanitize(benchmark)
        identity_log = (workspace / "work/AbuM53_benchmark_final.log").read_text(encoding="utf-8-sig")
        gpu = re.search(r"LogRHI:\s+Name:\s+([^\r\n]+)", identity_log)
        driver = re.search(r"Driver Version:\s+(\S+)", identity_log)
        feature = re.search(r'rhifeaturelevel="([^"]+)"', identity_log)
        if not gpu or not driver or not feature:
            raise ValueError("Cannot establish GPU/driver/feature level from benchmark startup evidence")
        report.update({"source_report": "work/AbuM53Benchmark/final-results/benchmark.json",
                       "source_report_sha256": digest(benchmark_path),
                       "test_configuration": {"gpu": gpu[1].strip(), "feature_level": feature[1], "driver": driver[1],
                         "identity_evidence": "Locally inspected startup records in AbuM53_benchmark_final.log; raw engine log not redistributed"}})
        for stage, original in zip(report["stages"], benchmark["stages"]):
            stage["csv_sha256"] = digest(Path(original["csv_path"]))
            stage["screenshot_sha256"] = digest(Path(original["screenshot_path"]))
        write("synthetic-benchmark.json", report)
    print(json.dumps({"output": str(args.output.resolve()), "portable_checks": int(portable[1]),
                      "ue_tests": len(tests), "files_written": len(written)}, indent=2))


if __name__ == "__main__":
    main()
