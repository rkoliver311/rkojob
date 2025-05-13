# Dog-fooding: verify-change job
from rkojob import context_value, lazy_format
from rkojob.actions import VerifyTestStructure, ToolActionBuilder
from rkojob.job import (
    lazy_action, JobBuilder,
)

tox = ToolActionBuilder("tox")

with JobBuilder("verify-change") as job:

    with job.stage("setup") as setup:
        pass

    with job.stage("static-analysis") as static_analysis:
        # Use explicit name for verify_test_structure so it can be run separately
        with static_analysis.step("verify-test-structure") as verify_test_structure:
            verify_test_structure.action = lazy_action(
                VerifyTestStructure,
                src_path=context_value("src_path"),
                tests_path=context_value("tests_path"),
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
