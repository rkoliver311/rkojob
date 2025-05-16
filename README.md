# rkoJob

**rkoJob** is a lightweight framework for defining and running
structured jobs, with a primary focus on CI/CD workflows.

🐣 This project is in the early stages of development. Contributions,
feedback, and bug reports are welcome. 🌱

------------------------------------------------------------------------

## Quick Start

### Installation

Until the project is published to PyPI, install it from source:

``` bash
git clone https://github.com/rkoliver311/rkojob.git
cd rkojob
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

------------------------------------------------------------------------

### Example

Here's a minimal example of how to declare a job using the builder-style
API:

``` python
# build_test_deploy.py

from pathlib import Path

from rkojob import context_value
from rkojob.actions import ShellAction, ToolActionBuilder
from rkojob.coerce import as_bool
from rkojob.job import JobBuilder
from rkojob.values import ComputedValue

pip = ToolActionBuilder("pip")
cat = ToolActionBuilder("cat")

def path_exists(path: str) -> ComputedValue[bool]:
    return ComputedValue(lambda: Path(path).exists())

with JobBuilder("build-test-deploy") as job_builder:
    with job_builder.stage("setup") as setup:
        with setup.step("install-dependencies") as step:
            step.action = pip.install(requirement="requirements.txt")

    with job_builder.stage("build") as build:
        with build.step("build") as step:
            step.action = ShellAction("scripts/build.sh")

        with build.step("log-errors") as step:
            step.action = cat("build/errors.log")
            step.run_if = path_exists("build/errors.log")

    with job_builder.stage("test") as test:
        with test.step("start-test-server") as step:
            step.action = ShellAction("scripts/server.sh", "start")
            test.teardown += ShellAction("scripts/server.sh", "stop")

        with test.step("test") as step:
            step.action = ShellAction("scripts/test.sh")

        with test.step("log-errors") as step:
            step.action = cat("test/errors.log")
            step.run_if = path_exists("test/errors.log")

    with job_builder.stage("deploy") as deploy:
        with deploy.step("deploy") as step:
            step.action = ShellAction("scripts/deploy.sh")
            step.skip_if = context_value("dry_run", as_bool)

job = job_builder.build()
```

Run the job:

``` bash
rkojob run --job build_and_test.job --value dry_run=true
```

You can also load values from a YAML file using the `--values-from`
option:

``` yaml
dry_run: true
docker:
  tag: release
  registry: gcr.io
```

Nested values can be accessed using dot-delimited keys:

``` python
docker_tag = context_value("docker.tag")
docker_registry = context_value("docker.registry")
```

------------------------------------------------------------------------

## Core Concepts

### `JobContext`

Provides contextual data during execution. It tracks the current job
state and allows communication between steps and infrastructure (e.g.,
status reporting, shared values).

------------------------------------------------------------------------

### `JobRunner`

Orchestrates execution of a `Job` instance by walking its structure and
evaluating conditions like `run_if` and `skip_if`.

------------------------------------------------------------------------

### `Job`, `JobStage`, and `JobStep`

Concrete implementations of the `JobScope` protocol:

- **`Job`**: The top-level container for all stages.
- **`JobStage`**: A logical grouping of steps, typically representing
  phases like "build" or "test".
- **`JobStep`**: The atomic unit of execution. Each step wraps an
  `action` and associated logic.

------------------------------------------------------------------------

### Actions

Actions implement the `JobCallable[None]` protocol and define what
actually happens when a step runs.

Built-in actions include:

- `ShellAction`: Runs a shell command.
- `ToolActionBuilder`: Dynamically creates parameterized shell actions
  for common CLI tools.
- You can also define your own custom actions.

### Scope Teardown

Each scope can define one or more teardown actions to be executed just
before the scope exits. Teardown actions are useful for cleanup,
finalization, or diagnostics.

You can register teardown actions during job definition:

``` python
with job.stage("stage") as stage:
    ...
    stage.teardown += ShellAction("echo", "tearing down stage")
    stage.teardown += ShellAction("echo", "more tearing down")
```

Actions can also register teardown behavior dynamically at runtime using
the `JobContext`:

``` python
def some_action(context: JobContext) -> None:
    context.add_teardown(
        context.parent_scope(),
        ShellAction("echo", "teardown parent scope")
    )
```

**Execution order**:

Dynamically added teardown actions are executed first, in reverse order
of addition (LIFO). Statically defined teardown actions (added during
job definition) are executed after, in definition order (FIFO). This
ensures that resources acquired dynamically can be reliably cleaned up
before general teardown steps.

------------------------------------------------------------------------

### Conditional Scopes

Any scope conforming to `JobConditionalScope` (e.g., `JobStep`) can be
conditionally run or skipped by setting `run_if` or `skip_if`. These
fields accept a flexible `JobConditionalType`, including:

``` python
# Static boolean
step.run_if = False

# Boolean with explanation
step.skip_if = True, "Step disabled"

# Context-aware callable
step.run_if = lambda context: len(context.get_errors()) != 0
```

Built-in condition helpers:

- `job_always`: Always returns `True`
- `job_never`: Always returns `False`
- `job_failing`: Returns `True` if the job has any recorded errors
- `job_succeeding`: Returns `True` if the job has no errors
- `scope_failing(scope)`: True if the given scope has any errors
- `scope_succeeding(scope)`: True if the given scope has no errors

**Example:**

``` python
with JobBuilder("job") as job_builder:
    with job_builder.stage("stage") as stage:
        with stage.step("step") as step:
            step.run_if = scope_failing(stage)
```

#### `run_if` vs `skip_if`

Both `run_if` and `skip_if` control whether a scope will be executed,
but they serve slightly different purposes:

`run_if` determines if a scope is **eligible to run at all**.

`skip_if` determines if a scope that *could* run should be **explicitly
skipped**.

If both are set:

- The scope must pass `run_if`
- Then, it must not be blocked by `skip_if`

------------------------------------------------------------------------

More documentation coming soon as the project evolves.
