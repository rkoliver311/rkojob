# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
from enum import Enum, auto
from typing import Generator, Generic, TypeVar

from rkojob import (
    Delegate,
    JobCallable,
    JobConditionalType,
    JobContext,
    JobScopeID,
    JobScopeType,
    create_scope_id,
    delegate,
)


class JobScopes(Enum):
    """Concrete implementation of JobScopeType"""

    STEP = auto()
    STAGE = auto()
    JOB = auto()

    def __str__(self) -> str:
        return self.name.capitalize()


A = TypeVar("A", bound=JobCallable[None])


class JobScopeIDMixin(JobScopeID):
    _id: str

    @property
    def id(self) -> str:
        return self._id

    def __eq__(self, other: object) -> bool:
        if isinstance(other, JobScopeID):
            return self.id == other.id
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.id)


class JobStep(JobScopeIDMixin, Generic[A]):
    """
    Class representing a job step.
    """

    def __init__(
        self,
        name: str,
        action: A | None = None,
        run_if: JobConditionalType | None = None,
        skip_if: JobConditionalType | None = None,
        id: str | None = None,
    ) -> None:
        self._name: str = name

        self._action: A | None = None
        self._run_if: JobConditionalType | None = run_if
        self._skip_if: JobConditionalType | None = skip_if
        self._id = id or create_scope_id()

        if action:
            self.action = action

    @property
    def name(self) -> str:
        return self._name

    @property
    def type(self) -> JobScopeType:
        return JobScopes.STEP

    @property
    def action(self) -> A | None:
        return self._action

    @action.setter
    def action(self, action: A | None) -> None:
        self._action = action

    @delegate(continue_on_error=True)
    def teardown(self, context: JobContext) -> None: ...

    @property
    def run_if(self) -> JobConditionalType | None:
        return self._run_if

    @run_if.setter
    def run_if(self, value: JobConditionalType | None) -> None:
        self._run_if = value

    @property
    def skip_if(self) -> JobConditionalType | None:
        return self._skip_if

    @skip_if.setter
    def skip_if(self, value: JobConditionalType | None) -> None:
        self._skip_if = value

    def __str__(self) -> str:
        return f"{self.type} {self.name}"


class JobStage(JobScopeIDMixin):
    """
    Class representing a job stage that consists of one or more steps.
    """

    def __init__(self, name: str, steps: list[JobStep] | None = None, id: str | None = None) -> None:
        self._name: str = name
        if steps is None:
            steps = []
        self.steps: list[JobStep] = steps
        self._id: str = id or create_scope_id()

    @property
    def name(self) -> str:
        return self._name

    @property
    def type(self) -> JobScopeType:
        return JobScopes.STAGE

    @property
    def scopes(self) -> list[JobStep]:
        return self.steps

    @delegate(continue_on_error=True)
    def teardown(self, context: JobContext) -> None: ...

    def __str__(self) -> str:
        return f"{self.type} {self.name}"


class Job(JobScopeIDMixin):
    """
    Class representing a job that consists of one or more stages.
    """

    def __init__(self, name: str, stages: list[JobStage] | None = None, id: str | None = None) -> None:
        self._name: str = name
        if stages is None:
            stages = []
        self.stages: list[JobStage] = stages
        self._id: str = id or create_scope_id()

    @property
    def name(self) -> str:
        return self._name

    @property
    def type(self) -> JobScopeType:
        return JobScopes.JOB

    @property
    def scopes(self) -> list[JobStage]:
        return self.stages

    @delegate(continue_on_error=True)
    def teardown(self, context: JobContext) -> None: ...

    def __str__(self) -> str:
        return f"{self.type} {self.name}"


class JobStepBuilder(JobScopeIDMixin):
    def __init__(self, name: str) -> None:
        self._name: str = name
        self.action: JobCallable[None] | None = None
        self.teardown: Delegate[[JobContext], None] = Delegate(continue_on_error=True)
        self.run_if: JobConditionalType | None = None
        self.skip_if: JobConditionalType | None = None
        self._id: str = create_scope_id()
        self.builds_type: JobScopeType = JobScopes.STEP

    def build(self) -> JobStep:
        step: JobStep = JobStep(
            name=self._name,
            action=self.action,
            run_if=self.run_if,
            skip_if=self.skip_if,
            id=self._id,
        )
        step.teardown += self.teardown
        return step

    def __str__(self) -> str:
        return f"{self.builds_type} {self._name}"


class JobStageBuilder(JobScopeIDMixin):
    def __init__(self, name: str) -> None:
        self._name: str = name
        self._steps: list[JobStep] = []
        self.teardown: Delegate[[JobContext], None] = Delegate(continue_on_error=True)
        self._id: str = create_scope_id()
        self.builds_type: JobScopeType = JobScopes.STAGE

    @contextmanager
    def step(self, name: str) -> Generator[JobStepBuilder, None, None]:
        builder: JobStepBuilder = JobStepBuilder(name)
        yield builder
        self._steps.append(builder.build())

    def build(self) -> JobStage:
        stage: JobStage = JobStage(name=self._name, steps=self._steps, id=self._id)
        stage.teardown += self.teardown
        return stage

    def __str__(self) -> str:
        return f"{self.builds_type} {self._name}"


class JobBuilder(JobScopeIDMixin, AbstractContextManager):
    def __init__(self, name: str) -> None:
        self._name: str = name
        self._stages: list[JobStage] = []
        self.teardown: Delegate[[JobContext], None] = Delegate(continue_on_error=True)
        self._id: str = create_scope_id()
        self.builds_type: JobScopeType = JobScopes.JOB

    def __exit__(self, exc_type, exc_value, traceback, /):
        pass

    @contextmanager
    def stage(self, name: str) -> Generator[JobStageBuilder, None, None]:
        builder: JobStageBuilder = JobStageBuilder(name)
        yield builder
        self._stages.append(builder.build())

    def build(self) -> Job:
        job: Job = Job(name=self._name, stages=self._stages, id=self._id)
        job.teardown += self.teardown
        return job

    def __str__(self) -> str:
        return f"{self.builds_type} {self._name}"
