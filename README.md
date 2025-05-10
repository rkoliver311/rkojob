# rkoJob

**rkoJob** is a lightweight framework for defining and running structured jobs, with a primary focus on CI/CD workflows.

🐣 This project is in the early stages of development. Contributions, feedback, and bug reports are welcome. 🌱

## Quick Start

### Installation

Until the project is published to PyPI, install it from source:

```bash
git clone https://github.com/rkoliver311/rkojob.git
cd rkojob
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

### Example

Here’s a minimal example of how to declare a job using the builder-style API:

```python
# build_test_deploy.py

from pathlib import Path

from rkojob import context_value
from rkojob.actions import ShellAction, ToolActionBuilder
from rkojob.coerce import as_bool
from rkojob.job import JobBuilder
from rkojob.values import ComputedValue

# Dynamic bindings for pip and cat
pip = ToolActionBuilder("pip")
cat = ToolActionBuilder("cat")

# Helper to determine whether a path exists
def path_exists(path: str) -> ComputedValue[bool]:
    return ComputedValue(lambda: Path(path).exists())

with JobBuilder("build-test-deploy") as job_builder:
    with job_builder.stage("setup") as setup_stage:
        with setup_stage.step("install-dependencies") as install_dependencies:
            install_dependencies.action = pip.install(requirement="requirements.txt")

    with job_builder.stage("build") as build_stage:
        with build_stage.step("build") as build:
            build.action = ShellAction("scripts/build.sh")

        with build_stage.step("log-errors") as log_errors:
            log_errors.action = cat("build/errors.log")
            log_errors.run_if = path_exists("build/errors.log")

    with job_builder.stage("test") as test_stage:
        with test_stage.step("test") as test:
            test.action = ShellAction("scripts/test.sh")

        with test_stage.step("log-errors") as log_errors:
            log_errors.action = cat("test/errors.log")
            log_errors.run_if = path_exists("test/errors.log")

    with job_builder.stage("deploy") as deploy_stage:
        with deploy_stage.step("deploy") as deploy:
            deploy.action = ShellAction("scripts/deploy.sh")
            deploy.skip_if = context_value("dry_run", as_bool)

job = job_builder.build()
```

To run the job:

```bash
rkojob run --job build_and_test.job --values dry_run=true
```

## Core Concepts

### `JobContext`

Provides contextual data during execution. Tracks the current state of the job and facilitates communication between actions and infrastructure (e.g., status reporting, values).

### `JobRunner`

The orchestrator that executes a `Job` instance. Responsible for walking the job structure and evaluating `run_if` / `skip_if` conditions.

### `Job`, `JobStage`, and `JobStep`

Concrete implementations of the `JobScope` protocol:

- **Job**: The top-level container for all stages.
- **JobStage**: A logical grouping of steps, typically representing a phase like "build" or "test".
- **JobStep**: The atomic unit of execution. Each step wraps an `action` and its execution logic.

### Actions

Actions are the core units of work and must implement the `JobCallable[None]` protocol. Built-in actions include:

- `ShellAction`: Run shell commands.
- `ToolActionBuilder`: Dynamically create parameterized shell actions (e.g., for common CLI tools).
- Custom actions can be defined to encapsulate reusable logic.

---

More documentation coming soon as the project evolves.
