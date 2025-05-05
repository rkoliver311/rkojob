from __future__ import annotations

from contextlib import contextmanager
from typing import (
    Final,
    Generator,
    Protocol,
    Tuple,
    TypeAlias,
    TypeVar,
    cast,
    overload,
    runtime_checkable,
)

from rkojob.values import (
    ComputedValue,
    ValueConsumer,
    ValueKey,
    ValueProvider,
    ValueRef,
    Values,
)


class JobException(Exception):
    """Base class for job‑specific errors."""

    pass


class JobContext(Protocol):
    """
    Execution context for a running job.

    Implementations maintain a stack of `JobScope` objects, provide
    nested status reporting via `in_scope`, and collect exceptions
    raised during execution.
    """

    @contextmanager
    def in_scope(self, scope: JobScope) -> Generator[JobScope, None, None]: ...

    """
    Push *scope* onto the stack for the duration of the ``with`` block.

    Implementations **must** pop the scope in a ``finally`` block to keep
    the stack balanced.

    :param scope: The scope to enter.
    :yields: The same *scope* instance for convenience.
    """

    @property
    def scope(self) -> JobScope: ...
    @property
    def scopes(self) -> Tuple[JobScope, ...]: ...

    def exception(self, error: str | Exception) -> Exception: ...

    """
    Record *exception* in the current scope.

    :param error: And exception or error message.
    :returns: The exception instance or the error message as an exception.
    """

    def get_exceptions(self, scope: JobScope | None = None) -> list[Exception]: ...
    @property
    def values(self) -> Values: ...

    """
    Return exceptions recorded for *scope* or for *all* scopes if omitted.

    :param scope: Scope to return exceptions for, or ``None`` to get all exceptions.
    :returns: List of recorded exceptions.
    """


class JobScopeType(Protocol):
    """
    Classifies a `JobScope`, typically implemented as an ``Enum``.
    Lower values for `value` usually denotes a higher‑level scope.
    """

    @property
    def value(self) -> int: ...


class JobScope(Protocol):
    """Logical unit of work executed as part of a job."""

    @property
    def type(self) -> JobScopeType: ...
    @property
    def name(self) -> str: ...


@runtime_checkable
class JobGroupScope(JobScope, Protocol):
    """
    Composite scope that groups child scopes.

    :ivar list scopes: List of child scopes.
    """

    @property
    def scopes(self) -> list[JobScope]: ...


R_co = TypeVar("R_co", covariant=True)
T_co = TypeVar("T_co", covariant=True)
T = TypeVar("T")


@runtime_checkable
class JobCallable(Protocol[R_co]):
    """
    A callable object that takes a `JobContext` parameter.

    :param context: The current job context.
    :returns: A value of type *R_co*.
    """

    def __call__(self, context: JobContext) -> R_co: ...


JobResolvableValue: TypeAlias = ValueKey[T_co] | ValueProvider[T_co] | JobCallable[T_co] | T_co


@overload
def resolve_value(
    value: ValueKey[T_co], *, context: JobContext | None = ..., default: T_co | None = ...
) -> T | None: ...


@overload
def resolve_value(
    value: ValueRef[T_co], *, context: JobContext | None = ..., default: T_co | None = ...
) -> T | None: ...


@overload
def resolve_value(
    value: JobCallable[T_co], *, context: JobContext | None = ..., default: T_co | None = ...
) -> T | None: ...


@overload
def resolve_value(value: T, *, context: JobContext | None = ..., default: T_co | None = ...) -> T_co | None: ...


def resolve_value(
    value: JobResolvableValue[T_co], *, context: JobContext | None = None, default: T_co | None = None
) -> T_co | None:
    if isinstance(value, ValueKey):
        if not context:
            return default
        return context.values.get_or_else(value, default=default)

    if isinstance(value, ValueProvider):
        return value.get() if value.has_value else default

    if isinstance(value, JobCallable):
        return value(context) if context else default

    return cast(T_co, value)


JobAssignableValue: TypeAlias = ValueConsumer[T] | ValueKey[T]


def assign_value(assignable: JobAssignableValue[T], value: T, *, context: JobContext | None = None) -> None:
    if isinstance(assignable, ValueConsumer):
        assignable.set(value)
    elif isinstance(assignable, ValueKey):
        if not context:
            raise JobException("Unable to assign value to context value without a context!")
        context.values.set(assignable, value)
    else:
        raise JobException(f"Unable to assign value to {assignable}")


def unassign_value(assignable: JobAssignableValue[T], *, context: JobContext | None = None) -> None:
    if isinstance(assignable, ValueConsumer):
        assignable.unset()
    elif isinstance(assignable, ValueKey):
        if not context:
            raise JobException("Unable to unassign context value without a context!")
        context.values.unset(assignable)
    else:
        raise JobException(f"Unable to unassign {assignable}")


JobConditionalValueType: TypeAlias = bool | tuple[bool, str]
JobConditionalType: TypeAlias = JobResolvableValue[JobConditionalValueType]

job_always: Final[JobConditionalType] = ComputedValue[JobConditionalValueType](lambda: (True, "Always"))
job_never: Final[ValueProvider[JobConditionalValueType]] = ComputedValue(lambda: (False, "Never"))


def job_fail(context: JobContext) -> tuple[bool, str]:
    return bool(context.get_exceptions()), "Job has failures."


def job_success(context: JobContext) -> tuple[bool, str]:
    return bool(not context.get_exceptions()), "Job is succeeding."


def scope_fail(scope: JobScope) -> JobConditionalType:
    def _wrapped(context: JobContext) -> tuple[bool, str]:
        return bool(context.get_exceptions(scope)), f"{scope} has failures."

    return _wrapped


def scope_success(scope: JobScope) -> JobConditionalType:
    def _wrapped(context: JobContext) -> tuple[bool, str]:
        return bool(not context.get_exceptions(scope)), f"{scope} is succeeding."

    return _wrapped


@runtime_checkable
class JobConditionalScope(Protocol):
    run_if: JobConditionalType | None
    skip_if: JobConditionalType | None


@runtime_checkable
class JobActionScope(JobScope, JobConditionalScope, Protocol):
    """
    Leaf scope that performs an *action*.

    :ivar JobCallable | None action: Function that executes the scope's work.
    """

    @property
    def action(self) -> JobCallable[None] | None: ...


@runtime_checkable
class JobTeardownScope(JobScope, JobConditionalScope, Protocol):
    """
    Leaf scope that performs a *teardown* after execution of a scope
    (not necessarily *this* scope).

    :ivar JobCallable | None teardown: Function that executes the scope's teardown work.
    """

    @property
    def teardown(self) -> JobCallable[None] | None: ...


@runtime_checkable
class JobAction(JobCallable[None], Protocol):
    """
    A class that performs an action and an optional teardown action.
    Used when an *action* and a *teardown* need to share state.
    """

    def action(self, context: JobContext) -> None: ...

    def teardown(self, context: JobContext) -> None: ...


class JobRunner(Protocol):
    """
    Orchestrates execution of a `JobScope` tree.

    A typical concrete implementation does a depth‑first walk::

        def run(self, ctx: JobContext, scope: JobScope) -> None:
            with ctx.in_scope(scope):
                if isinstance(scope, JobGroupScope):
                    for child in scope.scopes:
                        self.run(ctx, child)
                elif isinstance(scope, JobActionScope) and scope.action:
                    scope.action(ctx)
                elif isinstance(scope, JobTeardownScope) and scope.teardown:
                    scope.teardown(ctx)

    """

    def run(self, context: JobContext, scope: JobScope) -> None: ...
