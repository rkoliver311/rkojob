# Dog-fooding: A set of custom lint checks using rkojob

from rkojob.actions import VerifyTestStructure
from rkojob.job import (
    Job,
    JobStage,
    JobStep,
    deferred_init,
)
from rkojob.values import ValueKey

job = Job(
    "custom-checks",
    stages=[
        JobStage(
            "verify-test-structure",
            steps=[
                JobStep(
                    "verify-test-structure",
                    action=deferred_init(
                        VerifyTestStructure,
                        src_path=ValueKey("src_path"),
                        tests_path=ValueKey("tests_path"),
                        errors=ValueKey("errors"),
                    ),
                )
            ],
        ),
    ],
)
