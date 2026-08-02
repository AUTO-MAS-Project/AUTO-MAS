from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProjectFixtureSpec:
    name: str
    resource_name: str
    layout: str
    config_location: str
    tasks: tuple[str, ...]
    with_default_json: bool = True
    config_folder: str = "configs"


@dataclass(frozen=True, slots=True)
class ProjectFixture:
    root: Path
    working_dir: Path
    config_source: Path
    config_dir: Path


PROJECT_FIXTURE_SPECS = (
    ProjectFixtureSpec(
        "okef-source",
        "ok-ef",
        "source",
        "src/config.py",
        ("DailyTask", "BattleTask"),
    ),
    ProjectFixtureSpec(
        "okef-installed",
        "ok-ef",
        "installed",
        "src/config.py",
        ("DailyTask", "BattleTask"),
    ),
    ProjectFixtureSpec(
        "okww-source",
        "ok-ww",
        "source",
        "config.py",
        ("DailyTask", "FarmEchoTask"),
    ),
    ProjectFixtureSpec(
        "okww-installed",
        "ok-ww",
        "installed",
        "config.py",
        ("DailyTask", "FarmEchoTask"),
    ),
    ProjectFixtureSpec(
        "oknte-source",
        "ok-nte",
        "source",
        "src/config.py",
        ("LauncherTask", "DailyTask"),
    ),
    ProjectFixtureSpec(
        "oknte-installed",
        "ok-nte",
        "installed",
        "src/config.py",
        ("LauncherTask", "DailyTask"),
    ),
    ProjectFixtureSpec(
        "okgf2-source",
        "ok-gf2",
        "source",
        "src/config.py",
        (
            "DailyTask",
            "ShopTask",
            "ArenaTask",
            "BattleTask",
            "EventTask",
            "DiagnosisTask",
        ),
        with_default_json=False,
    ),
    ProjectFixtureSpec(
        "okgf2-installed",
        "ok-gf2",
        "installed",
        "src/config.py",
        (
            "DailyTask",
            "ShopTask",
            "ArenaTask",
            "BattleTask",
            "EventTask",
            "DiagnosisTask",
        ),
        with_default_json=False,
    ),
    ProjectFixtureSpec(
        "okdna-source",
        "ok-dna",
        "source",
        "src/config.py",
        ("DailyTask", "DiagnosisTask"),
    ),
    ProjectFixtureSpec(
        "okdna-installed",
        "ok-dna",
        "installed",
        "src/config.py",
        ("DailyTask", "DiagnosisTask"),
    ),
)


def build_project_fixture(base_dir: Path, spec: ProjectFixtureSpec) -> ProjectFixture:
    root = base_dir / spec.name / spec.resource_name
    root.mkdir(parents=True)

    if spec.layout == "source":
        (root / "pyappify.yml").write_text(
            f"name: {spec.resource_name}\nversion: 1.0.0\n",
            encoding="utf-8",
        )
        runtime_root = root
    elif spec.layout == "installed":
        app_root = root / "data" / "apps" / spec.resource_name
        app_root.mkdir(parents=True)
        (app_root / "app.json").write_text(
            json.dumps(
                {
                    "name": spec.resource_name,
                    "displayName": spec.resource_name,
                    "version": "1.0.0",
                }
            ),
            encoding="utf-8",
        )
        runtime_root = app_root / "working"
    else:
        raise ValueError(f"Unknown project fixture layout: {spec.layout}")

    config_source = runtime_root / spec.config_location
    config_source.parent.mkdir(parents=True, exist_ok=True)
    task_rows = ",\n".join(
        f"        ('fixture.tasks', '{task_name}')" for task_name in spec.tasks
    )
    config_source.write_text(
        "version = '1.0.0'\n"
        "config = {\n"
        f"    'config_folder': '{spec.config_folder}',\n"
        f"    'gui_title': '{spec.resource_name} fixture',\n"
        f"    'log_file': 'logs/{spec.resource_name}.log',\n"
        "    'onetime_tasks': [\n"
        f"{task_rows}\n"
        "    ],\n"
        "}\n"
        "raise RuntimeError('fixture config.py must not be executed')\n",
        encoding="utf-8",
    )

    config_dir = runtime_root / spec.config_folder
    if spec.with_default_json:
        config_dir.mkdir(parents=True)
        (config_dir / "DailyTask.json").write_text(
            json.dumps({"enabled": True}),
            encoding="utf-8",
        )

    return ProjectFixture(
        root=root,
        working_dir=runtime_root,
        config_source=config_source,
        config_dir=config_dir,
    )
