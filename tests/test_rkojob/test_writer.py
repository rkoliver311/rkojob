# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from datetime import timedelta
from io import StringIO
from unittest import TestCase
from unittest.mock import MagicMock

from rkojob import JobException
from rkojob.events import (
    JobDetailEvent,
    JobErrorEvent,
    JobFinishItemEvent,
    JobFinishScopeEvent,
    JobFinishScopeTeardownEvent,
    JobFinishSectionEvent,
    JobForkContextEvent,
    JobInfoEvent,
    JobJoinContextEvent,
    JobOutputEvent,
    JobSkipScopeEvent,
    JobStartItemEvent,
    JobStartScopeEvent,
    JobStartScopeTeardownEvent,
    JobStartSectionEvent,
    JobWarningEvent,
)
from rkojob.writer import (
    ErrorEntry,
    ItemFinishEntry,
    ItemFinishErrorEntry,
    ItemFinishErrorsEntry,
    JobStatusWriter,
    JobWriterEntry,
    OutputEntry,
    ScopeFinishEntry,
    ScopeFinishErrorEntry,
    ScopeFinishErrorsEntry,
    ScopeStartEntry,
    SectionFinishEntry,
    SectionFinishErrorEntry,
    SectionFinishErrorsEntry,
)


class StubScope:
    def __init__(self, name, type, id=None):
        self.name = name
        self.type = type
        self.id = id or name

    def __str__(self):
        return f"{self.type} {self.name}"


class TestOutputEntry(TestCase):
    def test_collapsible(self) -> None:
        stream: StringIO = StringIO()
        sut = OutputEntry(
            JobOutputEvent(MagicMock(), StubScope("scope", "type"), "this\nis\noutput\n", label="label"),
            collapsible=True,
        )
        sut.write_event(stream)
        self.assertEqual(
            "<details>\n"
            "<summary>label</summary>\n"
            "\n"
            "    this\n"
            "    is\n"
            "    output\n"
            "\n"
            "</details>\n"
            "\n",
            stream.getvalue(),
        )

    def test_not_collapsible(self) -> None:
        stream: StringIO = StringIO()
        sut = OutputEntry(
            JobOutputEvent(MagicMock(), StubScope("scope", "type"), "this\nis\noutput\n", label="label"),
            collapsible=False,
        )
        sut.write_event(stream)
        self.assertEqual(
            "label:\n" "\n" "    this\n" "    is\n" "    output\n" "\n",
            stream.getvalue(),
        )


class TestJobStatusWriter(TestCase):
    def test_depth(self) -> None:
        sut: JobStatusWriter = JobStatusWriter(MagicMock())
        self.assertEqual(0, sut._depth(ScopeFinishEntry))
        self.assertEqual(0, sut._depth(SectionFinishEntry))
        self.assertEqual(0, sut._depth(ItemFinishEntry))

        mock_scope_1 = MagicMock()
        sut.handle(JobStartScopeEvent(MagicMock(), None, started_scope=mock_scope_1))
        self.assertEqual(1, sut._depth(ScopeFinishEntry))
        self.assertEqual(0, sut._depth(SectionFinishEntry))
        self.assertEqual(0, sut._depth(ItemFinishEntry))

        sut.handle(JobStartScopeEvent(MagicMock(), mock_scope_1, started_scope=MagicMock()))
        self.assertEqual(2, sut._depth(ScopeStartEntry))
        self.assertEqual(0, sut._depth(SectionFinishEntry))
        self.assertEqual(0, sut._depth(ItemFinishEntry))

        sut.handle(JobStartSectionEvent(MagicMock(), MagicMock(), "section"))
        self.assertEqual(2, sut._depth(ScopeStartEntry))
        self.assertEqual(1, sut._depth(SectionFinishEntry))
        self.assertEqual(0, sut._depth(ItemFinishEntry))

        sut.handle(JobStartSectionEvent(MagicMock(), MagicMock(), "section"))
        self.assertEqual(2, sut._depth(ScopeStartEntry))
        self.assertEqual(2, sut._depth(SectionFinishEntry))
        self.assertEqual(0, sut._depth(ItemFinishEntry))

        sut.handle(JobStartItemEvent(MagicMock(), MagicMock(), "item"))
        self.assertEqual(2, sut._depth(ScopeStartEntry))
        self.assertEqual(2, sut._depth(SectionFinishEntry))
        self.assertEqual(1, sut._depth(ItemFinishEntry))

        sut.handle(JobStartItemEvent(MagicMock(), MagicMock(), "item"))
        self.assertEqual(2, sut._depth(ScopeStartEntry))
        self.assertEqual(2, sut._depth(SectionFinishEntry))
        self.assertEqual(2, sut._depth(ItemFinishEntry))

        sut.handle(JobFinishItemEvent(MagicMock(), MagicMock(), "outcome"))
        self.assertEqual(1, sut._depth(ItemFinishEntry))

        sut.handle(JobStartItemEvent(MagicMock(), MagicMock(), "item"))
        self.assertEqual(2, sut._depth(ItemFinishEntry))

        sut.handle(JobFinishItemEvent(MagicMock(), MagicMock(), "outcome"))
        self.assertEqual(1, sut._depth(ItemFinishEntry))

        sut.handle(JobFinishItemEvent(MagicMock(), MagicMock(), "outcome"))
        self.assertEqual(0, sut._depth(ItemFinishEntry))

        sut.handle(JobFinishSectionEvent(MagicMock(), MagicMock(), "section"))
        self.assertEqual(1, sut._depth(SectionFinishEntry))

        sut.handle(JobFinishSectionEvent(MagicMock(), MagicMock(), "section"))
        self.assertEqual(0, sut._depth(SectionFinishEntry))

        sut.handle(JobFinishScopeEvent(MagicMock(), None, MagicMock()))
        self.assertEqual(1, sut._depth(ScopeFinishEntry))

        sut.handle(JobFinishScopeEvent(MagicMock(), None, MagicMock()))
        self.assertEqual(0, sut._depth(ScopeFinishEntry))

    def test_find_start_event(self) -> None:
        sut: JobStatusWriter = JobStatusWriter(MagicMock(), MagicMock())
        mock_context = MagicMock()
        mock_scope_1 = MagicMock()
        sut.handle(JobStartScopeEvent(mock_context, None, started_scope=mock_scope_1))
        entry = sut._find_start_entry(ScopeFinishEntry)
        self.assertIs(mock_context, entry.event.context)
        self.assertIsNone(entry.event.scope)
        self.assertIs(mock_scope_1, entry.event.started_scope)

        mock_scope_2 = MagicMock()
        sut.handle(JobStartScopeEvent(mock_context, mock_scope_1, started_scope=mock_scope_2))
        entry = sut._find_start_entry(ScopeFinishEntry)
        self.assertIs(mock_context, entry.event.context)
        self.assertIs(mock_scope_1, entry.event.scope)
        self.assertIs(mock_scope_2, entry.event.started_scope)

        sut.handle(JobStartItemEvent(mock_context, mock_scope_2, "item"))

        entry = sut._find_start_entry(ScopeFinishErrorEntry)
        self.assertIs(mock_context, entry.event.context)
        self.assertIs(mock_scope_1, entry.event.scope)
        self.assertIs(mock_scope_2, entry.event.started_scope)

        entry = sut._find_start_entry(ItemFinishErrorsEntry)
        self.assertEqual("item", entry.event.item)
        sut.handle(JobFinishItemEvent(mock_context, mock_scope_2, "done."))
        with self.assertRaises(JobException):
            _ = sut._find_start_entry(ItemFinishErrorEntry)

        sut.handle(JobStartSectionEvent(mock_context, mock_scope_2, "name"))
        entry = sut._find_start_entry(SectionFinishErrorEntry)
        self.assertEqual("name", entry.event.section)

        sut.handle(JobFinishSectionEvent(mock_context, mock_scope_2, "name"))
        with self.assertRaises(JobException):
            _ = sut._find_start_entry(SectionFinishErrorsEntry)

        sut.handle(JobFinishScopeEvent(mock_context, mock_scope_1, finished_scope=mock_scope_2))
        entry = sut._find_start_entry(ScopeFinishEntry)
        self.assertIsNone(entry.event.scope)
        self.assertIs(mock_scope_1, entry.event.started_scope)

        sut.handle(JobFinishScopeEvent(mock_context, None, finished_scope=mock_scope_1))
        with self.assertRaises(JobException):
            _ = sut._find_start_entry(ScopeFinishErrorsEntry)

    def test_find_start_event_negative(self) -> None:
        sut = JobStatusWriter(MagicMock())
        with self.assertRaises(JobException) as e:
            _ = sut._find_start_entry(ErrorEntry)
        self.assertEqual("Event type does not have start/finish pairs.", str(e.exception))

        with self.assertRaises(JobException) as e:
            _ = sut._find_start_entry(ScopeFinishEntry)
        self.assertEqual("Did not find start event.", str(e.exception))

        with self.assertRaises(JobException) as e:
            _ = sut._find_start_entry(ScopeStartEntry)
        self.assertEqual("Event type is a start event.", str(e.exception))

    def test(self) -> None:
        expected: list[str] = []
        mock_context = MagicMock()

        stream: StringIO = StringIO()
        sut: JobStatusWriter = JobStatusWriter(stream=stream, include_duration=False)

        expected.append("# Job Job\n\n")
        job = StubScope("Job", "Job")
        sut.handle(JobStartScopeEvent(mock_context, None, started_scope=job))

        expected.append("## Stage Stage1\n\n")
        stage1 = StubScope("Stage1", "Stage")
        sut.handle(JobStartScopeEvent(mock_context, job, started_scope=stage1))

        expected.append("### Step Step1.1\n\n")
        step1_1 = StubScope("Step1.1", "Step")
        sut.handle(JobStartScopeEvent(mock_context, stage1, started_scope=step1_1))

        expected.append(" - Step1.1.1...done.\n\n")
        sut.handle(JobStartItemEvent(mock_context, step1_1, "Step1.1.1"))
        sut.handle(JobFinishItemEvent(mock_context, step1_1, "done."))

        expected.append("#### Section\n\n")
        sut.handle(JobStartSectionEvent(mock_context, stage1, "Section"))

        expected.append(" - Step1.1.2...done.\n\n")
        sut.handle(JobStartItemEvent(mock_context, step1_1, "Step1.1.2"))
        sut.handle(JobFinishItemEvent(mock_context, step1_1, "done."))

        expected.append("Finished **Section**\n\n")
        sut.handle(JobFinishSectionEvent(mock_context, step1_1, "Section"))

        expected.append("✅ Finished **Step Step1.1**\n\n")
        sut.handle(JobFinishScopeEvent(mock_context, stage1, finished_scope=step1_1))

        expected.append("### Step Step1.2\n\n")
        step1_2 = StubScope("Step1.2", "Step")
        sut.handle(JobStartScopeEvent(mock_context, stage1, started_scope=step1_2))

        expected.append("✅ Finished **Step Step1.2**\n\n")
        sut.handle(JobFinishScopeEvent(mock_context, stage1, finished_scope=step1_2))

        expected.append("✅ Finished **Stage Stage1**\n\n")
        sut.handle(JobFinishScopeEvent(mock_context, job, finished_scope=stage1))

        expected.append("## Stage Stage2\n\n")
        stage2 = StubScope("Stage2", "Stage")
        sut.handle(JobStartScopeEvent(mock_context, job, started_scope=stage2))

        expected.append("### Step Step2.1\n\n")
        step2_1 = StubScope("Step2.1", "Step")
        sut.handle(JobStartScopeEvent(mock_context, stage2, started_scope=step2_1))

        expected.append("✅ Finished **Step Step2.1**\n\n")
        sut.handle(JobFinishScopeEvent(mock_context, stage2, finished_scope=step2_1))

        expected.append("### Step Step2.2\n\n")
        step2_2 = StubScope("Step2.2", "Step")
        sut.handle(JobStartScopeEvent(mock_context, stage2, started_scope=step2_2))

        expected.append(" - Step2.2.1...\n")
        sut.handle(JobStartItemEvent(mock_context, step2_2, "Step2.2.1"))

        expected.append("   - Step2.2.2...done.\n")
        sut.handle(JobStartItemEvent(mock_context, step2_2, "Step2.2.2"))
        sut.handle(JobFinishItemEvent(mock_context, step2_2, "done."))

        expected.append("   - Step2.2.3...done.\n")
        sut.handle(JobStartItemEvent(mock_context, step2_2, "Step2.2.3"))
        sut.handle(JobFinishItemEvent(mock_context, step2_2, "done."))

        expected.append("   done.\n\n")
        sut.handle(JobFinishItemEvent(mock_context, step2_2, "done."))

        expected.append("✅ Finished **Step Step2.2**\n\n")
        sut.handle(JobFinishScopeEvent(mock_context, stage2, finished_scope=step2_2))

        expected.append("✅ Finished **Stage Stage2**\n\n")
        sut.handle(JobFinishScopeEvent(mock_context, job, finished_scope=stage2))

        expected.append("✅ Finished **Job Job**\n\n")
        sut.handle(JobFinishScopeEvent(mock_context, None, finished_scope=job))

        self.assertEqual("".join(expected), stream.getvalue())

    def test_get_errors(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        mock_context = MagicMock()
        self.assertEqual([], sut._get_errors(ErrorEntry))

        scope = StubScope("name", "type")
        sut.handle(JobStartScopeEvent(mock_context, None, started_scope=scope))
        sut.handle(JobErrorEvent(mock_context, scope, "error1"))
        sut.handle(JobStartSectionEvent(mock_context, scope, "section"))
        sut.handle(JobErrorEvent(mock_context, scope, "error2"))
        sut.handle(JobStartItemEvent(mock_context, scope, "item"))
        sut.handle(JobErrorEvent(mock_context, scope, "error3"))
        self.assertEqual(["error3"], sut._get_errors(ItemFinishEntry))
        self.assertEqual(["error3"], sut._get_errors(ItemFinishEntry, include_children=False))
        sut.handle(JobFinishItemEvent(mock_context, scope, "done."))
        self.assertEqual(["error2", "error3"], sut._get_errors(SectionFinishEntry))
        self.assertEqual(["error2"], sut._get_errors(SectionFinishEntry, include_children=False))
        sut.handle(JobFinishSectionEvent(mock_context, scope, "section"))
        self.assertEqual(["error1", "error2", "error3"], sut._get_errors(ScopeFinishEntry))
        self.assertEqual(["error1"], sut._get_errors(ScopeFinishEntry, include_children=False))
        sut.handle(JobFinishScopeEvent(mock_context, None, finished_scope=scope))

    def test_fork_context(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        mock_context = MagicMock()
        forked_context = MagicMock()

        sut.handle(JobForkContextEvent(mock_context, None, forked_context=forked_context))

        self.assertEqual("*Forking context...*\n\n", stream.getvalue())

    def test_fork_context_no_detail(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream, show_detail=False)
        mock_context = MagicMock()
        forked_context = MagicMock()

        sut.handle(JobForkContextEvent(mock_context, None, forked_context=forked_context))

        self.assertEqual("", stream.getvalue())

    def test_join_context(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        mock_context = MagicMock()
        joined_context = MagicMock()

        sut.handle(JobJoinContextEvent(mock_context, None, joined_context=joined_context))

        self.assertEqual("*Joining context...*\n\n", stream.getvalue())

    def test_join_context_no_detail(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream, show_detail=False)
        mock_context = MagicMock()
        joined_context = MagicMock()

        sut.handle(JobJoinContextEvent(mock_context, None, joined_context=joined_context))

        self.assertEqual("", stream.getvalue())

    def test_start_finish_scope(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        mock_context = MagicMock()

        scope = StubScope("name", "type")
        sut.handle(JobStartScopeEvent(mock_context, None, started_scope=scope))

        self.assertEqual("# type name\n\n", stream.getvalue())

        scope2 = StubScope("name2", "type2")
        sut.handle(JobStartScopeEvent(mock_context, scope, started_scope=scope2))
        self.assertEqual("# type name\n\n## type2 name2\n\n", stream.getvalue())

        sut.handle(JobFinishScopeEvent(mock_context, scope, finished_scope=scope2))
        self.assertEqual("# type name\n\n## type2 name2\n\n✅ Finished **type2 name2**\n\n", stream.getvalue())

        sut.handle(JobErrorEvent(mock_context, scope, "error1"))
        sut.handle(JobErrorEvent(mock_context, scope, "error2"))
        sut.handle(JobFinishScopeEvent(mock_context, None, finished_scope=scope))
        self.assertEqual(
            "# type name\n\n"
            "## type2 name2\n\n"
            "✅ Finished **type2 name2**\n\n"
            "❌ error1\n\n"
            "❌ error2\n\n"
            "❌ Finished **type name**\n"
            " - ❌ error1\n"
            " - ❌ error2\n\n",
            stream.getvalue(),
        )

    def test_finish_scope_one_error(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        mock_context = MagicMock()

        scope = StubScope("name", "type")
        sut.handle(JobStartScopeEvent(mock_context, None, started_scope=scope))
        sut.handle(JobErrorEvent(mock_context, scope, "error"))
        sut.handle(JobFinishScopeEvent(mock_context, None, finished_scope=scope))
        self.assertEqual(
            "# type name\n\n❌ error\n\n❌ Finished **type name**\n❌ error\n\n",
            stream.getvalue(),
        )

    def test_skip_scope(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        sut.handle(
            JobSkipScopeEvent(MagicMock(), MagicMock(), skipped_scope=StubScope("name", "type"), reason="Disabled")
        )
        self.assertEqual("**Skipping type name (Disabled)**\n\n", stream.getvalue())

    def test_start_finish_teardown(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)

        mock_context = MagicMock()
        stub_scope = StubScope("name", "type")

        sut.handle(JobStartScopeEvent(mock_context, None, started_scope=stub_scope))
        self.assertEqual("# type name\n\n", stream.getvalue())

        sut.handle(JobStartScopeTeardownEvent(mock_context, stub_scope))
        self.assertEqual("# type name\n\n## Teardown type name\n\n", stream.getvalue())

        sut.handle(JobFinishScopeTeardownEvent(mock_context, stub_scope))
        self.assertEqual(
            "# type name\n\n## Teardown type name\n\nFinished **Teardown type name**\n\n", stream.getvalue()
        )

    def test_start_finish_section(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)

        mock_context = MagicMock()
        mock_scope = MagicMock()

        sut.handle(JobStartSectionEvent(mock_context, mock_scope, "name"))
        self.assertEqual("# name\n\n", stream.getvalue())

        sut.handle(JobStartSectionEvent(mock_context, mock_scope, "name2"))
        self.assertEqual("# name\n\n## name2\n\n", stream.getvalue())

        sut.handle(JobFinishSectionEvent(mock_context, mock_scope, "name2"))
        self.assertEqual("# name\n\n## name2\n\nFinished **name2**\n\n", stream.getvalue())

        sut.handle(JobErrorEvent(mock_context, mock_scope, "error"))
        sut.handle(JobFinishSectionEvent(mock_context, mock_scope, "name"))
        self.assertEqual(
            "# name\n\n## name2\n\nFinished **name2**\n\n❌ error\n\n\u274c Finished **name**\n❌ error\n\n",
            stream.getvalue(),
        )

    def test_start_finish_item(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        mock_context = MagicMock()
        mock_scope = MagicMock()
        sut.handle(JobStartItemEvent(mock_context, mock_scope, "foo"))
        self.assertEqual(" - foo...", stream.getvalue())

        sut.handle(JobFinishItemEvent(mock_context, mock_scope, "done."))
        self.assertEqual(" - foo...done.\n", stream.getvalue())

    def test_start_finish_item_include_duration(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream, include_duration=True)
        mock_context = MagicMock()
        mock_scope = MagicMock()
        sut.handle(JobStartItemEvent(mock_context, mock_scope, "foo"))
        self.assertEqual(" - foo...", stream.getvalue())

        sut.handle(JobFinishItemEvent(mock_context, mock_scope, "done."))
        self.assertEqual(" - foo...done. (0s)\n", stream.getvalue())

    def test_start_finish_item_error(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        mock_context = MagicMock()
        mock_scope = MagicMock()

        sut.handle(JobStartItemEvent(mock_context, mock_scope, "foo"))
        self.assertEqual(" - foo...", stream.getvalue())

        sut.handle(JobErrorEvent(mock_context, mock_scope, "error"))
        sut.handle(JobFinishItemEvent(mock_context, mock_scope, "foo"))
        self.assertEqual(" - foo...❌ error\n", stream.getvalue())

    def test_start_finish_item_error_multiple(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        mock_context = MagicMock()
        mock_scope = MagicMock()

        sut.handle(JobStartItemEvent(mock_context, mock_scope, "foo"))
        self.assertEqual(" - foo...", stream.getvalue())

        sut.handle(JobErrorEvent(mock_context, mock_scope, "error1"))
        sut.handle(JobErrorEvent(mock_context, mock_scope, "error2"))
        sut.handle(JobErrorEvent(mock_context, mock_scope, Exception("error3")))
        sut.handle(JobFinishItemEvent(mock_context, mock_scope, "foo"))

        self.assertEqual(" - foo...❌\n   - ❌ error1\n" "   - ❌ error2\n" "   - ❌ error3\n", stream.getvalue())

    def test_start_finish_inner_item_error_multiple(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        mock_context = MagicMock()
        mock_scope = MagicMock()
        sut.handle(JobStartItemEvent(mock_context, mock_scope, "foo"))
        self.assertEqual(" - foo...", stream.getvalue())

        sut.handle(JobStartItemEvent(mock_context, mock_scope, "bar"))
        self.assertEqual(" - foo...\n" "   - bar...", stream.getvalue())

        sut.handle(JobErrorEvent(mock_context, mock_scope, "error1"))
        sut.handle(JobErrorEvent(mock_context, mock_scope, "error2"))
        sut.handle(JobErrorEvent(mock_context, mock_scope, Exception("error3")))
        sut.handle(JobFinishItemEvent(mock_context, mock_scope, "bar"))
        sut.handle(JobFinishItemEvent(mock_context, mock_scope, "foo"))

        self.assertEqual(
            " - foo...\n" "   - bar...❌\n" "     - ❌ error1\n" "     - ❌ error2\n" "     - ❌ error3\n   foo\n",
            stream.getvalue(),
        )

    def test_duration_format(self) -> None:
        self.assertEqual("0s", JobWriterEntry._format_duration(timedelta()))
        self.assertEqual("1.000s", JobWriterEntry._format_duration(timedelta(seconds=1)))
        self.assertEqual("5s", JobWriterEntry._format_duration(timedelta(seconds=5, milliseconds=1)))
        self.assertEqual("0.001s", JobWriterEntry._format_duration(timedelta(milliseconds=1)))
        self.assertEqual("1.001s", JobWriterEntry._format_duration(timedelta(seconds=1, milliseconds=1)))
        self.assertEqual("4m1s", JobWriterEntry._format_duration(timedelta(minutes=4, seconds=1, milliseconds=1)))
        self.assertEqual(
            "26h3m",
            JobWriterEntry._format_duration(timedelta(days=1, hours=2, minutes=3, seconds=4, milliseconds=5)),
        )

    def test_info(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        sut.handle(JobInfoEvent(MagicMock(), MagicMock(), "info"))
        self.assertEqual("info\n\n", stream.getvalue())

    def test_detail(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        sut.handle(JobDetailEvent(MagicMock(), MagicMock(), "detail"))
        self.assertEqual("🔎 detail\n\n", stream.getvalue())

    def test_detail_quiet(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream, show_detail=False)
        sut.handle(JobDetailEvent(MagicMock(), MagicMock(), "detail"))
        self.assertEqual("", stream.getvalue())

    def test_warning(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        sut.handle(JobWarningEvent(MagicMock(), MagicMock(), "warning"))
        self.assertEqual("⚠️ warning\n\n", stream.getvalue())

    def test_error(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        sut.handle(JobErrorEvent(MagicMock(), MagicMock(), "error"))
        self.assertEqual("❌ error\n\n", stream.getvalue())

    def test_output(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        mock_context = MagicMock()
        mock_scope = MagicMock()
        sut.handle(JobStartSectionEvent(mock_context, mock_scope, "Some code"))
        sut.handle(JobInfoEvent(mock_context, mock_scope, "Here it is:"))
        sut.handle(
            JobOutputEvent(
                mock_context,
                mock_scope,
                ["some Code {\n", "  var foo = bar;\n  print(foo);\n", "};\n"],
                label="Some code",
            )
        )
        sut.handle(JobFinishSectionEvent(mock_context, mock_scope, "Some code"))
        self.assertEqual(
            "# Some code\n\n"
            "Here it is:\n\n"
            "Some code:\n\n"
            "    some Code {\n"
            "      var foo = bar;\n"
            "      print(foo);\n"
            "    };\n\n"
            "Finished **Some code**\n\n",
            stream.getvalue(),
        )

    def test_output_as_str(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        sut.handle(JobOutputEvent(MagicMock(), MagicMock(), "Some output"))
        self.assertEqual("output:\n\n    Some output\n\n", stream.getvalue())
