# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from __future__ import annotations

from contextlib import contextmanager
from typing import (
    Any,
    Generator,
    Tuple,
)

from rkojob import (
    JobBaseStatus,
    JobException,
    JobScope,
    JobScopeID,
    JobScopeStatus,
    JobStatusCollector,
    Values,
)
from rkojob.writer import JobStatusWriter


class JobContextState:
    def __init__(self, *, scope: JobScope) -> None:
        self.scope: JobScope = scope


class JobScopeStatuses(JobBaseStatus):
    """
    A `JobStatus` implementation that tracks the status of scopes
    including errors that occurred within each scope.
    """

    def __init__(self) -> None:
        self._statuses: dict[JobScopeID, JobScopeStatus] = {}
        self._scope_stack: list[JobScope] = []
        self._errors: dict[tuple[JobScopeID, ...], list[str | Exception]] = {}

    def get_status(self, scope: JobScopeID) -> JobScopeStatus:
        return self._statuses.get(scope, JobScopeStatus.UNKNOWN)

    def get_errors(self, scope: JobScopeID | None = None) -> list[str | Exception]:
        errors: list[str | Exception] = []
        for scopes in self._errors:
            if scope is None or scope in scopes:
                errors.extend(self._errors[scopes])
        return errors

    def start_scope(self, scope: JobScope) -> None:
        if self.get_status(scope) != JobScopeStatus.UNKNOWN:
            raise JobException("Scope status already set.")
        self._scope_stack.append(scope)
        self._statuses[scope] = JobScopeStatus.RUNNING

    def finish_scope(self, scope: JobScope | None = None) -> None:
        if scope and scope is not self._scope_stack[-1]:
            raise JobException("Scope does not match scope on stack.")
        scope = self._scope_stack.pop()
        self._statuses[scope] = JobScopeStatus.FAILED if self.get_errors(scope) else JobScopeStatus.PASSED

    def finish_item(self, outcome: str = "done.", error: str | Exception | None = None) -> None:
        if error:
            self.error(error)

    def skip_scope(self, scope: JobScope, reason: str | None = None) -> None:
        self._statuses[scope] = JobScopeStatus.SKIPPED

    def error(self, error: Exception | str) -> None:
        key: Tuple[JobScopeID, ...] = tuple([scope for scope in self._scope_stack])
        if key not in self._errors:
            self._errors[key] = []
        self._errors[key].append(error)
        if key:
            # If we have a running scope mark it as failing
            self._statuses[key[-1]] = JobScopeStatus.FAILING


class JobContextImpl:
    def __init__(self, *, values: dict[str, Any] | None = None, status_writer: JobStatusWriter | None = None) -> None:
        # State that pushes and pops with the scope.
        self._state_stack: list[JobContextState] = []
        self._known_scopes: dict[str, JobScope] = {}
        if values is None:
            values = {}
        self._values: Values = Values(**values)
        self._status: JobStatusCollector = JobStatusCollector()
        self._scope_statuses: JobScopeStatuses = JobScopeStatuses()
        self._status.add_listener(self._scope_statuses)
        if status_writer:
            self._status.add_listener(status_writer)

    @contextmanager
    def in_scope(self, scope: JobScope) -> Generator[JobScope, None, None]:
        """
        Enter into *scope* for the duration of the ``with`` block.

        :param scope: The scope to enter.
        :yields: The same *scope* instance for convenience.
        """
        try:
            self._enter_scope(scope)
            yield scope
        finally:
            self._exit_scope(scope)

    def _enter_scope(self, scope: JobScope) -> None:
        state: JobContextState = JobContextState(scope=scope)
        self._state_stack.append(state)
        self._known_scopes[scope.id] = scope

    def _exit_scope(self, scope: JobScope) -> None:
        state: JobContextState = self._state_stack.pop()
        if state.scope is not scope:  # pragma: no cover
            raise JobException("Unexpected scope found on stack!")

    @property
    def scope(self) -> JobScope:
        """
        :returns: The current, innermost, scope.
        """
        return self._get_state(None).scope

    @property
    def root_scope(self) -> JobScope:
        if not self._state_stack:
            raise JobException("No root scope")
        return self._state_stack[0].scope

    def parent_scope(self, scope: JobScopeID | None = None, generation: int = 1):
        if scope is None:
            scope = self.scope
        scope_count: int = len(self._state_stack)
        scope_index: int = scope_count
        for idx, s in enumerate(self._state_stack):
            if scope == s.scope:
                scope_index = idx
                break
        parent_index: int = scope_index - generation
        if parent_index < 0 or scope_index >= scope_count:
            raise JobException(f"Scope {scope} has no parent (generation={generation})")
        return self._state_stack[parent_index].scope

    @property
    def scopes(self) -> Tuple[JobScope, ...]:
        """
        :returns: The full scope stack from outermost to innermost.
        """
        return tuple(state.scope for state in self._state_stack)

    def get_scope(self, scope_id: JobScopeID) -> JobScope:
        """
        Gets the `JobScope` instance associated with the provided *scope_id*.

        :param scope_id: A `JobScopeID` used to identify the scope.
        :returns: The `JobScope` associated with *scope_id* or *scope_id* if it is an instance of `JobScope`.
        """
        if isinstance(scope_id, JobScope):
            # Scope ID is the scope itself.
            return scope_id

        if scope_id.id not in self._known_scopes:
            raise JobException(f"Scope with ID '{scope_id.id}' is not known to this context.")

        return self._known_scopes[scope_id.id]

    @property
    def status(self) -> JobStatusCollector:
        return self._status

    def get_scope_status(self, scope: JobScopeID) -> JobScopeStatus:
        return self._scope_statuses.get_status(scope)

    def _get_state(self, scope: JobScopeID | None) -> JobContextState:
        # Get the state for the provided scope
        if not self._state_stack:
            raise JobException("No state found")
        if scope is None:
            return self._state_stack[-1]
        state: JobContextState | None = next(iter(it for it in self._state_stack if it.scope.id == scope.id), None)
        if state is None:
            raise JobException(f"No state found for scope '{scope}'")
        return state

    def error(self, error: str | Exception) -> Exception:
        """
        Record *error* in the current scope.

        :param error: And exception or error message.
        :returns: The exception instance or the error message as an exception.
        """
        if not isinstance(error, Exception):
            error = JobException(error)
        self.status.error(error)
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
