# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from __future__ import annotations

from typing import (
    Any,
    Tuple,
)

from rkojob import (
    JobCallable,
    JobContext,
    JobContextID,
    JobEvent,
    JobEventDispatcher,
    JobEventHandler,
    JobException,
    JobScope,
    JobScopeID,
    JobScopeStack,
    JobScopeStatus,
    JobStatus,
    JobTeardownScope,
    Values,
    create_context_id,
)
from rkojob.delegates import Delegate
from rkojob.events import (
    JobDirectEventDispatcher,
    JobErrorEvent,
    JobFinishScopeEvent,
    JobSkipScopeEvent,
    JobStartScopeEvent,
    JobStatusImpl,
)
from rkojob.writer import JobStatusWriter


class JobScopeStatuses(JobEventHandler):
    """
    A `JobEventHandler` implementation that tracks the status of scopes
    including errors that occurred within each scope.
    """

    def __init__(self) -> None:
        self._scope_stack: JobScopeStack[JobScopeID, None] = JobScopeStack()
        self._statuses: dict[JobScopeID, JobScopeStatus] = {}
        self._errors: dict[tuple[JobScopeID, ...], list[str | Exception]] = {}

    def get_status(self, scope: JobScopeID) -> JobScopeStatus:
        return self._statuses.get(scope, JobScopeStatus.UNKNOWN)

    def get_errors(self, scope: JobScopeID | None = None) -> list[str | Exception]:
        errors: list[str | Exception] = []
        for scopes in self._errors:
            if scope is None or scope in scopes:
                errors.extend(self._errors[scopes])
        return errors

    def handle(self, event: JobEvent) -> None:
        if isinstance(event, JobStartScopeEvent):
            self._start_scope(event.started_scope)
        elif isinstance(event, JobFinishScopeEvent):
            self._finish_scope(event.finished_scope)
        elif isinstance(event, JobSkipScopeEvent):
            self._skip_scope(event.skipped_scope)
        elif isinstance(event, JobErrorEvent):
            self._error(event.error)

    def _start_scope(self, scope: JobScopeID) -> None:
        if self.get_status(scope) != JobScopeStatus.UNKNOWN:
            raise JobException("Scope status already set.")
        self._scope_stack.push(scope)
        self._statuses[scope] = JobScopeStatus.RUNNING

    def _finish_scope(self, scope: JobScopeID | None = None) -> None:
        if scope and scope is not self._scope_stack.scope:
            raise JobException("Scope does not match scope on stack.")
        scope, _ = self._scope_stack.pop()
        self._statuses[scope] = JobScopeStatus.FAILED if self.get_errors(scope) else JobScopeStatus.PASSED

    def _skip_scope(self, scope: JobScopeID) -> None:
        self._statuses[scope] = JobScopeStatus.SKIPPED

    def _error(self, error: Exception | str) -> None:
        scope: JobScopeID | None = self._scope_stack.get_scope()
        path: tuple[JobScopeID, ...] = self._scope_stack.path_to(scope) if scope else tuple()
        if path not in self._errors:
            self._errors[path] = []
        self._errors[path].append(error)
        if scope:
            # If we have a running scope mark it as failing
            self._statuses[scope] = JobScopeStatus.FAILING


class JobScopeState:
    def __init__(self) -> None:
        # Teardown actions registered ad-hoc
        self.teardown: Delegate[[JobContext], None] = Delegate(continue_on_error=True, reverse=True)


class JobContextImpl(JobContext):
    def __init__(self, *, values: dict[str, Any] | None = None, status_writer: JobStatusWriter | None = None) -> None:
        # State that pushes and pops with the scope.
        self._id: JobContextID = create_context_id()
        self._scope_stack: JobScopeStack[JobScope, JobScopeState] = JobScopeStack(default_factory=JobScopeState)

        if values is None:
            values = {}
        self._values: Values = Values(**values)

        self._events: JobEventDispatcher = JobDirectEventDispatcher()
        self._events.add_handler(self)
        self._status: JobStatus = JobStatusImpl(self._events, self)

        self._scope_statuses: JobScopeStatuses = JobScopeStatuses()
        self._events.add_handler(self._scope_statuses)

        if status_writer:
            self._events.add_handler(status_writer)

    @property
    def id(self) -> JobContextID:
        return self._id

    def handle(self, event: JobEvent):
        if event.context == self.id:
            if isinstance(event, JobStartScopeEvent):
                self.push_scope(self._resolve_scope(event.started_scope))
            elif isinstance(event, JobFinishScopeEvent):
                self.pop_scope()

    def push_scope(self, scope: JobScope) -> None:
        """
        Push *scope* onto the context's scope stack.

        :param scope: The scope to push.
        """
        self._scope_stack.push(scope)

    def pop_scope(self) -> JobScope:
        """
        Pop a scope from the context's scope stack and free any associated state.

        :returns: The popped scope
        """
        scope, _ = self._scope_stack.pop()
        return scope

    @property
    def scope(self) -> JobScope:
        """
        :returns: The current, innermost, scope.
        """
        return self._scope_stack.peek()[0]

    @property
    def scopes(self) -> Tuple[JobScope, ...]:
        """
        :returns: The full scope stack from outermost to innermost.
        """
        return self._scope_stack.path_to(self._scope_stack.scope) if self._scope_stack else tuple()

    def add_teardown(self, scope: JobScopeID, teardown: JobCallable[None]) -> None:
        scope = self._resolve_scope(scope)
        if not isinstance(scope, JobTeardownScope):
            raise JobException(f"Scope {scope} does not support teardown.")
        if scope not in self._scope_stack:
            raise JobException(f"Scope {scope} is not an active scope.")
        self._scope_stack[scope].teardown += teardown

    def remove_teardown(self, scope: JobScopeID, teardown: JobCallable[None]) -> None:
        scope = self._resolve_scope(scope)
        if not isinstance(scope, JobTeardownScope):
            raise JobException(f"Scope {scope} does not support teardown.")
        if scope not in self._scope_stack:
            raise JobException(f"Scope {scope} is not an active scope.")
        self._scope_stack[scope].teardown -= teardown

    def get_teardown(self, scope: JobScopeID) -> Delegate[[JobContext], None]:
        scope = self._resolve_scope(scope)
        if not isinstance(scope, JobTeardownScope):
            raise JobException(f"Scope {scope} does not support teardown.")
        if scope not in self._scope_stack:
            raise JobException(f"Scope {scope} is not an active scope.")
        return self._scope_stack[scope].teardown

    def get_scope(self, scope: JobScopeID | None = None, generation: int = 0) -> JobScope | None:
        """
        Resolve a scope relative to another, where generation=0 is the same scope,
        generation=1 is the parent, etc.

        :param scope: Scope to resolve relative to or ``None`` to use the current scope.
        :param generation: The generation to resolve. A negative value means resolve relative from the root scope
         with -1 being the root.
        """
        if generation == 0:
            if scope is None:
                return self._scope_stack.get_scope()
            return self._resolve_scope(scope)

        scope_index: int
        scopes: list[JobScope] = list(self.scopes)
        if generation < 0:
            # Get a scope relative to the root
            scope_index = -1
        else:
            # Get a scope relative to scope
            if scope is None:
                scope_index = len(scopes) - 1
            else:
                scope = self._resolve_scope(scope)
                try:
                    scope_index = scopes.index(scope)
                except ValueError:
                    raise JobException(f"Scope '{scope}' is not in scope")

        scope_index -= generation
        if scope_index < 0:
            return None

        if scope_index >= len(scopes):
            raise JobException(
                f"Unable to get scope relative to {'root' if generation < 0 else scope} using generation={generation}"
            )
        return scopes[scope_index]

    def _resolve_scope(self, scope_id: JobScopeID) -> JobScope:
        if isinstance(scope_id, JobScope):
            # Scope ID is the scope itself.
            return scope_id

        if scope_id in self._scope_stack.all_nodes:
            return self._scope_stack.all_nodes[scope_id].key  # type: ignore[index]

        for scope in self._scope_stack.all_nodes:
            if scope_id.id == scope.id:
                return scope

        raise JobException(f"Scope with ID '{scope_id.id}' is not known to this context.")

    @property
    def events(self) -> JobStatus:
        return self._status

    def get_scope_status(self, scope: JobScopeID) -> JobScopeStatus:
        return self._scope_statuses.get_status(scope)

    def error(self, error: str | Exception) -> Exception:
        """
        Record *error* in the current scope.

        :param error: And exception or error message.
        :returns: The exception instance or the error message as an exception.
        """
        if not isinstance(error, Exception):
            error = JobException(error)
        self.events.error(error)
        return error

    def get_errors(self, scope: JobScopeID | None = None) -> list[Exception]:
        """
        Return exceptions recorded for *scope* or for *all* scopes if omitted.

        :param scope: Scope to return exceptions for, or ``None`` to get all exceptions.
        :returns: List of recorded exceptions.
        """
        return [
            Exception(error) if not isinstance(error, Exception) else error
            for error in self._scope_statuses.get_errors(scope)
        ]

    @property
    def values(self) -> Values:
        return self._values
