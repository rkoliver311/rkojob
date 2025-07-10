# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.
import shutil
from pathlib import Path

# Dog-fooding: verify-change job
from rkojob import context_value, lazy_action, lazy_format, JobContext
from rkojob.actions import ShellActionBuilder, VerifyPythonTestStructure
from rkojob.job import JobBuilder

pip = ShellActionBuilder("pip")
tox = ShellActionBuilder("tox")

with JobBuilder("verify-change") as job:

    with job.stage("setup") as setup:
        with setup.step("clean") as clean:
            def clean_action(context: JobContext) -> None:
                to_be_deleted: list[Path] = [Path(path) for path in (".tox", "build", "dist")]
                to_be_deleted.extend(Path().glob("**/*.egg-info"))
                for to_delete in to_be_deleted:
                    context.events.start_item(f"Deleting {to_delete}")
                    if to_delete.is_dir():
                        shutil.rmtree(to_delete)
                        outcome = "\u2705"
                    elif to_delete.is_file():
                        to_delete.unlink()
                        outcome = "\u2705"
                    elif not to_delete.exists():
                        outcome = "\u274E"
                    else:
                        outcome = "\uFE0F"
                    context.events.finish_item(outcome)
            clean.action = clean_action

        with setup.step("install-tox") as install_tox:
            install_tox.action = pip.install("tox")

    with job.stage("static-analysis") as static_analysis:
        static_analysis.concurrent = True
        # Use explicit name for verify_test_structure so it can be run separately
        with static_analysis.step("verify-test-structure") as verify_test_structure:
            verify_test_structure.action = lazy_action(
                VerifyPythonTestStructure,
                source_root=context_value("source_root"),
                test_root=context_value("test_root"),
                errors=context_value("errors", default=[]),
            )

        with static_analysis.step("tox-lint") as step:
            step.action = tox.run(e="lint")

        with static_analysis.step("tox-type") as step:
            step.action = tox.run(e="type")

    with job.stage("test") as test:

        with test.step("test") as step:
            py_env = lazy_format("py{python_version}")
            step.action = tox.run(e=py_env)

verify_change = job.build()

# Replace reference with built step
verify_test_structure = verify_test_structure.build()
