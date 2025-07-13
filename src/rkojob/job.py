# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
from enum import Enum, auto
from typing import Any, Generator, Generic, TypeVar

from rkojob import (
    Delegate,
    JobCallable,
    JobConditionalType,
    JobContext,
    JobIdType,
    JobScopeID,
    JobScopeType,
    create_scope_id,
    delegate,
)


class JobScopes(Enum):
    """Concrete implementation of JobScopeType"""

    STEP = auto()
    STAGE = auto()
    GROUP = auto()
    JOB = auto()

    def __str__(self) -> str:
        return self.name.capitalize()


class JobScopeIDMixin(JobScopeID):
    _id: JobIdType

    @property
    def id(self) -> JobIdType:
        return self._id

    def __eq__(self, other: object) -> bool:
        if isinstance(other, JobScopeID):
            return self.id == other.id
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.id)


A = TypeVar("A", bound=JobCallable[None])


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
        concurrent: bool = False,
        id: JobIdType | None = None,
    ) -> None:
        self._name: str = name

        self._action: A | None = None
        self._run_if: JobConditionalType | None = run_if
        self._skip_if: JobConditionalType | None = skip_if
        self._concurrent: bool = concurrent
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
    def concurrent(self) -> bool:
        return self._concurrent

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


class JobGroup(JobScopeIDMixin):
    """
    Class that allows steps and stages to be grouped together.
    """

    def __init__(
        self,
        name: str,
        scopes: list[JobGroup | JobStage | JobStep[Any]] | None = None,
        run_if: JobConditionalType | None = None,
        skip_if: JobConditionalType | None = None,
        concurrent: bool = False,
        id: JobIdType | None = None,
    ):
        self._name: str = name
        if scopes is None:
            scopes = []
        self._scopes: list[JobGroup | JobStage | JobStep[Any]] = scopes
        self._run_if: JobConditionalType | None = run_if
        self._skip_if: JobConditionalType | None = skip_if
        self._concurrent: bool = concurrent
        self._id: JobIdType = id or create_scope_id()

    @property
    def name(self) -> str:
        return self._name

    @property
    def type(self) -> JobScopeType:
        return JobScopes.GROUP

    @property
    def concurrent(self) -> bool:
        return self._concurrent

    @property
    def scopes(self) -> list[JobGroup | JobStage | JobStep[Any]]:
        return self._scopes

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


class JobStage(JobGroup):
    """
    Class representing a job stage that consists of one or more groups and steps.
    """

    def __init__(
        self,
        name: str,
        scopes: list[JobGroup | JobStep[Any]] | None = None,
        concurrent: bool = False,
        id: JobIdType | None = None,
    ) -> None:
        super().__init__(name, scopes, concurrent=concurrent, id=id)

    @property
    def type(self) -> JobScopeType:
        return JobScopes.STAGE


class Job(JobGroup):
    """
    Class representing a job that consists of one or more stages.
    """

    def __init__(
        self, name: str, scopes: list[JobGroup | JobStage | JobStep[Any]] | None = None, id: JobIdType | None = None
    ) -> None:
        super().__init__(name, scopes, concurrent=False, id=id)

    @property
    def type(self) -> JobScopeType:
        return JobScopes.JOB


class JobStepBuilder(AbstractContextManager, JobScopeIDMixin):
    def __init__(self, name: str, concurrent: bool = False) -> None:
        self._name: str = name

        self.builds_type: JobScopeType = JobScopes.STEP
        self._id: JobIdType = create_scope_id()

        self.action: JobCallable[None] | None = None
        self.teardown: Delegate[[JobContext], None] = Delegate(continue_on_error=True)
        self.run_if: JobConditionalType | None = None
        self.skip_if: JobConditionalType | None = None
        self.concurrent: bool = concurrent

    def __exit__(self, exc_type, exc_value, traceback, /):
        pass

    def build(self) -> JobStep:
        step: JobStep = JobStep(
            name=self._name,
            action=self.action,
            run_if=self.run_if,
            skip_if=self.skip_if,
            id=self._id,
            concurrent=self.concurrent,
        )
        step.teardown += self.teardown
        return step

    def __str__(self) -> str:
        return f"{self.builds_type} {self._name}"


class JobStageGroupBuilder(AbstractContextManager, JobScopeIDMixin):
    def __init__(self, name: str, concurrent: bool = False) -> None:
        self._name: str = name

        self.builds_type: JobScopeType = JobScopes.GROUP
        self._id: JobIdType = create_scope_id()

        self._scopes: list[JobGroup | JobStage | JobStep[Any]] = []
        self.teardown: Delegate[[JobContext], None] = Delegate(continue_on_error=True)
        self.run_if: JobConditionalType | None = None
        self.skip_if: JobConditionalType | None = None
        self.concurrent: bool = concurrent

    def __exit__(self, exc_type, exc_value, traceback, /):
        pass

    @contextmanager
    def group(self, name: str, concurrent: bool = False) -> Generator[JobStageGroupBuilder, None, None]:
        builder: JobStageGroupBuilder = JobStageGroupBuilder(name, concurrent=concurrent)
        yield builder
        self.add_scope(builder.build())

    @contextmanager
    def step(self, name: str, concurrent: bool = False) -> Generator[JobStepBuilder, None, None]:
        builder: JobStepBuilder = JobStepBuilder(name, concurrent=concurrent)
        yield builder
        self.add_scope(builder.build())

    def add_scope(self, scope: JobGroup | JobStage | JobStep[Any]) -> None:
        self._scopes.append(scope)

    def build(self) -> JobGroup:
        group: JobGroup = JobGroup(
            name=self._name,
            scopes=self._scopes,
            run_if=self.run_if,
            skip_if=self.skip_if,
            concurrent=self.concurrent,
            id=self._id,
        )
        group.teardown += self.teardown
        return group

    def __str__(self) -> str:
        return f"{self.builds_type} {self._name}"


class JobGroupBuilder(AbstractContextManager, JobScopeIDMixin):
    def __init__(self, name: str, concurrent: bool = False) -> None:
        self._name: str = name

        self.builds_type: JobScopeType = JobScopes.GROUP
        self._id: JobIdType = create_scope_id()

        self._scopes: list[JobGroup | JobStage | JobStep[Any]] = []
        self.teardown: Delegate[[JobContext], None] = Delegate(continue_on_error=True)
        self.run_if: JobConditionalType | None = None
        self.skip_if: JobConditionalType | None = None
        self.concurrent: bool = concurrent

    def __exit__(self, exc_type, exc_value, traceback, /):
        pass

    @contextmanager
    def group(self, name: str, concurrent: bool = False) -> Generator[JobGroupBuilder, None, None]:
        builder: JobGroupBuilder = JobGroupBuilder(name, concurrent=concurrent)
        yield builder
        self.add_scope(builder.build())

    @contextmanager
    def stage(self, name: str, concurrent: bool = False) -> Generator[JobStageBuilder, None, None]:
        builder: JobStageBuilder = JobStageBuilder(name, concurrent=concurrent)
        yield builder
        self.add_scope(builder.build())

    @contextmanager
    def step(self, name: str, concurrent: bool = False) -> Generator[JobStepBuilder, None, None]:
        builder: JobStepBuilder = JobStepBuilder(name, concurrent=concurrent)
        yield builder
        self.add_scope(builder.build())

    def add_scope(self, scope: JobGroup | JobStage | JobStep[Any]) -> None:
        self._scopes.append(scope)

    def build(self) -> JobGroup:
        group: JobGroup = JobGroup(
            name=self._name,
            scopes=self._scopes,
            run_if=self.run_if,
            skip_if=self.skip_if,
            concurrent=self.concurrent,
            id=self._id,
        )
        group.teardown += self.teardown
        return group

    def __str__(self) -> str:
        return f"{self.builds_type} {self._name}"


class JobStageBuilder(JobScopeIDMixin, AbstractContextManager):
    def __init__(self, name: str, concurrent: bool = False) -> None:
        self._name: str = name

        self.builds_type: JobScopeType = JobScopes.STAGE
        self._id: JobIdType = create_scope_id()

        self._scopes: list[JobGroup | JobStep[Any]] = []
        self.teardown: Delegate[[JobContext], None] = Delegate(continue_on_error=True)
        self.concurrent: bool = concurrent

    def __exit__(self, exc_type, exc_value, traceback, /):
        pass

    @contextmanager
    def group(self, name: str, concurrent: bool = False) -> Generator[JobStageGroupBuilder, None, None]:
        builder: JobStageGroupBuilder = JobStageGroupBuilder(name, concurrent=concurrent)
        yield builder
        self.add_scope(builder.build())

    @contextmanager
    def step(self, name: str, concurrent: bool = False) -> Generator[JobStepBuilder, None, None]:
        builder: JobStepBuilder = JobStepBuilder(name, concurrent=concurrent)
        yield builder
        self.add_scope(builder.build())

    def add_scope(self, scope: JobGroup | JobStep[Any]) -> None:
        self._scopes.append(scope)

    def build(self) -> JobStage:
        stage: JobStage = JobStage(name=self._name, scopes=self._scopes, concurrent=self.concurrent, id=self._id)
        stage.teardown += self.teardown
        return stage

    def __str__(self) -> str:
        return f"{self.builds_type} {self._name}"


class JobBuilder(JobScopeIDMixin, AbstractContextManager):
    def __init__(self, name: str) -> None:
        self._name: str = name
        self._scopes: list[JobStage | JobGroup | JobStep[Any]] = []
        self.teardown: Delegate[[JobContext], None] = Delegate(continue_on_error=True)
        self._id: JobIdType = create_scope_id()
        self.builds_type: JobScopeType = JobScopes.JOB

    def __exit__(self, exc_type, exc_value, traceback, /):
        pass

    @contextmanager
    def group(self, name: str, concurrent: bool = False) -> Generator[JobGroupBuilder, None, None]:
        builder: JobGroupBuilder = JobGroupBuilder(name, concurrent=concurrent)
        yield builder
        self.add_scope(builder.build())

    @contextmanager
    def stage(self, name: str, concurrent: bool = False) -> Generator[JobStageBuilder, None, None]:
        builder: JobStageBuilder = JobStageBuilder(name, concurrent=concurrent)
        yield builder
        self.add_scope(builder.build())

    @contextmanager
    def step(self, name: str, concurrent: bool = False) -> Generator[JobStepBuilder, None, None]:
        builder: JobStepBuilder = JobStepBuilder(name, concurrent=concurrent)
        yield builder
        self.add_scope(builder.build())

    def add_scope(self, scope: JobStage | JobGroup | JobStep[Any]) -> None:
        self._scopes.append(scope)

    def build(self) -> Job:
        job: Job = Job(name=self._name, scopes=self._scopes, id=self._id)
        job.teardown += self.teardown
        return job

    def __str__(self) -> str:
        return f"{self.builds_type} {self._name}"
