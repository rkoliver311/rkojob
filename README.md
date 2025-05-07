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
    from rkojob.actions import ShellAction
    from rkojob.factories import JobContextFactory, JobRunnerFactory
    from rkojob.job import JobBuilder
    from rkojob.values import ComputedValue, ValueKey
    
    with JobBuilder("build-test-deploy") as job_builder:
    
        with job_builder.stage("setup") as setup_stage:
    
            with setup_stage.step("install-dependencies") as install_dependencies:
                install_dependencies.action = ShellAction("pip", "install" "-r", "requirements.txt")
    
        with job_builder.stage("build") as build_stage:
    
            with build_stage.step("build") as build:
                build.action=ShellAction("scripts/build.sh")
    
            with build_stage.step("log-errors") as log_errors:
                log_errors.action = ShellAction("cat", "build/errors.log"),
                log_errors.run_if = ComputedValue(lambda: Path("build/errors.log").exists())
    
        with job_builder.stage("test") as test_stage:
            
            with test_stage.step("test") as test:
                test.action = ShellAction("scripts/test.sh")
    
            with test_stage.step("log-errors") as log_errors:
                log_errors.action = ShellAction("cat", "test/errors.log"),
                log_errors.run_if = ComputedValue(lambda: Path("test/errors.log").exists())
    
        with job_builder.stage("deploy") as deploy_stage:
            
            with deploy_stage.step("deploy") as deploy:
                deploy.action = ShellAction("scripts/deploy.sh")
                deploy.skip_if = ValueKey("dry_run")
    
    job = job_builder.build()
    
    # Run the job
    runner = JobRunnerFactory.create()
    context = JobContextFactory.create(values=dict(dry_run=True))
    
    runner.run(context, job)


## Core Classes

### JobContext

The execution context for the job. The context maintains state and enables monitoring the status of the job.

### JobRunner

The Job runner orchestrates the execution of the job.

### Job, JobStage, and JobStep

Primary concrete implementations of the `JobScope` protocol.

### Actions

The actual work of a job is performed by actions. The simplest action is a function that takes a `JobContext` parameter.
