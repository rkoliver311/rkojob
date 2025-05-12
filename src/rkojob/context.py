from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import (
    Any,
    ClassVar,
    Final,
    Generator,
    Generic,
    Iterable,
    TextIO,
    Tuple,
    TypeVar,
)

from rkojob import (
    JobBaseStatus,
    JobException,
    JobScope,
    JobScopeStatus,
    JobStatus,
    JobStatusCollector,
    Values,
)


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


# TODO: Replace with subclasses?
class JobStatusWriterPair(Enum):
    SCOPE = auto()
    SECTION = auto()
    ITEM = auto()


T = TypeVar("T")


class JobStatusWriterEvent(Generic[T]):
    pair_type: ClassVar[JobStatusWriterPair | None] = None
    is_start: ClassVar[bool] = False
    prefix: ClassVar[str] = "\n\n"
    suffix: ClassVar[str] = "\n\n"

    def __init__(
        self,
        event: T,
        start: datetime | None = None,
    ):
        self.event: T = event
        self.start: datetime | None = start

    def write_event(
        self,
        stream: TextIO,
        depth: int = 0,
        prev_event: JobStatusWriterEvent | None = None,
        duration: timedelta | None = None,
    ) -> None:
        self._write_prefix(stream, prev_event=prev_event)
        self._write_indent(stream, depth, prev_event=prev_event)
        self._write_event(stream, depth, duration=None if self.is_start else duration)
        self._write_suffix(stream)

    def _write_prefix(self, stream: TextIO, prev_event: JobStatusWriterEvent | None) -> None:
        if not prev_event:
            return
        if not prev_event.suffix.endswith(self.prefix):
            separator: str = self.prefix.removeprefix(prev_event.suffix)
            stream.write(separator)

    def _write_indent(self, stream: TextIO, depth: int, prev_event: JobStatusWriterEvent | None = None) -> None:
        pass

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(str(self.event))
        self._write_duration(stream, duration=duration)

    def _write_duration(self, stream: TextIO, duration: timedelta | None) -> None:
        if duration:
            stream.write(f" ({self._format_duration(duration)})")

    def _write_suffix(self, stream: TextIO) -> None:
        stream.write(self.suffix)

    @staticmethod
    def _format_duration(duration: timedelta) -> str:
        # 12h34m56.123s
        millis = int(duration.microseconds / 1000)
        seconds = duration.seconds
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        hours += duration.days * 24
        if hours != 0:
            return f"{hours}h{minutes}m"
        if minutes != 0:
            return f"{minutes}m{seconds}s"
        if seconds > 4:
            return f"{seconds}s"
        if seconds == 0 and millis == 0:
            return "0s"
        return f"{seconds}.{millis:03d}s"


class ScopeStartEvent(JobStatusWriterEvent[JobScope]):
    pair_type = JobStatusWriterPair.SCOPE
    is_start = True

    def __init__(self, scope: JobScope, start: datetime | None = None) -> None:
        super().__init__(scope, start=start)

    def _write_indent(self, stream: TextIO, depth: int, prev_event: JobStatusWriterEvent | None = None) -> None:
        stream.write("#" + "#" * depth + " ")

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"{self.event.type} {self.event.name}")


class ScopeFinishEvent(JobStatusWriterEvent[JobScope]):
    pair_type = JobStatusWriterPair.SCOPE

    def __init__(self, scope: JobScope) -> None:
        super().__init__(scope)

    def _write_indent(self, stream: TextIO, depth: int, prev_event: JobStatusWriterEvent | None = None) -> None:
        stream.write("\u2705 ")

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"Finished **{self.event.type} {self.event.name}**")
        self._write_duration(stream, duration)


class ScopeFinishErrorEvent(JobStatusWriterEvent[JobScope]):
    pair_type = JobStatusWriterPair.SCOPE

    def __init__(self, scope: JobScope, error: str | Exception) -> None:
        super().__init__(scope)
        self.error: str | Exception = error

    def _write_indent(self, stream: TextIO, depth: int, prev_event: JobStatusWriterEvent | None = None) -> None:
        stream.write("\u274c ")

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"Finished **{self.event.type} {self.event.name}**")
        self._write_duration(stream, duration)
        stream.write(f"\n\u274c {self.error}")


class ScopeFinishErrorsEvent(JobStatusWriterEvent[JobScope]):
    pair_type = JobStatusWriterPair.SCOPE

    def __init__(self, scope: JobScope, errors: list[str | Exception]) -> None:
        super().__init__(scope)
        self.errors: list[str | Exception] = errors

    def _write_indent(self, stream: TextIO, depth: int, prev_event: JobStatusWriterEvent | None = None) -> None:
        stream.write("\u274c ")

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"Finished **{self.event.type} {self.event.name}**")
        self._write_duration(stream, duration)
        for error in self.errors:
            stream.write(f"\n - \u274c {error}")


class ScopeSkippedEvent(JobStatusWriterEvent[JobScope]):
    def __init__(self, scope: JobScope, reason: str | None = None) -> None:
        super().__init__(scope)
        self.reason: str | None = reason

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"**Skipping {self.event.type} {self.event.name}")
        if self.reason:
            stream.write(f" ({self.reason})")
        stream.write("**")


class SectionStartEvent(JobStatusWriterEvent[str]):
    pair_type = JobStatusWriterPair.SECTION
    is_start = True

    def __init__(self, name: str, start: datetime | None = None) -> None:
        super().__init__(name, start=start)

    def _write_indent(self, stream: TextIO, depth: int, prev_event: JobStatusWriterEvent | None = None) -> None:
        stream.write("#" + "#" * depth + " ")


class SectionFinishEvent(JobStatusWriterEvent[str]):
    pair_type = JobStatusWriterPair.SECTION

    def __init__(self, name: str) -> None:
        super().__init__(name)

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"Finished **{self.event}**")
        self._write_duration(stream, duration)


class SectionFinishErrorEvent(JobStatusWriterEvent[str]):
    pair_type = JobStatusWriterPair.SECTION

    def __init__(self, name: str, error: str | Exception) -> None:
        super().__init__(name)
        self.error: str | Exception = error

    def _write_indent(self, stream: TextIO, depth: int, prev_event: JobStatusWriterEvent | None = None) -> None:
        stream.write("\u274c ")

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"Finished **{self.event}**")
        self._write_duration(stream, duration)
        stream.write(f"\n\u274c {self.error}")


class SectionFinishErrorsEvent(JobStatusWriterEvent[str]):
    pair_type = JobStatusWriterPair.SECTION

    def __init__(self, name: str, errors: list[str | Exception]) -> None:
        super().__init__(name)
        self.errors: list[str | Exception] = errors

    def _write_indent(self, stream: TextIO, depth: int, prev_event: JobStatusWriterEvent | None = None) -> None:
        stream.write("\u274c ")

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"\u274c Finished **{self.event}**")
        self._write_duration(stream, duration)
        for error in self.errors:
            stream.write(f"\n\u274c {error}")


class ItemStartEvent(JobStatusWriterEvent[str]):
    pair_type = JobStatusWriterPair.ITEM
    is_start = True
    prefix = "\n"
    suffix = ""

    def __init__(self, event: str, start: datetime | None = None) -> None:
        super().__init__(event, start=start)

    def _write_indent(self, stream: TextIO, depth: int, prev_event: JobStatusWriterEvent | None = None) -> None:
        stream.write("  " * depth + " - ")

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"{self.event}...")


class ItemFinishEvent(JobStatusWriterEvent[str]):
    pair_type = JobStatusWriterPair.ITEM
    prefix = ""
    suffix = "\n"

    def __init__(self, outcome: str = "done.") -> None:
        super().__init__(outcome)

    def _write_indent(self, stream: TextIO, depth: int, prev_event: JobStatusWriterEvent | None = None) -> None:
        if not isinstance(prev_event, ItemStartEvent):
            stream.write("   " * depth)


class ItemFinishErrorEvent(JobStatusWriterEvent[str | Exception]):
    pair_type = JobStatusWriterPair.ITEM
    prefix = ""
    suffix = "\n"

    def __init__(self, error: str | Exception) -> None:
        super().__init__(error)

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"\u274c {self.event}")
        self._write_duration(stream, duration)


class ItemFinishErrorsEvent(JobStatusWriterEvent[list[str | Exception]]):
    pair_type = JobStatusWriterPair.ITEM
    prefix = ""
    suffix = "\n"

    def __init__(self, errors: list[str | Exception]) -> None:
        super().__init__(errors)

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write("\u274c")
        self._write_duration(stream, duration)
        for error in self.event:
            stream.write(f"\n{'  ' * depth} - \u274c {error}")


class MessageEvent(JobStatusWriterEvent[str]):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class ErrorEvent(JobStatusWriterEvent[str | Exception]):
    def __init__(self, error: str | Exception) -> None:
        super().__init__(error)

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"\u274c {self.event}")


class OutputEvent(JobStatusWriterEvent[str | Iterable[str]]):
    def __init__(self, output: str | Iterable[str], label: str) -> None:
        super().__init__(output)
        self.label: str = label

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"{self.label}:\n")
        output: str | Iterable[str] = self.event
        if isinstance(output, str):
            output = [output]
        for line in output:
            if line.endswith("\n"):
                line = line[:-1]
            for subline in line.split("\n"):
                stream.write(f"\n    {subline}")


class JobStatusWriter(JobStatus):
    WARNING_CHAR: Final[str] = "⚠️"
    DETAIL_CHAR: Final[str] = "🔎"

    def __init__(
        self,
        stream: TextIO,
        show_detail: bool = True,
    ) -> None:
        self._show_detail: bool = show_detail
        self._stream: TextIO = stream
        self._event_stack: list[JobStatusWriterEvent] = []

    def _write_event_and_append(self, event: JobStatusWriterEvent) -> None:
        prev_event: JobStatusWriterEvent | None = self._event_stack[-1] if self._event_stack else None
        duration: timedelta | None = None
        if event.pair_type is not None and not event.is_start:
            start_event: JobStatusWriterEvent = self._find_start_event(type(event))
            if start_event.start:
                duration = datetime.now() - start_event.start
        depth: int
        if event.pair_type in (JobStatusWriterPair.SCOPE, JobStatusWriterPair.SECTION):
            depth = self._depth(ScopeStartEvent) + self._depth(SectionStartEvent)
        else:
            depth = self._depth(type(event))
        event.write_event(self._stream, depth=depth, prev_event=prev_event, duration=duration)
        self._event_stack.append(event)

    def _depth(self, event_type: type[JobStatusWriterEvent]) -> int:
        if event_type.pair_type is None:
            # Event type does not have nesting
            return 0

        depth: int = 0
        for event in self._event_stack:
            if event.pair_type != event_type.pair_type:
                # Not a related event
                continue
            if event.is_start:
                # Start event
                depth += 1
            else:
                # finish event
                depth -= 1
        return depth

    def start_scope(self, scope: JobScope, include_duration: bool = True) -> None:
        self._write_event_and_append(ScopeStartEvent(scope, start=datetime.now() if include_duration else None))

    def finish_scope(self, scope: JobScope | None = None) -> None:
        if scope is None:
            scope = self._find_start_event(ScopeFinishEvent).event
        errors: list[str | Exception] = self._get_errors(ScopeFinishEvent)
        event: ScopeFinishEvent | ScopeFinishErrorEvent | ScopeFinishErrorsEvent
        if len(errors) == 1:
            event = ScopeFinishErrorEvent(scope, errors[0])
        elif len(errors) > 1:
            event = ScopeFinishErrorsEvent(scope, errors)
        else:
            event = ScopeFinishEvent(scope)
        self._write_event_and_append(event)

    def skip_scope(self, scope: JobScope, reason: str | None = None) -> None:
        self._write_event_and_append(ScopeSkippedEvent(scope, reason=reason))

    def start_section(self, name: str, include_duration: bool = True) -> None:
        self._write_event_and_append(SectionStartEvent(name, start=datetime.now() if include_duration else None))

    def finish_section(self, name: str | None = None) -> None:
        if name is None:
            name = self._find_start_event(SectionFinishEvent).event
        errors: list[str | Exception] = self._get_errors(SectionFinishEvent)
        event: SectionFinishEvent | SectionFinishErrorEvent | SectionFinishErrorsEvent
        if len(errors) == 1:
            event = SectionFinishErrorEvent(name, errors[0])
        elif len(errors) > 1:
            event = SectionFinishErrorsEvent(name, errors)
        else:
            event = SectionFinishEvent(name)
        self._write_event_and_append(event)

    def start_item(self, event: str, include_duration: bool = False, dots: str = "...") -> None:
        self._write_event_and_append(ItemStartEvent(event, start=datetime.now() if include_duration else None))

    def finish_item(self, outcome: str = "done.", error: str | Exception | None = None) -> None:
        errors: list[str | Exception] = self._get_errors(ItemFinishEvent, include_children=False)
        event: ItemFinishEvent | ItemFinishErrorEvent | ItemFinishErrorsEvent
        if len(errors) == 1:
            event = ItemFinishErrorEvent(errors[0])
        elif len(errors) > 1:
            event = ItemFinishErrorsEvent(errors)
        else:
            event = ItemFinishEvent(outcome)
        self._write_event_and_append(event)

    def info(self, message: str) -> None:
        self._write_event_and_append(MessageEvent(message))

    def detail(self, message: str) -> None:
        if self._show_detail:
            self._write_event_and_append(
                MessageEvent(f"{self.DETAIL_CHAR} {message}"),
            )

    def warning(self, message: str | Exception) -> None:
        self._write_event_and_append(
            MessageEvent(f"{self.WARNING_CHAR} {message}"),
        )

    def error(self, message: str | Exception) -> None:
        event: ErrorEvent = ErrorEvent(message)
        if self._depth(ItemFinishEvent) > 0:
            # Append but don't write the error. It will be written on finish_item()
            self._event_stack.append(event)
        else:
            self._write_event_and_append(event)

    def output(self, output: str | Iterable[str], label: str | None = None) -> None:
        self._write_event_and_append(OutputEvent(output, label=label or "output"))

    def _get_errors(
        self, event_type: type[JobStatusWriterEvent], include_children: bool = True
    ) -> list[str | Exception]:
        if event_type.pair_type is None or event_type.is_start:
            # Event type can't have nested events (yet)
            return []

        start_event: JobStatusWriterEvent = self._find_start_event(event_type)

        errors: list[str | Exception] = []
        start_index: int = self._event_stack.index(start_event)
        depth: int = 0
        for event in self._event_stack[start_index:]:
            # if event.type.pair_type == event_type.pair_type:
            if event.pair_type is not None:
                if event.is_start:
                    depth += 1
                else:
                    depth -= 1

            if isinstance(event, ErrorEvent) and (include_children or depth == 1):
                errors.append(str(event.event) if not isinstance(event.event, Exception) else event.event)

        return errors

    def _find_start_event(self, event_type: type[JobStatusWriterEvent]) -> JobStatusWriterEvent:
        if event_type.pair_type is None:
            raise JobException("Event type does not have start/finish pairs.")

        if event_type.is_start:
            raise JobException("Event type is a start event.")

        events: list[JobStatusWriterEvent] = []
        for event in self._event_stack:
            if event.pair_type != event_type.pair_type:
                continue

            if event.is_start:
                events.append(event)
            else:
                events.pop()

        if not events:
            raise JobException("Did not find start event.")

        return events[-1]


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
