# rkojob

rkoJob is a set of tools for running structured jobs with a focus on CI/CD.

🐣 This project is in the early stages of development. 🌱

## Quick Start

### Installation

    # Until we publish to PyPI, install from source
    $ git clone https://github.com/rkoliver311/rkojob.git
    $ cd rkojob
    $ python -m venv .venv && source .venv/bin/activate
    $ pip install -e .

### Job Declaration (Builder API)

`build_test_deploy.py`:

    from pathlib import Path
    
    from rkojob import context_value
    from rkojob.actions import ShellAction, ToolActionBuilder
    from rkojob.coerce import as_bool
    from rkojob.job import JobBuilder
    from rkojob.values import ComputedValue
    
    # Dynamic bindings for pip and cat
    pip = ToolActionBuilder("pip")
    cat = ToolActionBuilder("cat")
    
    
    # Helper function to check whether a file exists
    def path_exists(path: str) -> ComputedValue[bool]: return ComputedValue(lambda: Path(path).exists())
    
    
    with JobBuilder("build-test-deploy") as job_builder:
        with job_builder.stage("setup") as setup_stage:
            with setup_stage.step("install-dependencies") as install_dependencies:
                install_dependencies.action = pip.install(requirement="requirements.txt")
    
        with job_builder.stage("build") as build_stage:
            with build_stage.step("build") as build:
                build.action = ShellAction("scripts/build.sh")
    
            with build_stage.step("log-errors") as log_errors:
                log_errors.action = cat("build/errors.log"),
                log_errors.run_if = path_exists("build/errors.log")
    
        with job_builder.stage("test") as test_stage:
            with test_stage.step("test") as test:
                test.action = ShellAction("scripts/test.sh")
    
            with test_stage.step("log-errors") as log_errors:
                log_errors.action = cat("test/errors.log"),
                log_errors.run_if = path_exists("test/errors.log")
    
        with job_builder.stage("deploy") as deploy_stage:
            with deploy_stage.step("deploy") as deploy:
                deploy.action = ShellAction("scripts/deploy.sh")
                deploy.skip_if = context_value("dry_run", as_bool)
    
    job = job_builder.build()


Running the job:

    $ rkojob --job-module build_and_test --job-name job --values dry_run=true

## Core Classes

### JobContext

The execution context for the job. The context maintains state and enables monitoring the status of the job.

### JobRunner

The Job runner orchestrates the execution of the job.

### Job, JobStage, and JobStep

Concrete implementations of the `JobScope` protocol.

### Actions

Actions are what perform the actual work of the job. Actions can be any object that implements the `JobCallable[None]` protocol.  
