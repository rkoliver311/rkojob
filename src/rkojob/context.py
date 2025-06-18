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
    JobEvent,
    JobEventDispatcher,
    JobEventHandler,
    JobException,
    JobFutures,
    JobGroupScope,
    JobIdType,
    JobInterrupt,
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
    JobLocalEventDispatcher,
    JobSkipScopeEvent,
    JobStartScopeEvent,
    JobStatusImpl,
)
from rkojob.factories import JobFuturesFactory


class JobScopeStatuses(JobEventHandler):
    """
    A `JobEventHandler` implementation that tracks the status of scopes
    including errors that occurred within each scope.
    """

    def __init__(self) -> None:
        # A scope stack to track current scope and associated errors.
        self._scope_stack: JobScopeStack[JobScopeID, list[str | Exception]] = JobScopeStack(default_factory=list)
        # Dict to track scope status
        self._statuses: dict[JobScopeID, JobScopeStatus] = {}
        # Errors that occur outside a scope
        self._global_errors: list[str | Exception] = []

    def get_status(self, scope: JobScopeID) -> JobScopeStatus:
        """
        Get the status of *scope*.

        :param scope: The scope to get the status of.
        :returns: A ``JobScopeStatus`` value for the scope.
        """
        return self._statuses.get(scope, JobScopeStatus.UNKNOWN)

    def get_errors(self, scope: JobScopeID | None = None) -> list[str | Exception]:
        """
        Get the errors recorded for *scope* and all of its child scopes.

        :param scope: The scope to get errors for. If ``None``, return all errors.
        :returns: A list of errors recorded for the scope.
        """
        errors: list[str | Exception] = []
        scopes: list[JobScopeID]
        if scope is None:
            # No scope provided. Collect errors for all scopes.
            scopes = list(self._scope_stack.all_nodes)
        else:
            # Collect errors for this scope and all child scopes.
            scopes = [scope, *self._scope_stack.children_of(scope)]

        # Add errors for all scopes in reverse order (depth first).
        for key in reversed(scopes):
            errs = self._scope_stack[key]
            errors.extend(errs)

        if scope is None:
            # Include errors that occurred outside a scope.
            errors.extend(self._global_errors)

        return errors

    def get_report(self, scope: JobScopeID | None = None) -> dict[JobScopeID, Any]:
        """
        Generate a report for *scope*, including nested reports for children
        scopes.

        :param scope: The scope to generate a report for. If ``None``, use the
         current scope.
        :returns: A dict including scope status and any recorded errors.
        """
        if scope is None:
            # Try the current scope.
            scope = next(iter(self._scope_stack.all_nodes), None)
        if scope is None:
            # No scope. Return empty report.
            return {}
        return {
            scope: {
                # The current status of the scope.
                "status": self.get_status(scope),
                # Errors recorded during the scope.
                "errors": self._scope_stack[scope],
                # Nested reports for child scopes.
                "scopes": {
                    child: self.get_report(child)[child] for child in self._scope_stack.children_of(scope, depth=1)
                },
            }
        }

    def handle(self, event: JobEvent) -> None:
        # Listen for events in order to record state and errors.
        if isinstance(event, JobStartScopeEvent):
            self._start_scope(event.started_scope)
        elif isinstance(event, JobFinishScopeEvent):
            self._finish_scope(event.finished_scope)
        elif isinstance(event, JobSkipScopeEvent):
            self._skip_scope(event.skipped_scope)
        elif isinstance(event, JobErrorEvent):
            self._error(event.scope, event.error)

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
        # Scope was skipped
        self._statuses[scope] = JobScopeStatus.SKIPPED

    def _error(self, scope: JobScopeID | None, error: Exception | str) -> None:
        if scope is None:
            # Error occurred outside of scope.
            self._global_errors.append(error)
        else:
            # Add error to scope's recorded errors.
            self._scope_stack[scope].append(error)
            # If we have a running scope mark it as failing
            self._statuses[scope] = JobScopeStatus.FAILING


class JobContextState:
    """
    State that is the same for all scopes in a context.
    """

    def __init__(self, events: JobEventDispatcher | None, values: dict[str, Any] | None):
        """
        :param events: The ``JobEventDispatcher`` that the context will use to
         generate and handle events. If ``None``, a new dispatcher will be used.
        :param values: A dict of context values that will be available via
         `context.values`.
        """
        if events is None:
            events = JobDirectEventDispatcher()
        if values is None:
            values = {}
        self.events: JobEventDispatcher = events
        self.values: Values = Values(**values)

        self.scope_statuses: JobScopeStatuses = JobScopeStatuses()
        self.events.add_handler(self.scope_statuses)


class JobScopeState:
    """
    State that is specific to a specific scope.
    """

    def __init__(self) -> None:
        # Teardown actions registered ad-hoc
        self.teardown: Delegate[[JobContext], None] = Delegate(continue_on_error=True, reverse=True)
        # Futures that can be executed during this scope and will be joined before the scope exits
        self.futures: JobFutures = JobFuturesFactory.create()


class JobContextImpl(JobContext, JobEventHandler):
    """
    Concrete ``JobContext`` implementation.
    """

    def __init__(
        self,
        *,
        values: dict[str, Any] | None = None,
        events: JobEventDispatcher | None = None,
        state: JobContextState | None = None,
    ) -> None:
        """
        :param values: A dict of context values that will be available via
         `context.values`. Ignored if *state* is specified.
        :param events: The ``JobEventDispatcher`` that the context will use to
         generate and handle events instead of the dispatcher from *state*.
        :param state: A shared ``JobContextState`` to use for the context's state.
        """
        # State shared by all contexts (global)
        if state is None:
            state = JobContextState(events=events, values=values)
        self._shared_state: JobContextState = state
        # Respond to events from the events dispatcher.
        self._shared_state.events.add_handler(self)

        # State that pushes and pops with the scope.
        self._scope_stack: JobScopeStack[JobScope, JobScopeState] = JobScopeStack(default_factory=JobScopeState)

        # State that extends beyond scope boundaries but is not shared between contexts

        # Unique identifier for the context
        self._id: JobIdType = create_context_id()

        # Dispatcher that scopes executed within this context will use to generate events.
        self._local_events: JobEventDispatcher = events or self._shared_state.events
        self._status: JobStatusImpl = JobStatusImpl(self._local_events, self)

        # The interrupt used to interrupt concurrent actions running within
        # this context (set if this is a forked context).
        self._interrupt: JobInterrupt | None = None

    @property
    def id(self) -> JobIdType:
        return self._id

    def fork(self, interrupt: JobInterrupt) -> JobContextImpl:
        # Create a "local" dispatcher that the forked context will send events to.
        local_events: JobLocalEventDispatcher = JobLocalEventDispatcher(self._local_events)

        # Pass it into the constructor to override the global dispatcher
        forked: JobContextImpl = type(self)(events=local_events, state=self._shared_state)
        forked._interrupt = interrupt

        # Add forked as a handler of its own events
        local_events.add_handler(forked)

        forked._scope_stack = self._scope_stack.fork()
        forked._status = JobStatusImpl(local_events, forked)

        return forked

    def join(self) -> None:
        if isinstance(self._local_events, JobLocalEventDispatcher):
            # Flush our local events to the parent context's events (typically global).
            self._local_events.flush()
        if self._interrupt:
            # Discard the interrupt
            self._interrupt.clear()
            self._interrupt = None

    def handle(self, event: JobEvent):
        if event.context.id == self.id:
            # Only handle events generated by this context.
            if isinstance(event, JobStartScopeEvent):
                # Push the scope on the stack
                self.push_scope(self._resolve_scope(event.started_scope))
            elif isinstance(event, JobFinishScopeEvent):
                # Pop the scope off the stack
                self.pop_scope()

    def push_scope(self, scope: JobScope) -> None:
        self._scope_stack.push(scope)

    def pop_scope(self) -> JobScope:
        scope, state = self._scope_stack.pop()
        # Clean up resources
        state.futures.shutdown()
        return scope

    @property
    def scope(self) -> JobScope:
        # Return the current scope off the stack
        return self._scope_stack.peek()[0]

    @property
    def scopes(self) -> Tuple[JobScope, ...]:
        # Return all the scopes on the stack as a tuple
        return self._scope_stack.path_to(self._scope_stack.scope) if self._scope_stack else tuple()

    def add_teardown(self, scope: JobScopeID, teardown: JobCallable[None]) -> None:
        # Make sure we have a real scope, not just an ID
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

    def get_futures(self, scope: JobScopeID) -> JobFutures:
        scope = self._resolve_scope(scope)
        if not isinstance(scope, JobGroupScope):
            raise JobException(f"Scope {scope} does not support futures.")
        if scope not in self._scope_stack:
            raise JobException(f"Scope {scope} is not an active scope.")
        return self._scope_stack[scope].futures

    def get_interrupt(self) -> JobInterrupt | None:
        return self._interrupt

    def get_scope(self, scope: JobScopeID | None = None, generation: int = 0) -> JobScope | None:
        if generation == 0:
            if scope is None:
                # Return the current scope
                return self._scope_stack.get_scope()
            # Resolve the provided scope then return
            return self._resolve_scope(scope)

        scope_index: int
        scopes: list[JobScope] = list(self.scopes)
        if generation < 0:
            # Get a scope relative to the root scope
            scope_index = -1
        else:
            # Get a scope relative to the provided scope
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
            # Provided generation goes beyond the root scope.
            # This is OK. Return None.
            return None

        if scope_index >= len(scopes):
            # This is not OK.
            raise JobException(
                f"Unable to get scope relative to {'root' if generation < 0 else scope} using generation={generation}"
            )

        return scopes[scope_index]

    def _resolve_scope(self, scope_id: JobScopeID) -> JobScope:
        # Resolve a scope ID into a actual scope

        if isinstance(scope_id, JobScope):
            # Scope ID is the scope itself.
            return scope_id

        # If the JobScopeID implementation supports equality by ID, use it
        if scope_id in self._scope_stack.all_nodes:
            return self._scope_stack.all_nodes[scope_id].key  # type: ignore[index]

        # Compare scope_id.id to known scope IDs
        for scope in self._scope_stack.all_nodes:
            if scope_id.id == scope.id:
                return scope

        # scope_id is unknown
        raise JobException(f"Scope with ID '{scope_id.id}' is not known to this context.")

    @property
    def events(self) -> JobStatus:
        return self._status

    def get_report(self, scope: JobScopeID | None = None) -> dict[JobScopeID, Any]:
        return self._shared_state.scope_statuses.get_report(scope)

    def get_scope_status(self, scope: JobScopeID) -> JobScopeStatus:
        return self._shared_state.scope_statuses.get_status(scope)

    def error(self, error: str | Exception) -> Exception:
        if not isinstance(error, Exception):
            error = JobException(error)
        self.events.error(error)
        return error

    def get_errors(self, scope: JobScopeID | None = None) -> list[Exception]:
        return [
            Exception(error) if not isinstance(error, Exception) else error
            for error in self._shared_state.scope_statuses.get_errors(scope)
        ]

    @property
    def values(self) -> Values:
        return self._shared_state.values

    def __str__(self) -> str:
        return f"context({self.id})"
