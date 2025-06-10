# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

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
    type = "fork_context"

    def __init__(self, context: JobContext, scope: JobScopeID | None, forked_context: JobContext) -> None:
        super().__init__(context, scope, forked_context=forked_context)

    @property
    def forked_context(self) -> JobContext:
        return cast(JobContext, self.data["forked_context"])


class JobJoinContextEvent(JobEvent):
    type = "join_context"

    def __init__(self, context: JobContext, scope: JobScopeID | None, joined_context: JobContext) -> None:
        super().__init__(context, scope, joined_context=joined_context)

    @property
    def joined_context(self) -> JobContext:
        return cast(JobContext, self.data["joined_context"])


class JobStartScopeEvent(JobEvent):
    type = "start_scope"

    def __init__(self, context: JobContext, scope: JobScopeID | None, started_scope: JobScopeID) -> None:
        super().__init__(context, scope, started_scope=started_scope)

    @property
    def started_scope(self) -> JobScopeID:
        return cast(JobScopeID, self.data["started_scope"])


class JobStartScopeTeardownEvent(JobEvent):
    type = "start_scope_teardown"

    def __init__(self, context: JobContext, scope: JobScopeID) -> None:
        super().__init__(context, scope)


class JobFinishScopeTeardownEvent(JobEvent):
    type = "finish_scope_teardown"

    def __init__(self, context: JobContext, scope: JobScopeID) -> None:
        super().__init__(context, scope)


class JobFinishScopeEvent(JobEvent):
    type = "finish_scope"

    def __init__(self, context: JobContext, scope: JobScopeID | None, finished_scope: JobScopeID) -> None:
        super().__init__(context, scope, finished_scope=finished_scope)

    @property
    def finished_scope(self) -> JobScopeID:
        return cast(JobScopeID, self.data["finished_scope"])


class JobErrorEvent(JobEvent):
    type = "error"

    def __init__(self, context: JobContext, scope: JobScopeID | None, error: str | Exception) -> None:
        super().__init__(context, scope, error=error)

    @property
    def error(self) -> str | Exception:
        return self.data["error"]


class JobSkipScopeEvent(JobEvent):
    type = "skip_scope"

    def __init__(
        self, context: JobContext, scope: JobScopeID | None, skipped_scope: JobScopeID, reason: str | None = None
    ) -> None:
        super().__init__(context, scope, skipped_scope=skipped_scope, reason=reason)

    @property
    def skipped_scope(self) -> JobScopeID:
        return cast(JobScopeID, self.data["skipped_scope"])

    @property
    def reason(self) -> str | None:
        return self.data.get("reason")


class JobStartSectionEvent(JobEvent):
    type = "start_section"

    def __init__(self, context: JobContext, scope: JobScopeID, section: str) -> None:
        super().__init__(context, scope, section=section)

    @property
    def section(self) -> str:
        return cast(str, self.data["section"])


class JobFinishSectionEvent(JobEvent):
    type = "finish_section"

    def __init__(self, context: JobContext, scope: JobScopeID, section: str) -> None:
        super().__init__(context, scope, section=section)

    @property
    def section(self) -> str:
        return cast(str, self.data["section"])


class JobStartItemEvent(JobEvent):
    type = "start_item"

    def __init__(self, context: JobContext, scope: JobScopeID, item: str) -> None:
        super().__init__(context, scope, item=item)

    @property
    def item(self) -> str:
        return cast(str, self.data["item"])


class JobFinishItemEvent(JobEvent):
    type = "finish_item"

    def __init__(self, context: JobContext, scope: JobScopeID, outcome: str) -> None:
        super().__init__(context, scope, outcome=outcome)

    @property
    def outcome(self) -> str:
        return cast(str, self.data["outcome"])


class JobWarningEvent(JobEvent):
    type = "warning"

    def __init__(self, context: JobContext, scope: JobScopeID, warning: str | Exception) -> None:
        super().__init__(context, scope, warning=warning)

    @property
    def warning(self) -> str | Exception:
        return self.data["warning"]


class JobInfoEvent(JobEvent):
    type = "info"

    def __init__(self, context: JobContext, scope: JobScopeID, message: str) -> None:
        super().__init__(context, scope, message=message)

    @property
    def message(self) -> str:
        return self.data["message"]


class JobDetailEvent(JobEvent):
    type = "detail"

    def __init__(self, context: JobContext, scope: JobScopeID, message: str) -> None:
        super().__init__(context, scope, message=message)

    @property
    def message(self) -> str:
        return self.data["message"]


class JobOutputEvent(JobEvent):
    type = "output"

    def __init__(
        self, context: JobContext, scope: JobScopeID, output: str | Iterable[str], label: str | None = None
    ) -> None:
        super().__init__(context, scope, output=output, label=label or "output")

    @property
    def output(self) -> str | Iterable[str]:
        return self.data["output"]

    @property
    def label(self) -> str:
        return self.data["label"]


class JobStatusImpl(JobStatus):
    """
    Convenience class used to send well-known job events to a handler.
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
    def add_handler(self, handler: JobEventHandler) -> None:
        self._delegate += handler.handle

    def remove_handler(self, handler: JobEventHandler) -> None:
        self._delegate -= handler.handle

    @delegate(continue_on_error=True)
    def _delegate(self, event: JobEvent) -> None: ...

    def handle(self, event: JobEvent) -> None:
        results: list[Exception | None] = self._delegate(event)
        errors: list[Exception] = [result for result in results if isinstance(result, Exception)]
        if errors:
            if len(errors) == 1:
                raise errors[0]
            raise JobException(f"Handle event failed: {errors}")


class JobBufferedEventHandler(JobEventHandler):
    def __init__(self, handler: JobEventHandler, size: int = -1) -> None:
        self._handler: JobEventHandler = handler
        self._size: int = size
        self._events: list[JobEvent] = []
        self._lock: RLock = RLock()

    def handle(self, event: JobEvent) -> None:
        with self._lock:
            self._events.append(event)
            if 0 <= self._size < len(self._events):
                self.flush()

    def flush(self) -> None:
        with self._lock:
            for event in self._events:
                self._handler.handle(event)
            self._events.clear()


class JobLocalEventDispatcher(JobEventDispatcher):
    def __init__(self, flush_to: JobEventHandler) -> None:
        self._buffer: JobBufferedEventHandler = JobBufferedEventHandler(flush_to)
        self._events: JobEventDispatcher = JobDirectEventDispatcher()
        self._events.add_handler(self._buffer)

    def handle(self, event: JobEvent):
        self._events.handle(event)

    def add_handler(self, handler: JobEventHandler) -> None:
        self._events.add_handler(handler)

    def remove_handler(self, handler: JobEventHandler) -> None:
        self._events.remove_handler(handler)

    def flush(self) -> None:
        self._buffer.flush()


JobEventRoutePredicate = Callable[[JobEvent], bool]


class JobRoutingEventDispatcher(JobEventDispatcher):
    ALWAYS: JobEventRoutePredicate = lambda _: True

    def __init__(self) -> None:
        self._routes: dict[JobEventRoutePredicate, JobEventDispatcher] = {}

    def add_handler(self, handler: JobEventHandler, predicate: JobEventRoutePredicate | None = None) -> None:
        if predicate is None:
            predicate = JobRoutingEventDispatcher.ALWAYS
        if predicate not in self._routes:
            self._routes[predicate] = JobDirectEventDispatcher()
        self._routes[predicate].add_handler(handler)

    def remove_handler(self, handler: JobEventHandler, predicate: JobEventRoutePredicate | None = None) -> None:
        if predicate is None:
            predicate = JobRoutingEventDispatcher.ALWAYS
        if predicate in self._routes:
            self._routes[predicate].remove_handler(handler)

    def handle(self, event: JobEvent) -> None:
        for predicate, dispatcher in self._routes.items():
            if predicate(event):
                dispatcher.handle(event)
