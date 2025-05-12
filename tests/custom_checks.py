# Dog-fooding: A set of custom lint checks using rkojob
from rkojob import context_value
from rkojob.actions import VerifyTestStructure
from rkojob.job import (
    Job,
    JobStage,
    JobStep,
    lazy_action,
)

job = Job(
    "custom-checks",
    stages=[
        JobStage(
            "verify-test-structure",
            steps=[
                JobStep(
                    "verify-test-structure",
                    action=lazy_action(
                        VerifyTestStructure,
                        src_path=context_value("src_path"),
                        tests_path=context_value("tests_path"),
                        errors=context_value("errors", default=[]),
                    ),
                )
            ],
        ),
    ],
)
