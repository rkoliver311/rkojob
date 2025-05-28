# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from typing import Iterable, cast

from rkojob import (
    JobContext,
    JobContextID,
    JobEvent,
    JobEventDispatcher,
    JobEventHandler,
    JobException,
    JobScopeID,
    JobScopeStack,
    JobStatus,
    delegate,
)


class JobStartScopeEvent(JobEvent):
    type = "start_scope"

    def __init__(self, context: JobContextID, scope: JobScopeID | None, started_scope: JobScopeID) -> None:
        super().__init__(context, scope, started_scope=started_scope)

    @property
    def started_scope(self) -> JobScopeID:
        return cast(JobScopeID, self.data["started_scope"])


class JobFinishScopeEvent(JobEvent):
    type = "finish_scope"

    def __init__(self, context: JobContextID, scope: JobScopeID | None, finished_scope: JobScopeID) -> None:
        super().__init__(context, scope, finished_scope=finished_scope)

    @property
    def finished_scope(self) -> JobScopeID:
        return cast(JobScopeID, self.data["finished_scope"])


class JobErrorEvent(JobEvent):
    type = "error"

    def __init__(self, context: JobContextID, scope: JobScopeID | None, error: str | Exception) -> None:
        super().__init__(context, scope, error=error)

    @property
    def error(self) -> str | Exception:
        return self.data["error"]


class JobSkipScopeEvent(JobEvent):
    type = "skip_scope"

    def __init__(
        self, context: JobContextID, scope: JobScopeID | None, skipped_scope: JobScopeID, reason: str | None = None
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

    def __init__(self, context: JobContextID, scope: JobScopeID, section: str) -> None:
        super().__init__(context, scope, section=section)

    @property
    def section(self) -> str:
        return cast(str, self.data["section"])


class JobFinishSectionEvent(JobEvent):
    type = "finish_section"

    def __init__(self, context: JobContextID, scope: JobScopeID, section: str) -> None:
        super().__init__(context, scope, section=section)

    @property
    def section(self) -> str:
        return cast(str, self.data["section"])


class JobStartItemEvent(JobEvent):
    type = "start_item"

    def __init__(self, context: JobContextID, scope: JobScopeID, item: str) -> None:
        super().__init__(context, scope, item=item)

    @property
    def item(self) -> str:
        return cast(str, self.data["item"])


class JobFinishItemEvent(JobEvent):
    type = "finish_item"

    def __init__(self, context: JobContextID, scope: JobScopeID, outcome: str) -> None:
        super().__init__(context, scope, outcome=outcome)

    @property
    def outcome(self) -> str:
        return cast(str, self.data["outcome"])


class JobWarningEvent(JobEvent):
    type = "warning"

    def __init__(self, context: JobContextID, scope: JobScopeID, warning: str | Exception) -> None:
        super().__init__(context, scope, warning=warning)

    @property
    def warning(self) -> str | Exception:
        return self.data["warning"]


class JobInfoEvent(JobEvent):
    type = "info"

    def __init__(self, context: JobContextID, scope: JobScopeID, message: str) -> None:
        super().__init__(context, scope, message=message)

    @property
    def message(self) -> str:
        return self.data["message"]


class JobDetailEvent(JobEvent):
    type = "detail"

    def __init__(self, context: JobContextID, scope: JobScopeID, message: str) -> None:
        super().__init__(context, scope, message=message)

    @property
    def message(self) -> str:
        return self.data["message"]


class JobOutputEvent(JobEvent):
    type = "output"

    def __init__(
        self, context: JobContextID, scope: JobScopeID, output: str | Iterable[str], label: str | None = None
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
        self._scopes: JobScopeStack[JobScopeID, None] = JobScopeStack()

    def handle(self, event: JobEvent) -> None:
        self._handler.handle(event)

    def start_scope(self, scope: JobScopeID) -> None:
        self.handle(JobStartScopeEvent(self._context.id, self._scopes.get_scope(), started_scope=scope))
        self._scopes.push(scope)

    def finish_scope(self, scope: JobScopeID | None = None) -> None:
        scope, _ = self._scopes.pop()
        self.handle(JobFinishScopeEvent(self._context.id, self._scopes.get_scope(), finished_scope=scope))

    def skip_scope(self, scope: JobScopeID, reason: str | None = None) -> None:
        self.handle(JobSkipScopeEvent(self._context.id, self._scopes.get_scope(), skipped_scope=scope, reason=reason))

    def start_section(self, section: str) -> None:
        self.handle(JobStartSectionEvent(self._context.id, self._scopes.scope, section=section))

    def finish_section(self, section: str) -> None:
        self.handle(JobFinishSectionEvent(self._context.id, self._scopes.scope, section=section))

    def start_item(self, item: str) -> None:
        self.handle(JobStartItemEvent(self._context.id, self._scopes.scope, item=item))

    def finish_item(self, outcome: str = "done.", error: str | Exception | None = None) -> None:
        if error:
            self.error(error)
        self.handle(JobFinishItemEvent(self._context.id, self._scopes.scope, outcome=outcome))

    def info(self, message: str) -> None:
        self.handle(JobInfoEvent(self._context.id, self._scopes.scope, message=message))

    def detail(self, message: str) -> None:
        self.handle(JobDetailEvent(self._context.id, self._scopes.scope, message=message))

    def warning(self, warning: str | Exception) -> None:
        self.handle(JobWarningEvent(self._context.id, self._scopes.scope, warning=warning))

    def error(self, error: str | Exception) -> None:
        self.handle(JobErrorEvent(self._context.id, self._scopes.scope, error=error))

    def output(self, output: str | Iterable[str], label: str | None = None) -> None:
        self.handle(JobOutputEvent(self._context.id, self._scopes.scope, output=output, label=label))


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
