# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from __future__ import annotations

from abc import ABC
from contextlib import AbstractContextManager, contextmanager
from enum import Enum, auto
from typing import Generator, Generic, ParamSpec, Type, TypeVar, cast

from rkojob import (
    JobAction,
    JobCallable,
    JobConditionalType,
    JobContext,
    JobException,
    JobScopeType,
    resolve_map,
    resolve_values,
)


class JobBaseAction(ABC, JobAction):
    def __call__(self, context: JobContext) -> None:
        return self.action(context)

    def action(self, context: JobContext) -> None:  # pragma: no cover
        pass

    def teardown_step(self, context: JobContext) -> None:  # pragma: no cover
        pass

    def teardown_stage(self, context: JobContext) -> None:  # pragma: no cover
        pass

    def teardown_job(self, context: JobContext) -> None:  # pragma: no cover
        pass

    def teardown(self, context: JobContext) -> None:
        match context.scope.type:
            case JobScopes.STEP:
                self.teardown_step(context)
            case JobScopes.STAGE:
                self.teardown_stage(context)
            case JobScopes.JOB:
                self.teardown_job(context)
            case unknown_scope:
                raise JobException(f"Unknown scope type: {unknown_scope}")


R = TypeVar("R")
P = ParamSpec("P")


def lazy_action(action_type: Type[JobAction], *args, **kwargs) -> JobCallable[None]:
    """
    Defer the instantiation of a `JobAction` instance so that it's `__init__` args
    can be resolved using the *context* at the time of execution. `JobAction` implementations
    that perform their own argument resolution do not need to be lazily initialized.

    :param action_type: The type of action to instantiate.
    :param args: The positional arguments of the action's `__init__` method.
    :param kwargs: The keyword arguments of the action's `__init__` method.
    :returns: A `JobAction` instance that wraps *action_type* and will initialize it at the time of execution.
    """

    class _Wrapper(JobBaseAction):
        def __init__(self) -> None:
            super().__init__()
            self._action_instance: JobAction | None = None

        def _get_action_instance(self, context: JobContext) -> JobAction:
            if self._action_instance is None:
                self._action_instance = action_type(
                    *resolve_values(args, context=context),
                    **resolve_map(kwargs, context=context),
                )
            return self._action_instance

        def action(self, context: JobContext) -> None:
            self._get_action_instance(context).action(context)

        def teardown(self, context: JobContext) -> None:
            self._get_action_instance(context).teardown(context)

    return _Wrapper()


class JobScopes(Enum):
    """Concrete implementation of JobScopeType"""

    STEP = auto()
    STAGE = auto()
    JOB = auto()

    def __str__(self) -> str:
        return self.name.capitalize()


A = TypeVar("A", bound=JobCallable[None])


class JobStep(Generic[A]):
    """
    Class representing a job step.
    """

    def __init__(
        self,
        name: str,
        action: A | None = None,
        teardown: JobCallable[None] | None = None,
        run_if: JobConditionalType | None = None,
        skip_if: JobConditionalType | None = None,
    ) -> None:
        self._name: str = name

        self._action: A | None = None
        self._teardown: JobCallable[None] | None = None
        self._run_if: JobConditionalType | None = run_if
        self._skip_if: JobConditionalType | None = skip_if

        if action:
            self.action = action
        if teardown:
            self.teardown = teardown

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

    @property
    def teardown(self) -> JobCallable[None] | None:
        if self._teardown is None:
            if isinstance(self.action, JobAction):
                self._teardown = cast(JobAction, self.action).teardown
        return self._teardown

    @teardown.setter
    def teardown(self, teardown: JobCallable[None] | None) -> None:
        if isinstance(self.action, JobAction):
            raise ValueError("Cannot specify teardown when action is JobAction")
        self._teardown = teardown

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


class JobStage:
    """
    Class representing a job stage that consists of one or more steps.
    """

    def __init__(self, name: str, steps: list[JobStep] | None = None) -> None:
        self._name: str = name
        if steps is None:
            steps = []
        self.steps: list[JobStep] = steps

    @property
    def name(self) -> str:
        return self._name

    @property
    def type(self) -> JobScopeType:
        return JobScopes.STAGE

    @property
    def scopes(self) -> list[JobStep]:
        return self.steps

    def __str__(self) -> str:
        return f"{self.type} {self.name}"


class Job:
    """
    Class representing a job that consists of one or more stages.
    """

    def __init__(self, name: str, stages: list[JobStage] | None = None) -> None:
        self._name: str = name
        if stages is None:
            stages = []
        self.stages: list[JobStage] = stages

    @property
    def name(self) -> str:
        return self._name

    @property
    def type(self) -> JobScopeType:
        return JobScopes.JOB

    @property
    def scopes(self) -> list[JobStage]:
        return self.stages

    def __str__(self) -> str:
        return f"{self.type} {self.name}"


class JobStageBuilder:
    def __init__(self, name: str) -> None:
        self._name: str = name
        self._steps: list[JobStep] = []

    @contextmanager
    def step(self, name: str) -> Generator[JobStep, None, None]:
        step: JobStep = JobStep(name)
        yield step
        self._steps.append(step)

    def build(self) -> JobStage:
        return JobStage(name=self._name, steps=self._steps)


class JobBuilder(AbstractContextManager):
    def __init__(self, name: str) -> None:
        self._name: str = name
        self._stages: list[JobStage] = []

    def __exit__(self, exc_type, exc_value, traceback, /):
        pass

    @contextmanager
    def stage(self, name: str) -> Generator[JobStageBuilder, None, None]:
        builder: JobStageBuilder = JobStageBuilder(name)
        yield builder
        self._stages.append(builder.build())

    def build(self) -> Job:
        return Job(name=self._name, stages=self._stages)
