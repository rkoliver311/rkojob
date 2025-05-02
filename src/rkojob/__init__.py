from __future__ import annotations

from contextlib import contextmanager
from typing import (
    Generator,
    Protocol,
    Tuple,
    TypeVar,
    runtime_checkable,
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


@runtime_checkable
class JobCallable(Protocol[R_co]):
    """
    A callable object that takes a `JobContext` parameter.

    :param context: The current job context.
    :returns: A value of type *R_co*.
    """

    def __call__(self, context: JobContext) -> R_co: ...


@runtime_checkable
class JobActionScope(JobScope, Protocol):
    """
    Leaf scope that performs an *action*.

    :ivar JobCallable | None action: Function that executes the scope's work.
    """

    @property
    def action(self) -> JobCallable[None] | None: ...


@runtime_checkable
class JobTeardownScope(JobScope, Protocol):
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
