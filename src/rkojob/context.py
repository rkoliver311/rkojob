from __future__ import annotations

from contextlib import contextmanager
from typing import (
    Generator,
    Tuple,
)

from rkojob import (
    JobException,
    JobScope,
)


class JobContextState:
    def __init__(self, *, scope: JobScope) -> None:
        self.scope: JobScope = scope


class JobContextImpl:
    def __init__(self) -> None:
        # State that pushes and pops with the scope.
        self._state_stack: list[JobContextState] = []
        # List of recorded exceptions
        self._exceptions: dict[tuple[JobScope, ...], list[Exception]] = {}

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

    def exception(self, error: str | Exception) -> Exception:
        """
        Record *exception* in the current scope.

        :param error: And exception or error message.
        :returns: The exception instance or the error message as an exception.
        """
        if not isinstance(error, Exception):
            error = JobException(error)
        if self.scopes not in self._exceptions:
            self._exceptions[self.scopes] = []
        self._exceptions[self.scopes].append(error)
        return error

    def get_exceptions(self, scope: JobScope | None = None) -> list[Exception]:
        """
        Return exceptions recorded for *scope* or for *all* scopes if omitted.

        :param scope: Scope to return exceptions for, or ``None`` to get all exceptions.
        :returns: List of recorded exceptions.
        """
        exceptions: list[Exception] = []
        for scopes in self._exceptions:
            if scope is None or scope in scopes:
                exceptions.extend(self._exceptions[scopes])
        return exceptions
