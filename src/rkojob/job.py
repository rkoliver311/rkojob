# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager, contextmanager
from enum import Enum, auto
from pathlib import Path
from typing import Any, Generator, Generic, TypeVar

from rkojob import (
    Delegate,
    JobCallable,
    JobConditionalType,
    JobContext,
    JobIdType,
    JobScopeID,
    JobScopeType,
    ValueKey,
    Values,
    create_scope_id,
    delegate,
    job_workspace,
)
from rkojob.values import ValueOrRef


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
        values: Values | None = None,
    ) -> None:
        self._name: str = name

        self._action: A | None = None
        self._run_if: JobConditionalType | None = run_if
        self._skip_if: JobConditionalType | None = skip_if
        self._concurrent: bool = concurrent
        self._id: str = id or create_scope_id()
        self._values: Values = values or Values()

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

    @property
    def values(self) -> Values:
        return self._values

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
        values: Values | None = None,
    ):
        self._name: str = name
        if scopes is None:
            scopes = []
        self._scopes: list[JobGroup | JobStage | JobStep[Any]] = scopes
        self._run_if: JobConditionalType | None = run_if
        self._skip_if: JobConditionalType | None = skip_if
        self._concurrent: bool = concurrent
        self._id: JobIdType = id or create_scope_id()
        self._values: Values = values or Values()

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

    @property
    def values(self) -> Values:
        return self._values

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
        values: Values | None = None,
    ) -> None:
        super().__init__(name, scopes, concurrent=concurrent, id=id, values=values)

    @property
    def type(self) -> JobScopeType:
        return JobScopes.STAGE


class Job(JobGroup):
    """
    Class representing a job that consists of one or more stages.
    """

    def __init__(
        self,
        name: str,
        scopes: list[JobGroup | JobStage | JobStep[Any]] | None = None,
        id: JobIdType | None = None,
        values: Values | None = None,
    ) -> None:
        super().__init__(name, scopes, concurrent=False, id=id, values=values)

    @property
    def type(self) -> JobScopeType:
        return JobScopes.JOB


T_co = TypeVar("T_co", covariant=True)
T = TypeVar("T")


class JobBuilderBase(AbstractContextManager, JobScopeIDMixin, ABC, Generic[T_co]):
    def __init__(self, name: str, builds_type: JobScopeType, workspace: ValueOrRef[Path | str] | None = None) -> None:
        self._name: str = name
        self.builds_type: JobScopeType = builds_type
        self._id: JobIdType = create_scope_id()

        self.teardown: Delegate[[JobContext], None] = Delegate(continue_on_error=True)
        self.values: Values = Values()
        if workspace is not None:
            self.set_value(job_workspace, workspace)

    def set_value(self, key: ValueKey[T] | str, value: ValueOrRef[T]) -> None:
        self.values.set(key, value)

    def __exit__(self, exc_type, exc_value, traceback, /):
        pass

    @abstractmethod
    def build(self) -> T_co:  # pragma: no cover
        pass

    def __str__(self) -> str:
        return f"{self.builds_type} {self._name}"


class JobStepBuilder(JobBuilderBase[JobStep]):
    def __init__(self, name: str, concurrent: bool = False, workspace: ValueOrRef[Path | str] | None = None) -> None:
        super().__init__(name, JobScopes.STEP, workspace=workspace)

        self.action: JobCallable[None] | None = None
        self.run_if: JobConditionalType | None = None
        self.skip_if: JobConditionalType | None = None
        self.concurrent: bool = concurrent

    def build(self) -> JobStep:
        step: JobStep = JobStep(
            name=self._name,
            action=self.action,
            run_if=self.run_if,
            skip_if=self.skip_if,
            id=self._id,
            concurrent=self.concurrent,
            values=self.values,
        )
        step.teardown += self.teardown
        return step


class JobStageGroupBuilder(JobBuilderBase[JobGroup]):
    def __init__(self, name: str, concurrent: bool = False, workspace: ValueOrRef[Path | str] | None = None) -> None:
        super().__init__(name, JobScopes.GROUP, workspace=workspace)

        self._scopes: list[JobGroup | JobStage | JobStep[Any]] = []
        self.run_if: JobConditionalType | None = None
        self.skip_if: JobConditionalType | None = None
        self.concurrent: bool = concurrent

    @contextmanager
    def group(
        self, name: str, concurrent: bool = False, workspace: ValueOrRef[Path | str] | None = None
    ) -> Generator[JobStageGroupBuilder, None, None]:
        builder: JobStageGroupBuilder = JobStageGroupBuilder(name, concurrent=concurrent, workspace=workspace)
        yield builder
        self.add_scope(builder.build())

    @contextmanager
    def step(
        self, name: str, concurrent: bool = False, workspace: ValueOrRef[Path | str] | None = None
    ) -> Generator[JobStepBuilder, None, None]:
        builder: JobStepBuilder = JobStepBuilder(name, concurrent=concurrent, workspace=workspace)
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
            values=self.values,
        )
        group.teardown += self.teardown
        return group


class JobGroupBuilder(JobBuilderBase[JobGroup]):
    def __init__(self, name: str, concurrent: bool = False, workspace: ValueOrRef[Path | str] | None = None) -> None:
        super().__init__(name, JobScopes.GROUP, workspace=workspace)

        self._scopes: list[JobGroup | JobStage | JobStep[Any]] = []
        self.run_if: JobConditionalType | None = None
        self.skip_if: JobConditionalType | None = None
        self.concurrent: bool = concurrent

    @contextmanager
    def group(
        self, name: str, concurrent: bool = False, workspace: ValueOrRef[Path | str] | None = None
    ) -> Generator[JobGroupBuilder, None, None]:
        builder: JobGroupBuilder = JobGroupBuilder(name, concurrent=concurrent, workspace=workspace)
        yield builder
        self.add_scope(builder.build())

    @contextmanager
    def stage(
        self, name: str, concurrent: bool = False, workspace: ValueOrRef[Path | str] | None = None
    ) -> Generator[JobStageBuilder, None, None]:
        builder: JobStageBuilder = JobStageBuilder(name, concurrent=concurrent, workspace=workspace)
        yield builder
        self.add_scope(builder.build())

    @contextmanager
    def step(
        self, name: str, concurrent: bool = False, workspace: ValueOrRef[Path | str] | None = None
    ) -> Generator[JobStepBuilder, None, None]:
        builder: JobStepBuilder = JobStepBuilder(name, concurrent=concurrent, workspace=workspace)
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
            values=self.values,
        )
        group.teardown += self.teardown
        return group


class JobStageBuilder(JobBuilderBase[JobStage]):
    def __init__(self, name: str, concurrent: bool = False, workspace: ValueOrRef[Path | str] | None = None) -> None:
        super().__init__(name, JobScopes.STAGE, workspace=workspace)

        self._scopes: list[JobGroup | JobStep[Any]] = []
        self.concurrent: bool = concurrent

    @contextmanager
    def group(
        self, name: str, concurrent: bool = False, workspace: ValueOrRef[Path | str] | None = None
    ) -> Generator[JobStageGroupBuilder, None, None]:
        builder: JobStageGroupBuilder = JobStageGroupBuilder(name, concurrent=concurrent, workspace=workspace)
        yield builder
        self.add_scope(builder.build())

    @contextmanager
    def step(
        self, name: str, concurrent: bool = False, workspace: ValueOrRef[Path | str] | None = None
    ) -> Generator[JobStepBuilder, None, None]:
        builder: JobStepBuilder = JobStepBuilder(name, concurrent=concurrent, workspace=workspace)
        yield builder
        self.add_scope(builder.build())

    def add_scope(self, scope: JobGroup | JobStep[Any]) -> None:
        self._scopes.append(scope)

    def build(self) -> JobStage:
        stage: JobStage = JobStage(
            name=self._name, scopes=self._scopes, concurrent=self.concurrent, id=self._id, values=self.values
        )
        stage.teardown += self.teardown
        return stage


class JobBuilder(JobBuilderBase[Job]):
    def __init__(self, name: str, workspace: ValueOrRef[Path | str] | None = None) -> None:
        super().__init__(name, JobScopes.JOB, workspace=workspace)

        self._scopes: list[JobStage | JobGroup | JobStep[Any]] = []

    @contextmanager
    def group(
        self, name: str, concurrent: bool = False, workspace: ValueOrRef[Path | str] | None = None
    ) -> Generator[JobGroupBuilder, None, None]:
        builder: JobGroupBuilder = JobGroupBuilder(name, concurrent=concurrent, workspace=workspace)
        yield builder
        self.add_scope(builder.build())

    @contextmanager
    def stage(
        self, name: str, concurrent: bool = False, workspace: ValueOrRef[Path | str] | None = None
    ) -> Generator[JobStageBuilder, None, None]:
        builder: JobStageBuilder = JobStageBuilder(name, concurrent=concurrent, workspace=workspace)
        yield builder
        self.add_scope(builder.build())

    @contextmanager
    def step(
        self, name: str, concurrent: bool = False, workspace: ValueOrRef[Path | str] | None = None
    ) -> Generator[JobStepBuilder, None, None]:
        builder: JobStepBuilder = JobStepBuilder(name, concurrent=concurrent, workspace=workspace)
        yield builder
        self.add_scope(builder.build())

    def add_scope(self, scope: JobStage | JobGroup | JobStep[Any]) -> None:
        self._scopes.append(scope)

    def build(self) -> Job:
        job: Job = Job(name=self._name, scopes=self._scopes, id=self._id, values=self.values)
        job.teardown += self.teardown
        return job
