# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import ClassVar, Generic, Iterable, TextIO, TypeVar

from rkojob import JobEvent, JobEventHandler, JobException
from rkojob.events import (
    JobDetailEvent,
    JobErrorEvent,
    JobFinishItemEvent,
    JobFinishScopeEvent,
    JobFinishSectionEvent,
    JobInfoEvent,
    JobOutputEvent,
    JobSkipScopeEvent,
    JobStartItemEvent,
    JobStartScopeEvent,
    JobStartSectionEvent,
    JobWarningEvent,
)


# TODO: Replace with subclasses?
class JobStatusWriterPair(Enum):
    SCOPE = auto()
    SECTION = auto()
    ITEM = auto()


T = TypeVar("T", bound=JobEvent)


class JobWriterEntry(ABC, Generic[T]):
    pair_type: ClassVar[JobStatusWriterPair | None] = None
    is_start: ClassVar[bool] = False
    prefix: ClassVar[str] = "\n\n"
    suffix: ClassVar[str] = "\n\n"

    def __init__(self, event: T):
        self.event: T = event

    def write_event(
        self,
        stream: TextIO,
        depth: int = 0,
        prev_event: JobWriterEntry | None = None,
        duration: timedelta | None = None,
    ) -> None:
        self._write_prefix(stream, prev_event=prev_event)
        self._write_indent(stream, depth, prev_event=prev_event)
        self._write_event(stream, depth, duration=None if self.is_start else duration)
        self._write_suffix(stream)

    def _write_prefix(self, stream: TextIO, prev_event: JobWriterEntry | None) -> None:
        if not prev_event:
            return
        if not prev_event.suffix.endswith(self.prefix):
            separator: str = self.prefix.removeprefix(prev_event.suffix)
            stream.write(separator)

    def _write_indent(self, stream: TextIO, depth: int, prev_event: JobWriterEntry | None = None) -> None:
        pass

    @abstractmethod
    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None: ...

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


class ScopeStartEntry(JobWriterEntry[JobStartScopeEvent]):
    pair_type = JobStatusWriterPair.SCOPE
    is_start = True

    def _write_indent(self, stream: TextIO, depth: int, prev_event: JobWriterEntry | None = None) -> None:
        stream.write("#" + "#" * depth + " ")

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(str(self.event.started_scope))


class ScopeFinishEntry(JobWriterEntry[JobFinishScopeEvent]):
    pair_type = JobStatusWriterPair.SCOPE

    def _write_indent(self, stream: TextIO, depth: int, prev_event: JobWriterEntry | None = None) -> None:
        stream.write("\u2705 ")

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"Finished **{self.event.finished_scope}**")
        self._write_duration(stream, duration)


class ScopeFinishErrorEntry(JobWriterEntry[JobFinishScopeEvent]):
    pair_type = JobStatusWriterPair.SCOPE

    def __init__(self, event: JobFinishScopeEvent, error: str | Exception) -> None:
        super().__init__(event)
        self.error: str | Exception = error

    def _write_indent(self, stream: TextIO, depth: int, prev_event: JobWriterEntry | None = None) -> None:
        stream.write("\u274c ")

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"Finished **{self.event.finished_scope}**")
        self._write_duration(stream, duration)
        stream.write(f"\n\u274c {self.error}")


class ScopeFinishErrorsEntry(JobWriterEntry[JobFinishScopeEvent]):
    pair_type = JobStatusWriterPair.SCOPE

    def __init__(self, event: JobFinishScopeEvent, errors: list[str | Exception]) -> None:
        super().__init__(event)
        self.errors: list[str | Exception] = errors

    def _write_indent(self, stream: TextIO, depth: int, prev_event: JobWriterEntry | None = None) -> None:
        stream.write("\u274c ")

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"Finished **{self.event.finished_scope}**")
        self._write_duration(stream, duration)
        for error in self.errors:
            stream.write(f"\n - \u274c {error}")


class ScopeSkippedEntry(JobWriterEntry[JobSkipScopeEvent]):
    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"**Skipping {self.event.skipped_scope}")
        if self.event.reason:
            stream.write(f" ({self.event.reason})")
        stream.write("**")


class SectionStartEntry(JobWriterEntry[JobStartSectionEvent]):
    pair_type = JobStatusWriterPair.SECTION
    is_start = True

    def _write_indent(self, stream: TextIO, depth: int, prev_event: JobWriterEntry | None = None) -> None:
        stream.write("#" + "#" * depth + " ")

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(self.event.section)


class SectionFinishEntry(JobWriterEntry[JobFinishSectionEvent]):
    pair_type = JobStatusWriterPair.SECTION

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"Finished **{self.event.section}**")
        self._write_duration(stream, duration)


class SectionFinishErrorEntry(JobWriterEntry[JobFinishSectionEvent]):
    pair_type = JobStatusWriterPair.SECTION

    def __init__(self, event: JobFinishSectionEvent, error: str | Exception) -> None:
        super().__init__(event)
        self.error: str | Exception = error

    def _write_indent(self, stream: TextIO, depth: int, prev_event: JobWriterEntry | None = None) -> None:
        stream.write("\u274c ")

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"Finished **{self.event.section}**")
        self._write_duration(stream, duration)
        stream.write(f"\n\u274c {self.error}")


class SectionFinishErrorsEntry(JobWriterEntry[JobFinishSectionEvent]):
    pair_type = JobStatusWriterPair.SECTION

    def __init__(self, event: JobFinishSectionEvent, errors: list[str | Exception]) -> None:
        super().__init__(event)
        self.errors: list[str | Exception] = errors

    def _write_indent(self, stream: TextIO, depth: int, prev_event: JobWriterEntry | None = None) -> None:
        stream.write("\u274c ")

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"\u274c Finished **{self.event.section}**")
        self._write_duration(stream, duration)
        for error in self.errors:
            stream.write(f"\n\u274c {error}")


class ItemStartEntry(JobWriterEntry[JobStartItemEvent]):
    pair_type = JobStatusWriterPair.ITEM
    is_start = True
    prefix = "\n"
    suffix = ""

    def _write_indent(self, stream: TextIO, depth: int, prev_event: JobWriterEntry | None = None) -> None:
        stream.write("  " * depth + " - ")

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"{self.event.item}...")


class ItemFinishEntry(JobWriterEntry[JobFinishItemEvent]):
    pair_type = JobStatusWriterPair.ITEM
    prefix = ""
    suffix = "\n"

    def _write_indent(self, stream: TextIO, depth: int, prev_event: JobWriterEntry | None = None) -> None:
        if not isinstance(prev_event, ItemStartEntry):
            stream.write("   " * depth)

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(self.event.outcome)
        self._write_duration(stream, duration)


class ItemFinishErrorEntry(JobWriterEntry[JobFinishItemEvent]):
    pair_type = JobStatusWriterPair.ITEM
    prefix = ""
    suffix = "\n"

    def __init__(self, event: JobFinishItemEvent, error: str | Exception) -> None:
        super().__init__(event)
        self.error: str | Exception = error

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"\u274c {self.error}")
        self._write_duration(stream, duration)


class ItemFinishErrorsEntry(JobWriterEntry[JobFinishItemEvent]):
    pair_type = JobStatusWriterPair.ITEM
    prefix = ""
    suffix = "\n"

    def __init__(self, event: JobFinishItemEvent, errors: list[str | Exception]) -> None:
        super().__init__(event)
        self.errors: list[str | Exception] = errors

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write("\u274c")
        self._write_duration(stream, duration)
        for error in self.errors:
            stream.write(f"\n{'  ' * depth} - \u274c {error}")


class InfoEntry(JobWriterEntry[JobInfoEvent]):
    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(self.event.message)


class WarningEntry(JobWriterEntry[JobWarningEvent]):
    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"⚠️ {self.event.warning}")


class DetailEntry(JobWriterEntry[JobDetailEvent]):
    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"🔎 {self.event.message}")


class ErrorEntry(JobWriterEntry[JobErrorEvent]):
    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        stream.write(f"\u274c {self.event.error}")


class OutputEntry(JobWriterEntry[JobOutputEvent]):
    def __init__(self, event: JobOutputEvent, collapsible: bool = False) -> None:
        super().__init__(event)
        self._collapsible: bool = collapsible

    def _write_event(self, stream: TextIO, depth: int, duration: timedelta | None = None) -> None:
        if self._collapsible:
            stream.write("<details>\n")
            stream.write(f"<summary>{self.event.label}</summary>\n")
        else:
            stream.write(f"{self.event.label}:\n")

        output: str | Iterable[str] = self.event.output
        if isinstance(output, str):
            output = [output]
        for line in output:
            if line.endswith("\n"):
                line = line[:-1]
            for subline in line.split("\n"):
                stream.write(f"\n    {subline}")

        if self._collapsible:
            stream.write("\n\n</details>")


class JobStatusWriter(JobEventHandler):
    def __init__(
        self,
        stream: TextIO,
        include_duration: bool = False,
        show_detail: bool = True,
        collapsible_output: bool = False,
    ) -> None:
        self._include_duration: bool = include_duration
        self._show_detail: bool = show_detail
        self._collapsible_output: bool = collapsible_output
        self._stream: TextIO = stream
        self._entry_stack: list[JobWriterEntry] = []

    def handle(self, event: JobEvent) -> None:
        entry: JobWriterEntry
        errors: list[str | Exception]
        append_only: bool = False

        if isinstance(event, JobStartScopeEvent):
            entry = ScopeStartEntry(event)
        elif isinstance(event, JobFinishScopeEvent):
            errors = self._get_errors(ScopeFinishEntry)
            if len(errors) == 1:
                entry = ScopeFinishErrorEntry(event, errors[0])
            elif len(errors) > 1:
                entry = ScopeFinishErrorsEntry(event, errors)
            else:
                entry = ScopeFinishEntry(event)
        elif isinstance(event, JobErrorEvent):
            entry = ErrorEntry(event)
            if self._depth(ItemFinishEntry) > 0:
                # Append but don't write the error. It will be written on finish_item()
                append_only = True
        elif isinstance(event, JobSkipScopeEvent):
            entry = ScopeSkippedEntry(event)
        elif isinstance(event, JobStartSectionEvent):
            entry = SectionStartEntry(event)
        elif isinstance(event, JobFinishSectionEvent):
            errors = self._get_errors(SectionFinishEntry)
            if len(errors) == 1:
                entry = SectionFinishErrorEntry(event, errors[0])
            elif len(errors) > 1:
                entry = SectionFinishErrorsEntry(event, errors)
            else:
                entry = SectionFinishEntry(event)
        elif isinstance(event, JobStartItemEvent):
            entry = ItemStartEntry(event)
        elif isinstance(event, JobFinishItemEvent):
            errors = self._get_errors(ItemFinishEntry, include_children=False)
            if len(errors) == 1:
                entry = ItemFinishErrorEntry(event, errors[0])
            elif len(errors) > 1:
                entry = ItemFinishErrorsEntry(event, errors)
            else:
                entry = ItemFinishEntry(event)
        elif isinstance(event, JobWarningEvent):
            entry = WarningEntry(event)
        elif isinstance(event, JobInfoEvent):
            entry = InfoEntry(event)
        elif isinstance(event, JobDetailEvent):
            if not self._show_detail:
                return
            entry = DetailEntry(event)
        elif isinstance(event, JobOutputEvent):
            entry = OutputEntry(event, collapsible=self._collapsible_output)
        else:  # pragma: no cover
            return

        if append_only:
            self._entry_stack.append(entry)
        else:
            self._write_entry_and_append(entry)

    def _write_entry_and_append(self, entry: JobWriterEntry) -> None:
        prev_event: JobWriterEntry | None = self._entry_stack[-1] if self._entry_stack else None
        duration: timedelta | None = None
        if self._include_duration and entry.pair_type is not None and not entry.is_start:
            start_entry: JobWriterEntry = self._find_start_entry(type(entry))
            duration = datetime.now() - start_entry.event.timestamp
        depth: int
        if entry.pair_type in (JobStatusWriterPair.SCOPE, JobStatusWriterPair.SECTION):
            depth = self._depth(ScopeStartEntry) + self._depth(SectionStartEntry)
        else:
            depth = self._depth(type(entry))
        entry.write_event(self._stream, depth=depth, prev_event=prev_event, duration=duration)
        self._entry_stack.append(entry)

    def _depth(self, entry_type: type[JobWriterEntry]) -> int:
        if entry_type.pair_type is None:
            # Event type does not have nesting
            return 0

        depth: int = 0
        for entry in self._entry_stack:
            if entry.pair_type != entry_type.pair_type:
                # Not a related event
                continue
            if entry.is_start:
                # Start event
                depth += 1
            else:
                # finish event
                depth -= 1
        return depth

    def _get_errors(self, entry_type: type[JobWriterEntry], include_children: bool = True) -> list[str | Exception]:
        if entry_type.pair_type is None or entry_type.is_start:
            # Event type can't have nested events (yet)
            return []

        start_entry: JobWriterEntry = self._find_start_entry(entry_type)

        errors: list[str | Exception] = []
        start_index: int = self._entry_stack.index(start_entry)
        depth: int = 0
        for entry in self._entry_stack[start_index:]:
            # if entry.type.pair_type == entry_type.pair_type:
            if entry.pair_type is not None:
                if entry.is_start:
                    depth += 1
                else:
                    depth -= 1

            if isinstance(entry, ErrorEntry) and (include_children or depth == 1):
                error: str | Exception = entry.event.error
                errors.append(str(error) if not isinstance(error, Exception) else error)

        return errors

    def _find_start_entry(self, entry_type: type[JobWriterEntry]) -> JobWriterEntry:
        if entry_type.pair_type is None:
            raise JobException("Event type does not have start/finish pairs.")

        if entry_type.is_start:
            raise JobException("Event type is a start event.")

        entries: list[JobWriterEntry] = []
        for entry in self._entry_stack:
            if entry.pair_type != entry_type.pair_type:
                continue

            if entry.is_start:
                entries.append(entry)
            else:
                entries.pop()

        if not entries:
            raise JobException("Did not find start event.")

        return entries[-1]
