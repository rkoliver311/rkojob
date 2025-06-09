# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Iterable
from concurrent.futures import Future
from contextlib import contextmanager
from copy import copy
from datetime import datetime
from enum import Enum, auto
from typing import (
    Any,
    Callable,
    Generator,
    Generic,
    Iterator,
    Mapping,
    ParamSpec,
    Protocol,
    Tuple,
    Type,
    TypeAlias,
    TypeVar,
    cast,
    overload,
    runtime_checkable,
)
from uuid import uuid4

from rkojob.delegates import Delegate, delegate
from rkojob.values import (
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


class JobEvent:
    type: str

    def __init__(self, context: JobContext, scope: JobScopeID | None, **data) -> None:
        self.context: JobContext = context
        self.scope: JobScopeID | None = scope
        self.timestamp: datetime = datetime.now()
        self.data: dict[str, Any] = data


class JobEventHandler(Protocol):
    def handle(self, event: JobEvent): ...


class JobEventDispatcher(JobEventHandler, Protocol):
    def add_handler(self, handler: JobEventHandler) -> None: ...
    def remove_handler(self, handler: JobEventHandler) -> None: ...


class JobStatus(JobEventHandler, ABC):
    """
    Convenience protocol which defines methods for well-known JobEvents
    """

    @abstractmethod
    def fork_context(self, context: JobContext) -> None: ...

    @abstractmethod
    def join_context(self, context: JobContext) -> None: ...

    @abstractmethod
    def start_scope(self, scope: JobScopeID) -> None: ...

    @abstractmethod
    def finish_scope(self, scope: JobScopeID | None = ...) -> None: ...

    @abstractmethod
    def skip_scope(self, scope: JobScopeID, reason: str | None = ...) -> None: ...

    @abstractmethod
    def start_scope_teardown(self, scope: JobScopeID | None = ...) -> None: ...

    @abstractmethod
    def finish_scope_teardown(self, scope: JobScopeID | None = ...) -> None: ...

    @abstractmethod
    def start_section(self, section: str) -> None: ...

    @abstractmethod
    def finish_section(self, section: str) -> None: ...

    @abstractmethod
    def start_item(self, description: str) -> None: ...

    @abstractmethod
    def finish_item(self, outcome: str = ..., error: str | Exception | None = ...) -> None: ...

    @abstractmethod
    def info(self, info: str) -> None: ...

    @abstractmethod
    def detail(self, detail: str) -> None: ...

    @abstractmethod
    def error(self, error: Exception | str) -> None: ...

    @abstractmethod
    def warning(self, warning: Exception | str) -> None: ...

    @abstractmethod
    def output(self, output: str | Iterable[str], label: str | None = ...) -> None: ...

    @contextmanager
    def scope(self, scope: JobScopeID) -> Generator[None, None, None]:
        try:
            self.start_scope(scope)
            yield
        except Exception as e:
            self.error(e)
            raise
        finally:
            self.finish_scope(scope)

    @contextmanager
    def scope_teardown(self, scope: JobScopeID) -> Generator[None, None, None]:
        try:
            self.start_scope_teardown(scope)
            yield
        except Exception as e:
            self.warning(e)
        finally:
            self.finish_scope_teardown(scope)

    @contextmanager
    def section(self, section: str) -> Generator[None, None, None]:
        try:
            self.start_section(section)
            yield
        except Exception as e:
            self.error(e)
            raise
        finally:
            self.finish_section(section)

    @contextmanager
    def item(self, item: str) -> Generator[None, None, None]:
        try:
            self.start_item(item)
            yield
        except Exception as e:
            self.error(e)
            raise
        finally:
            self.finish_item()


class JobScopeStatus(Enum):
    PASSED = auto()
    FAILED = auto()
    RUNNING = auto()
    FAILING = auto()
    SKIPPED = auto()
    UNKNOWN = auto()


R = TypeVar("R")
P = ParamSpec("P")


class JobFuture(Protocol[R]):
    @property
    def context(self) -> JobContext: ...
    @property
    def done(self) -> bool: ...
    @property
    def running(self) -> bool: ...
    def result(self, timeout: float | None = ...) -> R: ...
    @property
    def future(self) -> Future[R]: ...


class JobFutures(Protocol):
    def submit(self, context: JobContext, task: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> JobFuture[R]: ...
    @property
    def futures(self) -> list[JobFuture[Any]]: ...
    def shutdown(self) -> None: ...


JobIdType: TypeAlias = str


def create_context_id() -> JobIdType:
    """
    Creates a new, unique context ID value.
    """
    return JobIdType(uuid4())


class JobContext(Protocol):
    """
    Execution context for a running job.

    Implementations maintain a stack of `JobScope` objects, provide
    nested status reporting via `in_scope`, and collect exceptions
    raised during execution.
    """

    @property
    def id(self) -> JobIdType: ...
    def push_scope(self, scope: JobScope) -> None: ...
    def pop_scope(self) -> JobScope: ...
    @property
    def scope(self) -> JobScope: ...
    @property
    def scopes(self) -> Tuple[JobScope, ...]: ...
    def get_scope(self, scope: JobScopeID | None = ..., generation: int = ...) -> JobScope | None: ...
    def add_teardown(self, scope: JobScopeID, teardown: JobCallable[None]) -> None: ...
    def remove_teardown(self, scope: JobScopeID, teardown: JobCallable[None]) -> None: ...
    def get_teardown(self, scope: JobScopeID) -> Delegate[[JobContext], None]: ...
    def get_futures(self, scope: JobScopeID) -> JobFutures: ...
    def error(self, error: str | Exception) -> Exception: ...
    def get_errors(self, scope: JobScopeID | None = ...) -> list[Exception]: ...
    def get_report(self, scope: JobScopeID | None = ...) -> dict[JobScopeID, Any]: ...
    @property
    def values(self) -> Values: ...
    @property
    def events(self) -> JobStatus: ...
    def get_scope_status(self, scope: JobScopeID) -> JobScopeStatus: ...
    def fork(self) -> JobContext: ...
    def join(self) -> None: ...


def create_scope_id() -> JobIdType:
    """
    Creates a new, unique scope ID value.
    """
    return JobIdType(uuid4())


@runtime_checkable
class JobScopeID(Protocol):
    """
    Provides a unique ID for a scope.
    """

    @property
    def id(self) -> JobIdType: ...


class JobScopeType(Protocol):
    """
    Classifies a `JobScope`, typically implemented as an ``Enum``.
    Lower values for `value` usually denotes a higher‑level scope.
    """

    @property
    def value(self) -> int: ...


@runtime_checkable
class JobScope(JobScopeID, Protocol):
    """Logical unit of work executed as part of a job."""

    @property
    def type(self) -> JobScopeType: ...
    @property
    def name(self) -> str: ...
    @property
    def concurrent(self) -> bool: ...


@runtime_checkable
class JobGroupScope(JobScope, Protocol):
    """
    Composite scope that groups child scopes.

    :ivar list scopes: List of child scopes.
    """

    @property
    def scopes(self) -> list[JobScope]: ...


K = TypeVar("K", bound=JobScopeID)
V = TypeVar("V")


class JobScopeStackNode(Generic[K, V]):
    def __init__(self, key: K, value: V, parent: JobScopeStackNode[K, V] | None) -> None:
        self.key: K = key
        self.value: V = value
        self.parent: JobScopeStackNode[K, V] | None = parent
        self.children: list[JobScopeStackNode[K, V]] = []
        if self.parent:
            self.parent.children.append(self)


class JobScopeStack(Generic[K, V], Mapping[K, V]):

    def __init__(self, default_factory: Callable[[], V] | None = None) -> None:
        self._node: JobScopeStackNode[K, V] | None = None
        self._nodes: dict[K, JobScopeStackNode[K, V]] = {}
        if default_factory is None:

            def default_factory() -> V:
                return None  # type: ignore[return-value]

        self._default_factory: Callable[[], V] = default_factory

        # Set when a stack is a fork. Indicates where the fork occurred
        self._forked_node: JobScopeStackNode[K, V] | None = None

    def push(self, key: K, value: V | None = None) -> None:
        if value is None:
            value = self._default_factory()
        self._node = JobScopeStackNode(key, value, self._node)
        self._nodes[key] = self._node

    def pop(self) -> tuple[K, V]:
        if self._node is None:
            raise JobException("Scope stack underflow.")
        node: JobScopeStackNode[K, V] = self._node
        self._node = self._node.parent
        return node.key, node.value

    def peek(self) -> tuple[K, V]:
        if self._node is None:
            raise JobException("Scope stack underflow.")
        return self._node.key, self._node.value

    @property
    def all_nodes(self) -> dict[K, JobScopeStackNode[K, V]]:
        return self._nodes

    def get_scope(self) -> K | None:
        if self._node is None:
            return None
        return self._node.key

    @property
    def scope(self) -> K:
        return self.peek()[0]

    @property
    def value(self) -> V:
        return self.peek()[1]

    def path_to(self, key: K) -> tuple[K, ...]:
        path: list[K] = []
        node: JobScopeStackNode[K, V] | None = self._nodes.get(key)
        while node:
            path.append(node.key)
            node = node.parent
        return tuple(reversed(path))

    def children_of(self, key: K, depth: int | None = None) -> tuple[K, ...]:
        children: list[K] = []
        if depth is None or depth > 0:
            node: JobScopeStackNode[K, V] | None = self._nodes.get(key)
            if node:
                if depth is not None:
                    depth -= 1
                for child in node.children:
                    children.append(child.key)
                    children.extend(self.children_of(child.key, depth=depth))
        return tuple(children)

    def fork(self) -> JobScopeStack[K, V]:
        fork: JobScopeStack[K, V] = type(self)()
        fork._node = self._node
        fork._nodes = copy(self._nodes)
        fork._default_factory = self._default_factory
        fork._forked_node = self._node
        return fork

    @property
    def at_fork(self) -> bool:
        return self._node is self._forked_node

    def __getitem__(self, key: K, /) -> V:
        return self._nodes[key].value

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __iter__(self) -> Iterator[K]:
        node: JobScopeStackNode[K, V] | None = self._node
        while node is not None:
            yield node.key
            node = node.parent


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


FORMAT_MAP_KEY_PATTERN = re.compile(r"\{([a-zA-Z_][\w\.]*)(?:![rs])?(?::[^{}]+)?}")


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
        values.update({key: context_value(key) for key in missing_keys})

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


class _JobContextIdentity:
    """A `JobCallable[JobContext]` that returns the context itself."""

    def __call__(self, context: JobContext) -> JobContext:
        return context

    def __repr__(self) -> str:
        return "job_context()"


job_context = _JobContextIdentity()


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
        value: Any = NoValue
        scopes: list[str] = [scope.name for scope in context.scopes]
        keys: list[str] = [f"{'.'.join(scopes[:i])}.{self._key}" for i in range(len(scopes), 0, -1)]

        for key in keys:
            if context.values.has_value(key):
                value = context.values.get(key)
                break

        if not context.values.has_value(self._key) and self._default is not NoValue:
            context.values.set(self._key, self._default)
            return cast(R_co, self._default)

        if value is NoValue:
            try:
                value = context.values.get(self._key)
            except NoValueError:
                message: str = f"No context value found for key '{self._key}'"
                if keys:
                    message += f" (first tried: {keys})."
                raise NoValueError(message)
        if self._coercer:
            value = self._coercer(value)
        return cast(R_co, value)

    def __repr__(self) -> str:
        if self._coercer:
            return f"context_value('{self._key}', {self._coercer.__name__})"
        return f"context_value('{self._key}')"


environment_variable: type[EnvironmentVariable] = EnvironmentVariable
"""Convenience alias for a value provided by an environment variable."""

value_ref: type[ValueRef] = ValueRef
"""Convenience alias for a value held in a ValueRef"""


class job_scope:
    def __init__(self, scope: JobScopeID | None = None, generation: int = 0) -> None:
        """
        Resolves a `JobScope` from the context by a `JobScopeID`.
        :param scope: The `JobScopeID` used to resolve the scope or ``None`` to resolve to the current scope.
        :param generation: The "generation" of the scope. A value of 0 returns the scope that identified by *scope*,
         1 returns *scope*'s parent, 2 returns the grandparent and so on. A negative value returns a scope
         relative to the root with -1 being the root scope.
        """
        self._scope: JobScopeID | None = scope
        self._generation: int = generation

    def __call__(self, context: JobContext) -> JobScope | None:
        return context.get_scope(self._scope, generation=self._generation)

    def __repr__(self) -> str:
        return f"job_scope({self._scope!r})"


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


class _JobScopeCondition:
    """Class for built-in scope conditions."""

    def __init__(self, func: JobCallable[bool], reason: str) -> None:
        self._func: JobCallable[bool] = func
        self._reason: str = reason

    def __call__(self, context: JobContext) -> JobConditionalValueType:
        return self._func(context), self._reason

    def __repr__(self) -> str:
        return self._reason


job_always = _JobScopeCondition(lambda _: True, "Always")
"""Scope condition that always returns ``True``."""


job_never = _JobScopeCondition(lambda _: False, "Never")
"""Scope condition that always returns ``False``."""


job_failing = _JobScopeCondition(lambda context: bool(context.get_errors()), "Job has failures.")
"""Scope condition that returns ``True`` if *any* errors have been recorded."""


job_succeeding = _JobScopeCondition(lambda context: bool(not context.get_errors()), "Job is succeeding.")
"""Scope condition that returns ``True`` if *no* errors have been recorded."""


def scope_failing(scope: JobScopeID) -> JobCallable[JobConditionalValueType]:
    """Scope condition that returns ``True`` if errors have been recorded for the provided `scope`."""
    return _JobScopeCondition(lambda context: bool(context.get_errors(scope)), f"{scope} has failures.")


def scope_succeeding(scope: JobScopeID) -> JobCallable[JobConditionalValueType]:
    """Scope condition that returns ``True`` if *no* errors have been recorded for the provided `scope`."""
    return _JobScopeCondition(lambda context: bool(not context.get_errors(scope)), f"{scope} is succeeding.")


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
class JobTeardownScope(JobScope, Protocol):
    """
    Scope that performs zero or more *teardown* actions before exiting.

    :ivar Delegate[[JobContext], None] teardown: Delegate used to add/call teardown actions.
    """

    @delegate(continue_on_error=True, reverse=True)
    def teardown(self, context: JobContext): ...


class JobAction(JobCallable[None], ABC):
    """
    A class that performs an action and an optional teardown action.
    Used when an *action* and a *teardown* need to share state.
    """

    def __call__(self, context: JobContext) -> None:
        self.action(context)

    @abstractmethod
    def action(self, context: JobContext) -> None: ...


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


class job_action(JobAction, Generic[P, R]):
    def __init__(self, action: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> None:
        """
        Wraps an arbitrary `callable` in a `JobAction` instance.

        :param action: The `callable` to wrap.
        :param args: Positional args to resolve and pass into *action*
        :param kwargs: Keyword args to resolve and pass into *action*
        """
        self._action: Callable[P, R] = action
        self._args: tuple[Any, ...] = args
        self._kwargs: dict[str, Any] = kwargs

    def action(self, context: JobContext) -> None:
        self._action(*resolve_values(self._args, context=context), **resolve_map(self._kwargs, context=context))

    def __repr__(self) -> str:
        return f"job_action({self._action!r})"


A = TypeVar("A", bound=JobAction)


class lazy_action(JobAction, Generic[A]):
    def __init__(self, action_type: Type[A], *args, **kwargs) -> None:
        """
        Defer the instantiation of a `JobAction` instance so that it's `__init__` args
        can be resolved using the *context* at the time of execution. `JobAction` implementations
        that perform their own argument resolution do not need to be lazily initialized.

        :param action_type: The type of action to instantiate.
        :param args: The positional arguments of the action's `__init__` method.
        :param kwargs: The keyword arguments of the action's `__init__` method.
        """
        super().__init__()
        self._action_type: Type[A] = action_type
        self._args: tuple[Any, ...] = args
        self._kwargs: dict[str, Any] = kwargs
        self._action_instance: A | None = None

    def _get_action_instance(self, context: JobContext) -> A:
        if self._action_instance is None:
            self._action_instance = self._action_type(
                *resolve_values(self._args, context=context),
                **resolve_map(self._kwargs, context=context),
            )
        return self._action_instance

    def action(self, context: JobContext) -> None:
        self._get_action_instance(context).action(context)

    def __repr__(self) -> str:
        return f"lazy_action({self._action_type.__name__})"
