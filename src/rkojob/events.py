# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

"""
Standard `JobEvent` types and useful event related implementations.
"""

from threading import RLock
from typing import Callable, Iterable, cast

from rkojob import (
    JobContext,
    JobEvent,
    JobEventDispatcher,
    JobEventHandler,
    JobException,
    JobScopeID,
    JobStatus,
    delegate,
)


class JobForkContextEvent(JobEvent):
    """Event indicating that a context has been forked."""

    def __init__(self, context: JobContext, scope: JobScopeID | None, forked_context: JobContext) -> None:
        """
        :param context: The "parent" context.
        :param scope: The current scope of the "parent" context.
        :param forked_context: The new context that was forked off of the
         "parent" context.
        """
        super().__init__("fork_context", context, scope, forked_context=forked_context)

    @property
    def forked_context(self) -> JobContext:
        """:returns: The forked context."""
        return cast(JobContext, self.data["forked_context"])


class JobJoinContextEvent(JobEvent):
    """Event indicating that a forked context has been joined."""

    def __init__(self, context: JobContext, scope: JobScopeID | None, joined_context: JobContext) -> None:
        """
        :param context: The "parent" context.
        :param scope: The current scope of the "parent" context.
        :param joined_context: The previously forked context that has been
         joined.
        """
        super().__init__("join_context", context, scope, joined_context=joined_context)

    @property
    def joined_context(self) -> JobContext:
        """:returns: The joined context."""
        return cast(JobContext, self.data["joined_context"])


class JobStartScopeEvent(JobEvent):
    """Event indicating that a scope has been started."""

    def __init__(self, context: JobContext, scope: JobScopeID | None, started_scope: JobScopeID) -> None:
        """
        :param context: The current context.
        :param scope: The parent scope the started scope. May be `None` if
         `started_scope` has no parent.
        :param started_scope: The started scope.
        """
        super().__init__("start_scope", context, scope, started_scope=started_scope)

    @property
    def started_scope(self) -> JobScopeID:
        """:returns: The started scope."""
        return cast(JobScopeID, self.data["started_scope"])


class JobFinishScopeEvent(JobEvent):
    """Event indicating that a scope has finished."""

    def __init__(self, context: JobContext, scope: JobScopeID | None, finished_scope: JobScopeID) -> None:
        """
        :param context: The current context.
        :param scope: The parent scope the finished scope. May be `None` if
         `finished_scope` has no parent.
        :param finished_scope: The finished scope.
        """
        super().__init__("finish_scope", context, scope, finished_scope=finished_scope)

    @property
    def finished_scope(self) -> JobScopeID:
        """:returns: The finished scope."""
        return cast(JobScopeID, self.data["finished_scope"])


class JobSkipScopeEvent(JobEvent):
    """Event indicating that a scope has been skipped."""

    def __init__(
        self, context: JobContext, scope: JobScopeID | None, skipped_scope: JobScopeID, reason: str | None = None
    ) -> None:
        """
        :param context: The current context.
        :param scope: The parent scope the skipped scope. May be `None` if
         `skipped_scope` has no parent.
        :param skipped_scope: The scope that has been skipped.
        :param reason: The optional reason that the scope was skipped.
        """
        super().__init__("skip_scope", context, scope, skipped_scope=skipped_scope, reason=reason)

    @property
    def skipped_scope(self) -> JobScopeID:
        """:returns: The skipped scope."""
        return cast(JobScopeID, self.data["skipped_scope"])

    @property
    def reason(self) -> str | None:
        """:returns: The optional reason that the scope was skipped."""
        return self.data.get("reason")


class JobStartScopeTeardownEvent(JobEvent):
    """Event indicating that scope teardown has been started."""

    def __init__(self, context: JobContext, scope: JobScopeID) -> None:
        """
        :param context: The current context.
        :param scope: The scope being torn down.
        """
        super().__init__("start_scope_teardown", context, scope)


class JobFinishScopeTeardownEvent(JobEvent):
    """Event indicating that scope teardown has finished."""

    def __init__(self, context: JobContext, scope: JobScopeID) -> None:
        """
        :param context: The current context.
        :param scope: The scope that has been torn down.
        """
        super().__init__("finish_scope_teardown", context, scope)


class JobStartSectionEvent(JobEvent):
    """Event indicating that a section has been started."""

    def __init__(self, context: JobContext, scope: JobScopeID, section: str) -> None:
        """
        :param context: The current context.
        :param scope: The current scope.
        :param section: The started section.
        """
        super().__init__("start_section", context, scope, section=section)

    @property
    def section(self) -> str:
        """:returns: The started section."""
        return cast(str, self.data["section"])


class JobFinishSectionEvent(JobEvent):
    """Event indicating that a section has been finished."""

    def __init__(self, context: JobContext, scope: JobScopeID, section: str) -> None:
        """
        :param context: The current context.
        :param scope: The current scope.
        :param section: The finished section.
        """
        super().__init__("finish_section", context, scope, section=section)

    @property
    def section(self) -> str:
        """:returns: The finished section."""
        return cast(str, self.data["section"])


class JobStartItemEvent(JobEvent):
    """Event indicating that an item has been started."""

    def __init__(self, context: JobContext, scope: JobScopeID, item: str) -> None:
        """
        :param context: The current context.
        :param scope: The current scope.
        :param item: The started item.
        """
        super().__init__("start_item", context, scope, item=item)

    @property
    def item(self) -> str:
        """:returns: The started item."""
        return cast(str, self.data["item"])


class JobFinishItemEvent(JobEvent):
    """Event indicating that an item has been finished."""

    def __init__(self, context: JobContext, scope: JobScopeID, outcome: str) -> None:
        """
        :param context: The current context.
        :param scope: The current scope.
        :param outcome: The outcome of the finished item.
        """
        super().__init__("finish_item", context, scope, outcome=outcome)

    @property
    def outcome(self) -> str:
        """:returns: The outcome of the finished item."""
        return cast(str, self.data["outcome"])


class JobInfoEvent(JobEvent):
    """Event containing an informational message."""

    def __init__(self, context: JobContext, scope: JobScopeID, message: str) -> None:
        """
        :param context: The current context.
        :param scope: The current scope.
        :param message: The informational message.
        """
        super().__init__("info", context, scope, message=message)

    @property
    def message(self) -> str:
        """:returns: The informational message."""
        return self.data["message"]


class JobDetailEvent(JobEvent):
    """Event containing a detailed message."""

    def __init__(self, context: JobContext, scope: JobScopeID, message: str) -> None:
        """
        :param context: The current context.
        :param scope: The current scope.
        :param message: The detailed message.
        """
        super().__init__("detail", context, scope, message=message)

    @property
    def message(self) -> str:
        """:returns: The detailed message."""
        return self.data["message"]


class JobErrorEvent(JobEvent):
    """Event indicating that an error has occurred."""

    def __init__(self, context: JobContext, scope: JobScopeID | None, error: str | Exception) -> None:
        """
        :param context: The current context.
        :param scope: The current scope. May be `None`.
        :param error: The error.
        """
        super().__init__("error", context, scope, error=error)

    @property
    def error(self) -> str | Exception:
        """:returns: The error."""
        return self.data["error"]


class JobWarningEvent(JobEvent):
    """Event indicating that a warning has occurred."""

    def __init__(self, context: JobContext, scope: JobScopeID, warning: str | Exception) -> None:
        """
        :param context: The current context.
        :param scope: The current scope.
        :param warning: The warning.
        """
        super().__init__("warning", context, scope, warning=warning)

    @property
    def warning(self) -> str | Exception:
        """:returns: The warning."""
        return self.data["warning"]


class JobOutputEvent(JobEvent):
    """Event containing the output of a command."""

    def __init__(
        self, context: JobContext, scope: JobScopeID, output: str | Iterable[str], label: str | None = None
    ) -> None:
        """
        :param context: The current context.
        :param scope: The current scope.
        :param output: The output.
        :param label: Optional label of the output.
        """
        super().__init__("output", context, scope, output=output, label=label or "output")

    @property
    def output(self) -> str | Iterable[str]:
        """:returns: The output."""
        return self.data["output"]

    @property
    def label(self) -> str:
        """:returns: Optional label of the output."""
        return self.data["label"]


class JobStatusImpl(JobStatus):
    """
    Concrete implementation of `JobStatus` used to send well-known job events
    to a handler.
    """

    def __init__(self, handler: JobEventHandler, context: JobContext) -> None:
        self._handler: JobEventHandler = handler
        self._context: JobContext = context

    def handle(self, event: JobEvent) -> None:
        self._handler.handle(event)

    def add_handler(self, handler: JobEventHandler) -> None:
        if not isinstance(self._handler, JobEventDispatcher):
            raise JobException("Wrapped handler is not an event dispatcher.")
        self._handler.add_handler(handler)

    def remove_handler(self, handler: JobEventHandler) -> None:
        if not isinstance(self._handler, JobEventDispatcher):
            raise JobException("Wrapped handler is not an event dispatcher.")
        self._handler.remove_handler(handler)

    def fork_context(self, context: JobContext) -> None:
        self.handle(JobForkContextEvent(self._context, self._context.get_scope(), forked_context=context))

    def join_context(self, context: JobContext) -> None:
        self.handle(JobJoinContextEvent(self._context, self._context.get_scope(), joined_context=context))

    def start_scope(self, scope: JobScopeID) -> None:
        self.handle(JobStartScopeEvent(self._context, self._context.get_scope(), started_scope=scope))

    def start_scope_teardown(self, scope: JobScopeID | None = None) -> None:
        if scope is None:
            scope = self._context.scope
        self.handle(JobStartScopeTeardownEvent(self._context, scope))

    def finish_scope_teardown(self, scope: JobScopeID | None = None) -> None:
        if scope is None:
            scope = self._context.scope
        self.handle(JobFinishScopeTeardownEvent(self._context, scope))

    def finish_scope(self, scope: JobScopeID | None = None) -> None:
        if scope is None:
            scope = self._context.scope
        self.handle(
            JobFinishScopeEvent(self._context, self._context.get_scope(scope, generation=1), finished_scope=scope)
        )

    def skip_scope(self, scope: JobScopeID, reason: str | None = None) -> None:
        self.handle(JobSkipScopeEvent(self._context, self._context.get_scope(), skipped_scope=scope, reason=reason))

    def start_section(self, section: str) -> None:
        self.handle(JobStartSectionEvent(self._context, self._context.scope, section=section))

    def finish_section(self, section: str) -> None:
        self.handle(JobFinishSectionEvent(self._context, self._context.scope, section=section))

    def start_item(self, item: str) -> None:
        self.handle(JobStartItemEvent(self._context, self._context.scope, item=item))

    def finish_item(self, outcome: str = "done.", error: str | Exception | None = None) -> None:
        if error:
            self.error(error)
        self.handle(JobFinishItemEvent(self._context, self._context.scope, outcome=outcome))

    def info(self, message: str) -> None:
        self.handle(JobInfoEvent(self._context, self._context.scope, message=message))

    def detail(self, message: str) -> None:
        self.handle(JobDetailEvent(self._context, self._context.scope, message=message))

    def warning(self, warning: str | Exception) -> None:
        self.handle(JobWarningEvent(self._context, self._context.scope, warning=warning))

    def error(self, error: str | Exception) -> None:
        self.handle(JobErrorEvent(self._context, self._context.scope, error=error))

    def output(self, output: str | Iterable[str], label: str | None = None) -> None:
        self.handle(JobOutputEvent(self._context, self._context.scope, output=output, label=label))


class JobDirectEventDispatcher(JobEventDispatcher):
    """
    A `JobEventDispatcher` implementation that forwards all events to zero or
    more handlers.
    """

    def add_handler(self, handler: JobEventHandler) -> None:
        """
        Add a handler as an event destination.
        :param handler: The handler to add as an event destination.
        """
        self._handle += handler.handle

    def remove_handler(self, handler: JobEventHandler) -> None:
        """
        Remove a handler as an event destination.
        :param handler: The handler to remove as an event destination.
        """
        self._handle -= handler.handle

    # This decorated method is the delegate that handlers are added to.
    # When this delegate is called, all registered handlers are called
    # with the provided event. (See the `handle` implementation below).
    @delegate(continue_on_error=True)
    def _handle(self, event: JobEvent) -> None: ...

    def handle(self, event: JobEvent) -> None:
        # Call the `_handle` delegate which calls `handle` on all our
        # registered handlers, returning a list with the value, or exception,
        # returned by each handler.
        results: list[Exception | None] = self._handle(event)
        # Determine if any of the handlers raised an exception
        errors: list[Exception] = [result for result in results if isinstance(result, Exception)]
        if errors:
            if len(errors) == 1:
                # If only one error occurred, raise that error.
                raise errors[0]
            # If multiple errors occurred, raise a single exception including
            # all the error messages.
            raise JobException(f"Handle event failed: {errors}")


class JobBufferedEventHandler(JobEventHandler):
    """
    A `JobEventHandler` implementation that buffers handled events and flushes
    them to another handler when a certain number of events have been buffered
    or when `flush` is called.
    """

    def __init__(self, handler: JobEventHandler, size: int = -1) -> None:
        """
        :param handler: The handler to wrap and flush events to.
        :param size: Optional max size of the number of events to buffer.
         A value of `0` disables buffering. A value of `-1` disables automatic
         flushing.
        """
        self._handler: JobEventHandler = handler
        self._size: int = size
        self._events: list[JobEvent] = []
        self._lock: RLock = RLock()

    def handle(self, event: JobEvent) -> None:
        """
        Handle the event by adding it to the buffer. If the number of buffered
        events exceeds the buffer size, and auto-flushing is enabled, `flush`
        will be called.

        :param event: The event to buffer.
        """
        with self._lock:
            self._events.append(event)
            if 0 <= self._size < len(self._events):
                self.flush()

    def flush(self) -> None:
        """
        Flush the currently buffered events to the wrapped event handler.
        """
        with self._lock:
            for event in self._events:
                self._handler.handle(event)
            self._events.clear()


class JobLocalEventDispatcher(JobEventDispatcher):
    """
    A `JobEventDispatcher` implementation that buffers events to be flushed
    later to a wrapped handler. Handler's that are added to this dispatcher
    receive events immediately. This allows events to be handled by a "local"
    set of handlers and later flushed to a broader audience. For example, a
    forked context will send events to a `JobLocalEventDispatcher` to be
    flushed to the global dispatcher when the context is joined.
    """

    def __init__(self, flush_to: JobEventHandler) -> None:
        """
        :param flush_to: The `JobEventHandler` to flush events to.
        """
        self._buffer: JobBufferedEventHandler = JobBufferedEventHandler(flush_to)
        self._events: JobEventDispatcher = JobDirectEventDispatcher()
        self._events.add_handler(self._buffer)

    def handle(self, event: JobEvent):
        self._events.handle(event)

    def add_handler(self, handler: JobEventHandler) -> None:
        """
        Add a handler as a local event destination. Events will be forwarded
        immediately to this handler, not buffered.
        :param handler: The handler to add as a local event destination.
        """
        self._events.add_handler(handler)

    def remove_handler(self, handler: JobEventHandler) -> None:
        """
        Remove a handler as a local event destination.
        :param handler: The handler to remove as a local event destination.
        """
        self._events.remove_handler(handler)

    def flush(self) -> None:
        """Flush local events to the wrapped handler."""
        self._buffer.flush()


JobEventRoutePredicate = Callable[[JobEvent], bool]


class JobRoutingEventDispatcher(JobEventDispatcher):
    """
    A `JobEventDispatcher` implementation that routes events to other handlers
    based on a routing predicate, `(JobEvent) -> bool`. If the predicate
    associated with the handler returns `True`, the event is forwarded to the
    handler.
    """

    ALWAYS: JobEventRoutePredicate = lambda _: True

    def __init__(self) -> None:
        self._routes: dict[JobEventRoutePredicate, JobEventDispatcher] = {}

    def add_handler(self, handler: JobEventHandler, predicate: JobEventRoutePredicate | None = None) -> None:
        """
        Add a handler to the dispatcher with the optional routing predicate.

        :param handler: The handler to add as an event destination.
        :param predicate: The optional routing predicate. Events will only be
         routed to this handler if it evaluates to `True` for the event. If not
         provided, all events will be forwarded to the handler.
        """
        if predicate is None:
            predicate = JobRoutingEventDispatcher.ALWAYS
        if predicate not in self._routes:
            self._routes[predicate] = JobDirectEventDispatcher()
        self._routes[predicate].add_handler(handler)

    def remove_handler(self, handler: JobEventHandler, predicate: JobEventRoutePredicate | None = None) -> None:
        """
        Remove a handler from the dispatcher for the optional routing predicate.

        :param handler: The handler to remove as an event destination.
        :param predicate: The routing predicate the event was added with.
        """
        if predicate is None:
            predicate = JobRoutingEventDispatcher.ALWAYS
        if predicate in self._routes:
            self._routes[predicate].remove_handler(handler)

    def handle(self, event: JobEvent) -> None:
        """
        Handle the event by routing it to registered handlers.

        :param event: The event to route.
        """
        for predicate, dispatcher in self._routes.items():
            if predicate(event):
                dispatcher.handle(event)
