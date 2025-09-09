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
from pathlib import Path
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
    ValueOrRef,
    ValueProvider,
    ValueRef,
    Values,
)


class JobException(Exception):
    """Base class for job‑specific errors."""

    pass


class JobEvent:
    """
    A class the represents some event that has occurred. This class can be used
    directly or sub-typed.
    """

    def __init__(self, type: str, context: JobContext, scope: JobScopeID | None, **data) -> None:
        """
        :param type: A string that identifies the type of event.
        :param context: The context in which the event occurred.
        :param scope: The scope in which the event occurred, or `None` if the
         event is not associated with a scope.
        :param data: Additional data associated with the event.
        """
        self.type: str = type
        self.context: JobContext = context
        self.scope: JobScopeID | None = scope
        self.timestamp: datetime = datetime.now()
        self.data: dict[str, Any] = data


class JobEventHandler(Protocol):
    """
    A protocol for type that can handle a `JobEvent`.
    """

    def handle(self, event: JobEvent) -> None:
        """
        Handle the provided event. What it means to "handle" is up to the
        implementation.

        :param event: The `JobEvent` to handle.
        """


@runtime_checkable
class JobEventDispatcher(JobEventHandler, Protocol):
    """
    A `JobEventHandler` that dispatches events to zero or more other handlers.
    """

    def add_handler(self, handler: JobEventHandler) -> None:
        """
        Add a handler as an event destination.
        :param handler: The handler to add as an event destination.
        """

    def remove_handler(self, handler: JobEventHandler) -> None:
        """
        Remove a handler as an event destination.
        :param handler: The handler to remove as an event destination.
        """


class ItemContextOutcome:
    """
    A class returned by the `JobStatus.item()` context manager that can be used
    to set the outcome or error of an item.
    """

    def __init__(self, outcome: str = "done.", error: str | Exception | None = None) -> None:
        self.outcome: str = outcome
        self.error: str | Exception | None = error


class JobStatus(JobEventHandler, ABC):
    """
    Convenience base class which defines methods for well-known `JobEvents`
    """

    def add_handler(self, handler: JobEventHandler) -> None:
        """
        For implementations that support dispatch, add a handler as an event
        destination.
        :param handler: The handler to add as an event destination.
        """

    def remove_handler(self, handler: JobEventHandler) -> None:
        """
        For implementations that support dispatch, remove a handler as an event
        destination.
        :param handler: The handler to remove as an event destination.
        """

    @abstractmethod
    def fork_context(self, context: JobContext) -> None:
        """
        Create and handle an event indicating that a context has been forked.
        :param context: The new context that was forked off of the "parent"
         context.
        """

    @abstractmethod
    def join_context(self, context: JobContext) -> None:
        """
        Create and handle an event indicating that a forked context has been
        joined.
        :param context: The previously forked context that has been joined.
        """

    @abstractmethod
    def start_scope(self, scope: JobScopeID) -> None:
        """
        Create and handle an event indicating that a scope has been started.
        :param scope: The started scope.
        """

    @abstractmethod
    def finish_scope(self, scope: JobScopeID | None = ...) -> None:
        """
        Create and handle an event indicating that a scope has finished.
        :param scope: The finished scope. If `None`, the current scope will be
         assumed.
        """

    @abstractmethod
    def skip_scope(self, scope: JobScopeID, reason: str | None = ...) -> None:
        """
        Create and handle an event indicating that a scope has been skipped.
        :param scope: The scope that has been skipped.
        :param reason: The optional reason that the scope was skipped.
        """

    @abstractmethod
    def start_scope_teardown(self, scope: JobScopeID | None = ...) -> None:
        """
        Create and handle an event indicating that scope teardown has been
        started.
        :param scope: The scope being torn down. If `None`, the current scope
         will be assumed.
        """

    @abstractmethod
    def finish_scope_teardown(self, scope: JobScopeID | None = ...) -> None:
        """
        Create and handle an event indicating that scope teardown has finished.
        :param scope: The scope that has been torn down. If `None`, the
         current scope will be assumed.
        """

    @abstractmethod
    def start_section(self, section: str) -> None:
        """
        Create and handle an event indicating that a section has been started.
        `JobAction` implementations can use this event to logically organize an
        action's...actions.
        :param section: The started section.
        """

    @abstractmethod
    def finish_section(self, section: str) -> None:
        """
        Create and handle an event indicating that a section has been finished.
        `JobAction` implementations can use this event to logically organize
        and report on an action's...actions.
        :param section: The finished section.
        """

    @abstractmethod
    def start_item(self, item: str) -> None:
        """
        Create and handle an event indicating that an item has been started.
        `JobAction` implementations can use this event to logically organize
        and report on an action's...actions.
        :param item: The started item.
        """

    @abstractmethod
    def finish_item(self, outcome: str = ..., error: str | Exception | None = ...) -> None:
        """
        Create and handle an event indicating that an item has been finished.
        `JobAction` implementations can use this event to logically organize
        and report on an action's...actions.
        :param outcome: The outcome of the finished item.
        :param error: Optional error if the item failed.
        """

    @abstractmethod
    def info(self, message: str) -> None:
        """
        Create and handle an event containing an informational message.
        `JobAction` implementations can use this event to logically organize
        and report on an action's...actions.
        :param message: The informational message.
        """

    @abstractmethod
    def detail(self, message: str) -> None:
        """
        Create and handle an event containing a detailed message.
        `JobAction` implementations can use this event to logically organize
        and report on an action's...actions.
        :param message: The detailed message.
        """

    @abstractmethod
    def error(self, error: Exception | str) -> None:
        """
        Create and handle an event indicating that an error has occurred.
        :param error: The error.
        """

    @abstractmethod
    def warning(self, warning: Exception | str) -> None:
        """
        Create and handle an event indicating that a warning has occurred.
        :param warning: The warning.
        """

    @abstractmethod
    def output(self, output: str | Iterable[str], label: str | None = ...) -> None:
        """
        Create and handle an event containing the output of a command.
        :param output: The output.
        :param label: Optional label of the output.
        """

    @contextmanager
    def scope(self, scope: JobScopeID) -> Generator[None, None, None]:
        """
        A context manager that calls `self.start_scope(scope)` on enter,
        `self.error(e)` on error, and `self.finish_scope(scope)` on exit.

        :param scope: The scope that will be started and finished.
        """
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
        """
        A context manager that calls `self.start_scope_teardown(scope)` on
        enter, `self.warning(e)` on error, and
        `self.finish_scope_teardown(scope)` on exit.

        :param scope: The scope that will be torn down.
        """
        try:
            self.start_scope_teardown(scope)
            yield
        except Exception as e:
            self.warning(e)
        finally:
            self.finish_scope_teardown(scope)

    @contextmanager
    def section(self, section: str) -> Generator[None, None, None]:
        """
        A context manager that calls `self.start_section(section)` on enter,
        `self.error(e)` on error, and `self.finish_section(section)` on exit.

        :param section: The section that will be started and finished.
        """
        try:
            self.start_section(section)
            yield
        except Exception as e:
            self.error(e)
            raise
        finally:
            self.finish_section(section)

    @contextmanager
    def item(self, item: str) -> Generator[ItemContextOutcome, None, None]:
        """
        A context manager that calls `self.start_item(item)` on enter,
        `self.error(e)` on error, and `self.finish_item(item)` on exit.

        :param item: The item that will be started and finished.
        """
        outcome: ItemContextOutcome = ItemContextOutcome()
        try:
            self.start_item(item)
            yield outcome
        except Exception as e:
            outcome.error = e
            raise
        finally:
            self.finish_item(outcome=outcome.outcome, error=outcome.error)


class JobScopeStatus(Enum):
    """Enum representing the current status of a scope."""

    PASSED = auto()
    """The scope has completed and was successful."""

    FAILED = auto()
    """The scope has completed and had errors."""

    RUNNING = auto()
    """The scope is currently running and no errors have occurred."""

    FAILING = auto()
    """The scope is currently running and errors have occurred."""

    SKIPPED = auto()
    """The scope was skipped."""

    UNKNOWN = auto()
    """The scope has not run."""


R = TypeVar("R")
P = ParamSpec("P")


class JobInterrupt(Protocol):
    """
    A protocol that can be used to send an interrupt to a concurrent task.
    """

    def is_set(self) -> bool:
        """:returns: Whether this interrupt has been set."""

    def set(self) -> None:
        """Sets this interrupt."""

    def clear(self) -> None:
        """Clears this interrupt."""

    def wait(self, timeout: float | None = None) -> bool:
        """
        Wait for this interrupt to be set.
        :param timeout: Optional timeout.
        :returns: `True` if this interrupt was set. `False` if timeout was
         exceeded.
        """


class JobFuture(Protocol[R]):
    """
    Protocol representing a concurrent task, typically scope.
    """

    @property
    def context(self) -> JobContext:
        """:returns: The context associated with the concurrent task."""

    @property
    def done(self) -> bool:
        """:returns: Whether this task is complete."""

    @property
    def running(self) -> bool:
        """:returns: Whether this task is still running."""

    def result(self, timeout: float | None = ...) -> R:
        """
        Wait for this task to complete and return the result.
        :param timeout: An optional timeout. If the timeout is exceeded a
         `TimeoutError` is raised.
        """

    @property
    def future(self) -> Future[R]:
        """:returns: The wrapped `concurrent.Future` instance."""


class JobFutures(Protocol):
    """
    Protocol providing methods to create and manage `JobFuture` instances.
    """

    def submit(self, context: JobContext, task: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> JobFuture[R]:
        """
        Submits a new task for concurrent execution.
        :param context: The context associated with the `JobFuture` to be created.
        :param task: The task to execute concurrently.
        :param args: Args to pass to the task.
        :param kwargs: Keyword args to pass to the task.
        :returns: A `JobFuture` instance.
        """

    @property
    def futures(self) -> list[JobFuture[Any]]:
        """:returns: A list of `JobFuture` instances submitted using this instance."""

    def shutdown(self) -> None:
        """
        Clean-up resources associated with this `JobFutures` instance. No tasks
        can be submitted after this method is called.
        """

    def create_interrupt(self) -> JobInterrupt:
        """
        :returns: A new `JobInterrupt` instance which can be used to send an
         interrupt to a `JobFuture`.
        """


JobIdType: TypeAlias = str


def create_context_id() -> JobIdType:
    """
    Creates a new, unique context ID value.
    """
    return JobIdType(uuid4())


class JobContext(Protocol):
    """
    Execution context for a running job.

    Implementations maintain a stack of ``JobScope`` objects, provide
    nested status reporting via `in_scope`, and collect exceptions
    raised during execution.
    """

    @property
    def id(self) -> JobIdType:
        """:returns: The unique identifier for this context."""

    def push_scope(self, scope: JobScope) -> None:
        """
        Push *scope* onto the context's scope stack.

        :param scope: The scope to push.
        """

    def pop_scope(self) -> JobScope:
        """
        Pop a scope from the context's scope stack and free any associated state.

        :returns: The popped scope
        """

    @property
    def scope(self) -> JobScope:
        """
        :returns: The current, innermost, scope.
        """

    @property
    def scopes(self) -> Tuple[JobScope, ...]:
        """
        :returns: The full scope stack from outermost to innermost.
        """

    def get_scope(self, scope: JobScopeID | None = ..., generation: int = ...) -> JobScope | None:
        """
        Resolve a scope relative to another, where generation=0 is the same scope,
        generation=1 is the parent, etc.

        :param scope: Scope to resolve relative to or ``None`` to use the current scope.
        :param generation: The generation to resolve. A negative value means resolve relative from the root scope
         with -1 being the root.
        """

    def add_teardown(self, scope: JobScopeID, teardown: JobCallable[None]) -> None:
        """
        Add an action to the *scope*'s teardown. Teardown actions added via
        this method are executed in reverse order of addition (LIFO) and
        *before* actions that are statically defined during job definition,
        which are executed in definition order (FIFO).

        :param scope: The scope to add the teardown action to.
        :param teardown: The action to execute during the scope's teardown.
        """

    def remove_teardown(self, scope: JobScopeID, teardown: JobCallable[None]) -> None:
        """
        Remove an action from the *scope*'s teardown. Only actions added via
        `add_teardown()` can be removed.

        :param scope: The scope to remove the teardown action from.
        :param teardown: The action to remove from the scope's teardown.
        """

    def get_teardown(self, scope: JobScopeID) -> Delegate[[JobContext], None]:
        """
        Get a teardown ``Delegate`` that, when called, will execute the
        teardown actions added via `add_teardown`.

        :returns: A `Delegate` instance that will invoke the teardown actions.
        """

    def get_futures(self, scope: JobScopeID) -> JobFutures:
        """
        Gets the ``JobFutures`` instance that can be used to execute concurrent
        scopes within the provided scope.
        :param scope: The parent scope that the concurrent scope will be
         executed within.
        :returns: A ``JobFutures`` instance.
        """

    def get_interrupt(self) -> JobInterrupt | None:
        """
        :returns: Optional interrupt that can be used to interrupt concurrent
         scopes associated with this context.
        """

    def error(self, error: str | Exception) -> Exception:
        """
        Record *error* in the current scope. Wrapper for
        `context.events.error()`.

        :param error: And exception or error message.
        :returns: The exception instance or the error message as an exception.
        """

    def get_errors(self, scope: JobScopeID | None = ...) -> list[Exception]:
        """
        Return exceptions recorded for *scope* or for *all* scopes if omitted.

        :param scope: Scope to return exceptions for, or ``None`` to get all exceptions.
        :returns: List of recorded exceptions.
        """

    def get_report(self, scope: JobScopeID | None = ...) -> dict[JobScopeID, Any]:
        """
        Generate a report for *scope*, including child scopes.

        :param scope: The scope to generate a report for. If ``None``, use the
         current scope.
        :returns: A dict including scope status and any recorded errors.
        """

    @property
    def values(self) -> Values:
        """
        :returns: A ``Values`` instance containing values associated with this
         context.
        """

    def get_value(
        self, key: ValueKey[T] | str, coercer: Callable[[Any], T] | None = None, default: T | NoValueType = NoValue
    ) -> T:
        """
        Get the value associated with the provided `key` from this context's values. If no value is present a
        ``NoValueError`` is raised (not a ``KeyError``).

        :param key: A `ValueKey` or `str` key.
        :param coercer: An optional function to convert the raw value to the
         expected type.
        :param default: An optional default to use if no value is found; will
         be set and returned.
        :returns: A value of type `T`.
        """

    def has_value(self, key: ValueKey[T] | str) -> bool:
        """
        Check whether a value exists associated with the provided *key* in the context's values.
        """

    def set_value(self, key: ValueKey[T] | str, value: ValueOrRef[T]) -> None:
        """
        Sets or adds a `value` associated with the provided `key` to this context's values.

        :param key: The key to associate the value with.
        :param value: The value to add to this ``Values`` instance.
        """

    @property
    def events(self) -> JobStatus:
        """
        :returns: A `JobStatus` implementation that serves as the primary means
         to generate and handle events from this context and its current scope.
        """

    def get_scope_status(self, scope: JobScopeID) -> JobScopeStatus:
        """
        Get the current status of a scope.

        :param scope: The scope to get the status for.
        :returns: A ``JobScopeStatus`` instance.
        """

    def fork(self, interrupt: JobInterrupt) -> JobContext:
        """
        Create a forked, isolated context from this context.
        :param interrupt: The `JobInterrupt` instance that can be used to
         interrupt concurrent scopes that are using forked context.
        :returns: A context forked from this context.
        """

    def join(self) -> None:
        """
        Join a context that had been previously forked. For example, flush all
        "local" events that had been generated while the context was forked.
        """


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
    def id(self) -> JobIdType:
        """:returns: A unique identifier for the scope."""


class JobScopeType(Protocol):
    """
    Classifies a `JobScope`, typically implemented as an ``Enum``.
    Lower values for `value` usually denotes a higher‑level scope.
    """

    @property
    def value(self) -> int:
        """:returns: The enum value of the scope type."""


@runtime_checkable
class JobScope(JobScopeID, Protocol):
    """Logical unit of work executed as part of a job."""

    @property
    def type(self) -> JobScopeType:
        """:returns: The type of the scope."""

    @property
    def name(self) -> str:
        """:returns: The name of the scope."""

    @property
    def concurrent(self) -> bool:
        """:returns: Whether the scope should be executed concurrently."""


@runtime_checkable
class JobGroupScope(JobScope, Protocol):
    """
    Composite scope that groups child scopes.

    :ivar list scopes: List of child scopes.
    """

    @property
    def scopes(self) -> list[JobScope]:
        """:returns: A list of child scopes."""


K = TypeVar("K", bound=JobScopeID)
V = TypeVar("V")


class JobScopeStackNode(Generic[K, V]):
    """
    Node to store data associated with a scope in a ``JobScopeStack``.
    """

    def __init__(self, key: K, value: V, parent: JobScopeStackNode[K, V] | None) -> None:
        self.key: K = key
        self.value: V = value
        self.parent: JobScopeStackNode[K, V] | None = parent
        self.children: list[JobScopeStackNode[K, V]] = []
        if self.parent:
            # Add this node to the parent's children
            self.parent.children.append(self)


class JobScopeStack(Generic[K, V], Mapping[K, V]):
    """
    A stack/dict-like data structure that aids in keeping track of scopes and
    associated state.
    """

    def __init__(self, default_factory: Callable[[], V] | None = None) -> None:
        """
        :param default_factory: Optional factory function used to create a
         value for a key if it does not exist.
        """
        self._node: JobScopeStackNode[K, V] | None = None
        self._nodes: dict[K, JobScopeStackNode[K, V]] = {}
        if default_factory is None:
            # Just return None
            def default_factory() -> V:
                return None  # type: ignore[return-value]

        self._default_factory: Callable[[], V] = default_factory

        # Set when a stack is a fork. Indicates where the fork occurred
        self._forked_node: JobScopeStackNode[K, V] | None = None

    def push(self, key: K, value: V | None = None) -> None:
        """
        Push a scope, and optional value, onto the stack.

        :param key: The scope to push onto the stack.
        :param value: Optional value to associate with the scope.
        """
        if value is None:
            # Create a default value
            value = self._default_factory()

        # Create a new node with the current node as the parent.
        self._node = JobScopeStackNode(key, value, self._node)

        # Add the node to our list of all known nodes for quick lookup
        self._nodes[key] = self._node

    def pop(self) -> tuple[K, V]:
        """
        Pop a scope from the stack.

        :returns: A tuple of the scope and its associated value.
        """
        if self._node is None:
            raise JobException("Scope stack underflow.")

        # Get the current node
        node: JobScopeStackNode[K, V] = self._node

        # Assign the current node to the popped node's parent
        self._node = self._node.parent

        # Return the scope and associated value
        return node.key, node.value

    def peek(self) -> tuple[K, V]:
        """:returns: A tuple of the current scope and associated value."""
        if self._node is None:
            raise JobException("Scope stack underflow.")
        return self._node.key, self._node.value

    @property
    def all_nodes(self) -> dict[K, JobScopeStackNode[K, V]]:
        """:returns: A scope-to-node dictionary of all nodes encountered by this stack."""
        return self._nodes

    def get_scope(self) -> K | None:
        """
        :returns: The current scope or ``None`` if there is no scope on the
         stack.
        """
        if self._node is None:
            return None
        return self._node.key

    @property
    def scope(self) -> K:
        """:returns: The current scope on the stack."""
        return self.peek()[0]

    @property
    def value(self) -> V:
        """
        :returns: The value associated with the current scope on the stack.
        """
        return self.peek()[1]

    def path_to(self, key: K) -> tuple[K, ...]:
        """
        Get a tuple of scopes that is a "path" to the provided scope.

        :param key: The scope to get the path to.
        :returns: The "path" to the provided scope from outermost to innermost
         scope.
        """
        path: list[K] = []

        # Get the node for the provided scope
        node: JobScopeStackNode[K, V] | None = self._nodes.get(key)

        # Walk up from the provided scope up to the root scope
        while node:
            path.append(node.key)
            node = node.parent

        # Reverse the path so that the root is
        # first and the provided scope is last.
        return tuple(reversed(path))

    def children_of(self, key: K, depth: int | None = None) -> tuple[K, ...]:
        """
        Get the children of the provided scope

        :param key: The scope to get the children of.
        :param depth: How deep to go when collecting children.
        :returns: A tuple of child scopes. Immediate children first.
        """
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
        """:returns: A new scope stack forked at the current scope."""
        # Create a new instance
        fork: JobScopeStack[K, V] = type(self)()
        # Set the current node
        fork._node = self._node
        # Make an isolated copy of the node dict
        fork._nodes = copy(self._nodes)
        # Use the same default factory
        fork._default_factory = self._default_factory
        # Make a note of the fork location
        fork._forked_node = self._node
        return fork

    @property
    def at_fork(self) -> bool:
        """:returns: Whether the stack is at the node where it was forked."""
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

    def __call__(self, context: JobContext) -> R_co:
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
    if isinstance(value, ValueProvider):
        # The value is a value provider which
        # may or may not have a value.
        if raise_no_value or value.has_value:
            # Either we want to raise an error
            # or we know we have a value.
            return value.get()
        # We don't want to raise an error, and we
        # don't have the value. Return the default.
        return default

    if isinstance(value, JobCallable):
        # The value is JobCallable that takes a
        # JobContext as an arg and returns a value.
        if context:
            return value(context)
        if raise_no_value:
            raise NoValueError("Unable to resolve value without context.")
        return default

    if isinstance(value, ValueKey):
        # The value is a key used to resolve a value
        # from the context's Value's instance.
        if context:
            if raise_no_value or context.values.has_value(value):
                # Either we want to raise an error instead of returning
                # the default, or we know we have a value.
                return context.values.get(value)
            else:
                # We don't want to raise an error, and we
                # don't have the value. Return the default.
                return default

        # No context to resolve value
        if raise_no_value:
            raise NoValueError("Unable to resolve value without context.")
        return default

    return cast(T_co, value)


def resolve_values(
    values: Iterable[JobResolvableValue[Any]], *, context: JobContext | None = None, raise_no_value: bool = True
) -> list[Any]:
    """
    Resolve an iterable of resolvable values.

    :param values: An iterable of resolvable values.
    :param context: A context used to resolve values.
    :param raise_no_value: Whether to raise an error if a value cannot be resolved.
    :returns: A list of resolved values.
    """
    return [resolve_value(value, context=context, raise_no_value=raise_no_value) for value in values]


def resolve_map(
    values: dict[Any, JobResolvableValue[Any]] | None = None,
    context: JobContext | None = None,
    raise_no_value: bool = True,
    **kwargs,
) -> dict[Any, Any]:
    """
    Resolve a map of resolvable values.

    :param values: A map of resolvable values.
    :param context: A context used to resolve values.
    :param raise_no_value: Whether to raise an error if a value cannot be resolved.
    :param kwargs: keyword args to resolve if *values* is not provided.
    :returns: A list of resolved values.
    """
    if values is None:
        values = kwargs
    resolved: dict[Any, Any] = {}
    for key, value in values.items():
        value = resolve_value(value, context=context, raise_no_value=raise_no_value)
        if isinstance(value, dict):
            value = resolve_map(value, context=context, raise_no_value=raise_no_value)
        if isinstance(value, list):
            value = resolve_values(value, context=context, raise_no_value=raise_no_value)
        resolved[key] = value
    return resolved


def lazy_map_value(value: JobResolvableValue[T], func: Callable[[T | None], R_co]) -> JobResolvableValue[R_co]:
    def _map(context: JobContext) -> R_co:
        resolved_value: T | None = resolve_value(value, context=context)
        return func(resolved_value)

    return _map


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


class context_value(ValueKey[T]):
    def __init__(self, key: str, coercer: Callable[[Any], T] | None = None, default: T | NoValueType = NoValue) -> None:
        """
        Retrieve a value from the context using a key that is resolved relative
        to the current scope stack. For example, with the key `foo` and the
        scope stack `job` → `stage` → `step`, the following keys will be tried,
        in order: `job.stage.step.foo`, `job.stage.foo`, `job.foo`, and `foo`.

        :param key: The name of the value to retrieve.
        :param coercer: An optional function to convert the raw value to the
         expected type.
        :param default: An optional default to use if no value is found; will
         be set and returned.
        """
        super().__init__(key)
        self._coercer: Callable[[Any], T] | None = coercer
        self._default: T | NoValueType = default

    def __call__(self, context: JobContext) -> T:
        return context.get_value(self.name, coercer=self._coercer, default=self._default)

    def set(self, context: JobContext, value: ValueOrRef[T]) -> None:
        """
        Sets the value associated with this `context_value`'s key in the
        context's ``Values`` instance.

        :param context: The context to set the value for.
        :param value: The value to set in the context.
        """
        context.set_value(self.name, value)

    def __repr__(self) -> str:
        if self._coercer:
            return f"context_value('{self.name}', {self._coercer.__name__})"
        return f"context_value('{self.name}')"


environment_variable: type[EnvironmentVariable] = EnvironmentVariable
"""Convenience alias for a value provided by an environment variable."""

value_ref: type[ValueRef] = ValueRef
"""Convenience alias for a value held in a ValueRef"""


job_workspace: context_value[Path | str] = context_value("workspace", default=".")
"""Current job workspace. Defaults to `.`"""


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


def scope_condition(
    value: JobResolvableValue[Any | None],
    func: Callable[[Any | None], Any | None] | None = None,
    reason: str | None = None,
) -> _JobScopeCondition:
    """
    Constructs a condition to be evaluated at runtime when deciding whether to
    run or skip a scope.

    The `value` is resolved just before the scope is evaluated. If provided,
    `func` is applied to the resolved value to transform or interpret it.
    The result is then used as the condition.

    The final outcome (whether the scope runs or is skipped) depends on how the
    condition is applied: for example, as a `run_if` (runs when the condition
    is truthy) or a `skip_if` (skips when truthy).

    :param value: A ``JobResolvableValue`` to be resolved at evaluation time.
    :param func: Optional transformation or predicate function applied to the
     resolved value.
    :param reason: Optional message recorded if the scope is skipped due to
     this condition.
    :returns: A ``_JobScopeCondition`` that can be used in `run_if` or
     `skip_if`.
    """

    def _func(context: JobContext) -> bool:
        result: Any | None = resolve_value(value, context=context)
        if isinstance(result, tuple) and isinstance(value, _JobScopeCondition):
            result = result[0]
        if func:
            result = func(result)
        return bool(result)

    return _JobScopeCondition(_func, reason if reason else "Condition is True")


job_always = _JobScopeCondition(lambda _: True, "Always")
"""Scope condition that always returns ``True``."""


job_never = _JobScopeCondition(lambda _: False, "Never")
"""Scope condition that always returns ``False``."""


job_failing = _JobScopeCondition(lambda context: bool(context.get_errors()), "Job has failures.")
"""Scope condition that returns ``True`` if *any* errors have been recorded."""


job_succeeding = _JobScopeCondition(lambda context: bool(not context.get_errors()), "Job is succeeding.")
"""Scope condition that returns ``True`` if *no* errors have been recorded."""


def scope_ran(scope: JobScopeID) -> JobCallable[JobConditionalValueType]:
    """Scope condition that returns ``True`` if a scope has run."""
    return _JobScopeCondition(
        lambda context: context.get_scope_status(scope) not in (JobScopeStatus.SKIPPED, JobScopeStatus.UNKNOWN),
        f"{scope} ran.",
    )


def scope_status(scope: JobScopeID, *statuses: JobScopeStatus) -> JobCallable[JobConditionalValueType]:
    """
    Scope condition that returns ``True`` if a scope's status matches one of
    the provided statuses.
    """
    return _JobScopeCondition(
        lambda context: context.get_scope_status(scope) in statuses,
        f"{scope} status is one of {[status.name for status in statuses]}.",
    )


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
