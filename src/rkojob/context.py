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
        self._statuses: dict[JobScope, JobScopeStatus] = {}
        self._scope_stack: list[JobScope] = []
        self._errors: dict[tuple[JobScope, ...], list[str | Exception]] = {}

    def get_status(self, scope: JobScope) -> JobScopeStatus:
        return self._statuses.get(scope, JobScopeStatus.UNKNOWN)

    def get_errors(self, scope: JobScope | None = None) -> list[str | Exception]:
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
        key: Tuple[JobScope, ...] = tuple([scope for scope in self._scope_stack])
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
    def scopes(self) -> Tuple[JobScope, ...]:
        """
        :returns: The full scope stack from outermost to innermost.
        """
        return tuple(state.scope for state in self._state_stack)

    @property
    def status(self) -> JobStatusCollector:
        return self._status

    def get_scope_status(self, scope: JobScope) -> JobScopeStatus:
        return self._scope_statuses.get_status(scope)

    def _get_state(self, scope: JobScope | None) -> JobContextState:
        # Get the state for the provided scope
        if not self._state_stack:
            raise JobException("No state found")
        if scope is None:
            return self._state_stack[-1]
        state: JobContextState | None = next(iter(it for it in self._state_stack if it.scope.name == scope.name), None)
        if state is None:
            raise JobException(f"No state found for scope '{scope.name}'")
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

    def get_errors(self, scope: JobScope | None = None) -> list[Exception]:
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
