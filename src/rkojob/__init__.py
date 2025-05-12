from __future__ import annotations

import re
from collections.abc import Iterable
from contextlib import contextmanager
from enum import Enum, auto
from typing import (
    Any,
    Callable,
    Final,
    Generator,
    Generic,
    Protocol,
    Tuple,
    TypeAlias,
    TypeVar,
    cast,
    overload,
    runtime_checkable,
)

from rkojob.delegates import delegate
from rkojob.values import (
    ComputedValue,
    EnvironmentVariable,
    NoValue,
    NoValueError,
    NoValueType,
    ValueConsumer,
    ValueKey,
    ValueProvider,
    ValueRef,
    Values,
)


class JobException(Exception):
    """Base class for job‑specific errors."""

    pass


class JobStatus(Protocol):
    def start_scope(self, scope: JobScope) -> None: ...

    def finish_scope(self, scope: JobScope | None = None) -> None: ...

    def skip_scope(self, scope: JobScope, reason: str | None = None) -> None: ...

    def start_section(self, name: str) -> None: ...

    def finish_section(self, name: str | None = None) -> None: ...

    def start_item(self, description: str) -> None: ...

    def finish_item(self, outcome: str = "done.", error: str | Exception | None = None) -> None: ...

    def info(self, info: str) -> None: ...

    def detail(self, detail: str) -> None: ...

    def error(self, error: Exception | str) -> None: ...

    def warning(self, warning: Exception | str) -> None: ...

    def output(self, output: str | Iterable[str], label: str | None = None) -> None: ...


class JobBaseStatus(JobStatus):
    def start_scope(self, scope: JobScope) -> None:  # pragma: no cover
        pass

    def finish_scope(self, scope: JobScope | None = None) -> None:  # pragma: no cover
        pass

    def skip_scope(self, scope: JobScope, reason: str | None = None) -> None:  # pragma: no cover
        pass

    def start_section(self, name: str) -> None:  # pragma: no cover
        pass

    def finish_section(self, name: str | None = None) -> None:  # pragma: no cover
        pass

    def start_item(self, description: str) -> None:  # pragma: no cover
        pass

    def finish_item(self, outcome: str = "done.", error: str | Exception | None = None) -> None:  # pragma: no cover
        pass

    def info(self, info: str) -> None:  # pragma: no cover
        pass

    def detail(self, detail: str) -> None:  # pragma: no cover
        pass

    def error(self, error: Exception | str) -> None:  # pragma: no cover
        pass

    def warning(self, warning: Exception | str) -> None:  # pragma: no cover
        pass

    def output(self, output: str | Iterable[str], label: str | None = None) -> None:  # pragma: no cover
        pass

    @contextmanager
    def scope(self, scope: JobScope) -> Generator[None, Any, None]:
        try:
            self.start_scope(scope)
            yield
        except Exception as e:
            self.error(e)
            raise
        finally:
            self.finish_scope(scope)

    @contextmanager
    def section(self, name: str) -> Generator[None, Any, None]:
        try:
            self.start_section(name)
            yield
        except Exception as e:
            self.error(e)
            raise
        finally:
            self.finish_section(name)

    @contextmanager
    def item(self, event: str) -> Generator[None, Any, None]:
        try:
            self.start_item(event)
            yield
        except Exception as e:
            self.error(e)
            raise
        finally:
            self.finish_item()


class JobStatusCollector:
    def __init__(self) -> None:
        pass

    def add_listener(self, status_listener: JobStatus) -> None:
        self.start_scope.add_callback(status_listener.start_scope)
        self.finish_scope.add_callback(status_listener.finish_scope)
        self.skip_scope.add_callback(status_listener.skip_scope)
        self.start_section.add_callback(status_listener.start_section)
        self.finish_section.add_callback(status_listener.finish_section)
        self.start_item.add_callback(status_listener.start_item)
        self.finish_item.add_callback(status_listener.finish_item)
        self.info.add_callback(status_listener.info)
        self.detail.add_callback(status_listener.detail)
        self.error.add_callback(status_listener.error)
        self.warning.add_callback(status_listener.warning)
        self.output.add_callback(status_listener.output)

    @contextmanager
    def scope(self, scope: JobScope) -> Generator[None, Any, None]:
        try:
            self.start_scope(scope)
            yield
        except Exception as e:
            self.error(e)
            raise
        finally:
            self.finish_scope(scope)

    @delegate
    def start_scope(self, scope: JobScope): ...

    @delegate
    def finish_scope(self, scope: JobScope | None = None): ...

    @delegate
    def skip_scope(self, scope: JobScope | None = None): ...

    @contextmanager
    def section(self, name: str) -> Generator[None, Any, None]:
        try:
            self.start_section(name)
            yield
        except Exception as e:
            self.error(e)
            raise
        finally:
            self.finish_section(name)

    @delegate
    def start_section(self, name: str) -> None: ...

    @delegate
    def finish_section(self, name: str | None = None) -> None: ...

    @contextmanager
    def item(self, event: str) -> Generator[None, Any, None]:
        try:
            self.start_item(event)
            yield
        except Exception as e:
            self.error(e)
            raise
        finally:
            self.finish_item()

    @delegate
    def start_item(self, event: str) -> None: ...

    @delegate
    def finish_item(self, outcome: str = "done.", error: str | Exception | None = None) -> None: ...

    @delegate
    def info(self, info: str) -> None: ...

    @delegate
    def detail(self, detail: str) -> None: ...

    @delegate
    def error(self, error: Exception | str) -> None: ...

    @delegate
    def warning(self, warning: Exception | str) -> None: ...

    @delegate
    def output(self, output: str | Iterable[str], label: str | None = None) -> None: ...


class JobScopeStatus(Enum):
    PASSED = auto()
    FAILED = auto()
    RUNNING = auto()
    FAILING = auto()
    SKIPPED = auto()
    UNKNOWN = auto()


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
    @property
    def status(self) -> JobStatusCollector: ...
    def get_scope_status(self, scope: JobScope) -> JobScopeStatus: ...

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
    A callable object that takes a `JobContext` parameter and returns a value.
    """

    def __call__(self, context: JobContext) -> R_co: ...

    """
    A callable object that takes a `JobContext` parameter.

    :param context: The current job context.
    :returns: A value of type *R_co*.
    """


# Convenience functions for reading values from provider-like objects.
# This includes objects that hold values (ex. ``ValueRef``),
# identify values (ex. ``ValueKey``), return values (ex. ``JobCallable``),
# or are values themselves.

JobResolvableValue: TypeAlias = ValueKey[T_co] | ValueProvider[T_co] | JobCallable[T_co] | T_co
"""
TypeAlias that represents all types that are considered "resolvable",
including those that require a ``JobContext``.
"""


@overload
def resolve_value(
    value: ValueKey[T_co],
    *,
    context: JobContext | None = ...,
    default: T_co | None = ...,
    raise_no_value: bool = ...,
) -> T | None: ...


@overload
def resolve_value(
    value: ValueRef[T_co], *, context: JobContext | None = ..., default: T_co | None = ..., raise_no_value: bool = ...
) -> T | None: ...


@overload
def resolve_value(
    value: JobCallable[T_co],
    *,
    context: JobContext | None = ...,
    default: T_co | None = ...,
    raise_no_value: bool = ...,
) -> T | None: ...


@overload
def resolve_value(
    value: T, *, context: JobContext | None = ..., default: T_co | None = ..., raise_no_value: bool = ...
) -> T_co | None: ...


def resolve_value(
    value: JobResolvableValue[T_co],
    *,
    context: JobContext | None = None,
    default: T_co | None = None,
    raise_no_value: bool = False,
) -> T_co | None:
    """
    Resolve a ``JobResolvableValue`` using the optional `context` if needed.

    :param value: The value to resolve.
    :param context: An optional ``JobContext`` to aid in value resolution.
    :param default: An optional default value to return if the value cannot be resolved. For example, if the `value` is
     a ``ValueRef`` that holds no value or the value is a ``ValueKey`` but no context was provided.
    :param raise_no_value: Whether to raise a NoValueError if the value cannot be resolved.
    :returns: The value or `default`.
    """
    if isinstance(value, ValueKey):
        if context:
            if raise_no_value or context.values.has_value(value):
                return context.values.get(value)
            else:
                return default
        if raise_no_value:
            raise NoValueError("Unable to resolve value without context.")
        return default

    if isinstance(value, ValueProvider):
        if raise_no_value or value.has_value:
            return value.get()
        return default

    if isinstance(value, JobCallable):
        if context:
            return value(context)
        if raise_no_value:
            raise NoValueError("Unable to resolve value without context.")
        return default

    return cast(T_co, value)


def resolve_values(
    values: Iterable[JobResolvableValue[Any]], *, context: JobContext | None = None, raise_no_value: bool = True
) -> list[Any]:
    return [resolve_value(value, context=context, raise_no_value=raise_no_value) for value in values]


def resolve_map(
    values: dict[Any, JobResolvableValue[Any]] | None = None,
    context: JobContext | None = None,
    raise_no_value: bool = True,
    **kwargs,
) -> dict[Any, Any]:
    if values is None:
        values = kwargs
    return {key: resolve_value(value, context=context, raise_no_value=raise_no_value) for key, value in values.items()}


FORMAT_MAP_KEY_PATTERN = re.compile(r"\{([^{}!:]+)(?:![rs])?(?::[^{}]+)?}")


class lazy_format:
    def __init__(self, template: str, **overrides: JobResolvableValue[Any]) -> None:
        """
        Lazily format a string using the provided `JobResolvableValue` instances and
        values from the *context* passed into `resolve_value`.

        :param value: The format string contain `{placeholder}` values.
        :param overrides: `JobResolvableValue` to use to replace placeholders.
        """
        self._template: str = template
        self._overrides: dict[str, JobResolvableValue[Any]] = overrides

    def __call__(self, context: JobContext) -> str:
        # Provided values
        values: dict[str, JobResolvableValue[Any]] = {**self._overrides}
        # Referenced values
        template_keys: list[str] = FORMAT_MAP_KEY_PATTERN.findall(self._template)
        # Missing values
        missing_keys: set[str] = set(template_keys) - set(values)
        # Add missing values from the context
        values.update({key: ValueKey(key) for key in missing_keys})

        resolved: dict[str, Any] = resolve_map(values, context=context)

        def substitute(match: re.Match) -> str:
            key = match.group(1)
            try:
                return str(resolved[key])
            except KeyError:  # pragma: no cover
                raise KeyError(f"Missing value for key '{key}' in lazy_format string: {self._template}")

        return FORMAT_MAP_KEY_PATTERN.sub(substitute, self._template)

    def __repr__(self) -> str:
        data_str = ", ".join(f"{k}={v!r}" for k, v in self._overrides.items())
        return f"lazy_format({self._template!r}{', ' + data_str if data_str else ''})"


class context_value(Generic[R_co]):
    def __init__(
        self, key: str, coercer: Callable[[Any], R_co] | None = None, default: R_co | NoValueType = NoValue
    ) -> None:
        """
        Retrieves a value from the context by key.
        :param key: The key of the value.
        :param coercer: A conversion function to coerce the value to the required type.
        :param default: A default value to set and return if no value is associated with the key.
        """
        self._key: str = key
        self._coercer: Callable[[Any], R_co] | None = coercer
        self._default: R_co | NoValueType = default

    def __call__(self, context: JobContext) -> R_co:
        if not context.values.has_value(self._key) and self._default is not NoValue:
            context.values.set(self._key, self._default)
            return cast(R_co, self._default)
        value: Any = context.values.get(self._key)
        if self._coercer:
            value = self._coercer(value)
        return cast(R_co, value)

    def __repr__(self) -> str:
        if self._coercer:
            return f"context_value('{self._key}', {self._coercer.__name__})"
        return f"context_value('{self._key}')"


environment_variable: type[EnvironmentVariable] = EnvironmentVariable
"""Convenience alias for a value provided by an environment variable."""


# Convenience functions for assigning values to consumer-like instances.
# This includes objects that accept values (ex. ``ValueConsumer``, ``ValueRef``)
# and those that identify assignable values (ex. ``ValueKey``) within the context of a...context.

JobAssignableValue: TypeAlias = ValueConsumer[T] | ValueKey[T]
"""TypeAlias for objects who can have a value assigned to them, including those that require a ``JobContext``."""


def assign_value(assignable: JobAssignableValue[T], value: T, *, context: JobContext | None = None) -> None:
    """
    Assign a value to a ``JobAssignableValue``.

    :param assignable: The ``JobAssignableValue`` instance to assign a value to.
    :param value: The value to assign to `assignable`.
    :param context: An optional ``JobContext`` which is required only if `assignable`
     references a context value (i.e. ``ValueKey``).
    """
    if isinstance(assignable, ValueConsumer):
        assignable.set(value)
    elif isinstance(assignable, ValueKey):
        if not context:
            raise JobException("Unable to assign value to context value without a context!")
        context.values.set(assignable, value)
    else:
        raise JobException(f"Unable to assign value to {assignable}")


def unassign_value(assignable: JobAssignableValue[T], *, context: JobContext | None = None) -> None:
    """
    Unassign (unset) a value on a ``JobAssignableValue``.

    :param assignable: The ``JobAssignableValue`` instance to unset.
    :param context: An optional ``JobContext`` which is required only if `assignable`
     references a context value (i.e. ``ValueKey``).
    """
    if isinstance(assignable, ValueConsumer):
        assignable.unset()
    elif isinstance(assignable, ValueKey):
        if not context:
            raise JobException("Unable to unassign context value without a context!")
        context.values.unset(assignable)
    else:
        raise JobException(f"Unable to unassign {assignable}")


JobConditionalValueType: TypeAlias = bool | tuple[bool, str]
"""TypeAlias for the return type used by scope conditions `run_if` and `skip_if`."""

JobConditionalType: TypeAlias = JobResolvableValue[JobConditionalValueType]
"""TypeAlias for the type used by scope conditions `run_if` and `skip_if`."""

job_always: Final[JobConditionalType] = ComputedValue[JobConditionalValueType](lambda: (True, "Always"))
"""Scope condition that always returns ``True``."""

job_never: Final[ValueProvider[JobConditionalValueType]] = ComputedValue(lambda: (False, "Never"))
"""Scope condition that always returns ``False``."""


def job_failing(context: JobContext) -> tuple[bool, str]:
    """Scope condition that returns ``True`` if *any* errors have been recorded."""
    return bool(context.get_exceptions()), "Job has failures."


def job_succeeding(context: JobContext) -> tuple[bool, str]:
    """Scope condition that returns ``True`` if *no* errors have been recorded."""
    return bool(not context.get_exceptions()), "Job is succeeding."


def scope_failing(scope: JobScope) -> JobConditionalType:
    """Scope condition that returns ``True`` if errors have been recorded for the provided `scope`."""

    def _wrapped(context: JobContext) -> tuple[bool, str]:
        return bool(context.get_exceptions(scope)), f"{scope} has failures."

    return _wrapped


def scope_succeeding(scope: JobScope) -> JobConditionalType:
    """Scope condition that returns ``True`` if *no* errors have been recorded for the provided `scope`."""

    def _wrapped(context: JobContext) -> tuple[bool, str]:
        return bool(not context.get_exceptions(scope)), f"{scope} is succeeding."

    return _wrapped


@runtime_checkable
class JobConditionalScope(Protocol):
    """
    Protocol for a scope that can be conditionally run and skipped.

    :ivar run_if: Whether the scope should be run.
    :ivar skip_if: Whether the scope should be skipped, even if it is eligible to run.
    """

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
