from datetime import timedelta
from enum import Enum, auto
from io import StringIO
from unittest import TestCase
from unittest.mock import MagicMock

from rkojob import JobException, JobScopeStatus, Values
from rkojob.context import (
    ErrorEvent,
    ItemFinishErrorEvent,
    ItemFinishErrorsEvent,
    ItemFinishEvent,
    JobContextImpl,
    JobScopeStatuses,
    JobStatusWriter,
    JobStatusWriterEvent,
    ScopeFinishErrorEvent,
    ScopeFinishErrorsEvent,
    ScopeFinishEvent,
    ScopeStartEvent,
    SectionFinishErrorEvent,
    SectionFinishErrorsEvent,
    SectionFinishEvent,
)


class TestJobScopeStatuses(TestCase):
    def test(self) -> None:
        mock_scope_1 = MagicMock()
        mock_scope_2 = MagicMock()
        mock_scope_3 = MagicMock()

        sut = JobScopeStatuses()
        self.assertEqual(JobScopeStatus.UNKNOWN, sut.get_status(mock_scope_1))
        self.assertEqual(JobScopeStatus.UNKNOWN, sut.get_status(mock_scope_2))
        self.assertEqual(JobScopeStatus.UNKNOWN, sut.get_status(mock_scope_3))

        sut.start_scope(mock_scope_1)
        self.assertEqual(JobScopeStatus.RUNNING, sut.get_status(mock_scope_1))
        self.assertEqual(JobScopeStatus.UNKNOWN, sut.get_status(mock_scope_2))
        self.assertEqual(JobScopeStatus.UNKNOWN, sut.get_status(mock_scope_3))

        sut.skip_scope(mock_scope_2)
        self.assertEqual(JobScopeStatus.RUNNING, sut.get_status(mock_scope_1))
        self.assertEqual(JobScopeStatus.SKIPPED, sut.get_status(mock_scope_2))
        self.assertEqual(JobScopeStatus.UNKNOWN, sut.get_status(mock_scope_3))

        with self.assertRaises(JobException) as e:
            sut.finish_scope(mock_scope_2)
        self.assertEqual("Scope does not match scope on stack.", str(e.exception))

        with self.assertRaises(JobException) as e:
            sut.start_scope(mock_scope_2)
        self.assertEqual("Scope status already set.", str(e.exception))

        sut.start_scope(mock_scope_3)
        self.assertEqual(JobScopeStatus.RUNNING, sut.get_status(mock_scope_1))
        self.assertEqual(JobScopeStatus.SKIPPED, sut.get_status(mock_scope_2))
        self.assertEqual(JobScopeStatus.RUNNING, sut.get_status(mock_scope_3))

        sut.finish_scope()
        self.assertEqual(JobScopeStatus.RUNNING, sut.get_status(mock_scope_1))
        self.assertEqual(JobScopeStatus.SKIPPED, sut.get_status(mock_scope_2))
        self.assertEqual(JobScopeStatus.PASSED, sut.get_status(mock_scope_3))

        sut.error("error")
        sut.finish_scope(mock_scope_1)
        self.assertEqual(JobScopeStatus.FAILED, sut.get_status(mock_scope_1))
        self.assertEqual(JobScopeStatus.SKIPPED, sut.get_status(mock_scope_2))
        self.assertEqual(JobScopeStatus.PASSED, sut.get_status(mock_scope_3))

    def test_finish_item(self) -> None:
        mock_scope_1 = MagicMock()

        sut = JobScopeStatuses()
        self.assertEqual(JobScopeStatus.UNKNOWN, sut.get_status(mock_scope_1))

        sut.start_scope(mock_scope_1)
        self.assertEqual(JobScopeStatus.RUNNING, sut.get_status(mock_scope_1))

        sut.start_item("item")
        self.assertEqual(JobScopeStatus.RUNNING, sut.get_status(mock_scope_1))

        sut.finish_item(error="error")
        self.assertEqual(JobScopeStatus.FAILING, sut.get_status(mock_scope_1))

        sut.finish_scope()
        self.assertEqual(JobScopeStatus.FAILED, sut.get_status(mock_scope_1))


class StubScope:
    def __init__(self, name, type):
        self.name = name
        self.type = type


class TestJobStatusWriter(TestCase):
    def test_depth(self) -> None:
        sut: JobStatusWriter = JobStatusWriter(MagicMock())
        self.assertEqual(0, sut._depth(ScopeFinishEvent))
        self.assertEqual(0, sut._depth(SectionFinishEvent))
        self.assertEqual(0, sut._depth(ItemFinishEvent))

        sut.start_scope(MagicMock())
        self.assertEqual(1, sut._depth(ScopeFinishEvent))
        self.assertEqual(0, sut._depth(SectionFinishEvent))
        self.assertEqual(0, sut._depth(ItemFinishEvent))

        sut.start_scope(MagicMock())
        self.assertEqual(2, sut._depth(ScopeStartEvent))
        self.assertEqual(0, sut._depth(SectionFinishEvent))
        self.assertEqual(0, sut._depth(ItemFinishEvent))

        sut.start_section(MagicMock())
        self.assertEqual(2, sut._depth(ScopeStartEvent))
        self.assertEqual(1, sut._depth(SectionFinishEvent))
        self.assertEqual(0, sut._depth(ItemFinishEvent))

        sut.start_section(MagicMock())
        self.assertEqual(2, sut._depth(ScopeStartEvent))
        self.assertEqual(2, sut._depth(SectionFinishEvent))
        self.assertEqual(0, sut._depth(ItemFinishEvent))

        sut.start_item(MagicMock())
        self.assertEqual(2, sut._depth(ScopeStartEvent))
        self.assertEqual(2, sut._depth(SectionFinishEvent))
        self.assertEqual(1, sut._depth(ItemFinishEvent))

        sut.start_item(MagicMock())
        self.assertEqual(2, sut._depth(ScopeStartEvent))
        self.assertEqual(2, sut._depth(SectionFinishEvent))
        self.assertEqual(2, sut._depth(ItemFinishEvent))

        sut.finish_item()
        self.assertEqual(1, sut._depth(ItemFinishEvent))

        sut.start_item(MagicMock())
        self.assertEqual(2, sut._depth(ItemFinishEvent))

        sut.finish_item()
        self.assertEqual(1, sut._depth(ItemFinishEvent))

        sut.finish_item()
        self.assertEqual(0, sut._depth(ItemFinishEvent))

        sut.finish_section()
        self.assertEqual(1, sut._depth(SectionFinishEvent))

        sut.finish_section()
        self.assertEqual(0, sut._depth(SectionFinishEvent))

        sut.finish_scope()
        self.assertEqual(1, sut._depth(ScopeFinishEvent))

        sut.finish_scope()
        self.assertEqual(0, sut._depth(ScopeFinishEvent))

    def test_find_start_event(self) -> None:
        sut: JobStatusWriter = JobStatusWriter(MagicMock())
        mock_scope_1 = MagicMock()
        sut.start_scope(mock_scope_1)
        event = sut._find_start_event(ScopeFinishEvent)
        self.assertEqual(event.event, mock_scope_1)

        mock_scope_2 = MagicMock()
        sut.start_scope(mock_scope_2)
        event = sut._find_start_event(ScopeFinishEvent)
        self.assertEqual(event.event, mock_scope_2)

        sut.start_item("item")

        event = sut._find_start_event(ScopeFinishErrorEvent)
        self.assertEqual(event.event, mock_scope_2)

        event = sut._find_start_event(ItemFinishErrorsEvent)
        self.assertEqual("item", event.event)
        sut.finish_item()
        with self.assertRaises(JobException):
            _ = sut._find_start_event(ItemFinishErrorEvent)

        sut.start_section("name")
        event = sut._find_start_event(SectionFinishErrorEvent)
        self.assertEqual("name", event.event)

        sut.finish_section()
        with self.assertRaises(JobException):
            _ = sut._find_start_event(SectionFinishErrorsEvent)

        sut.finish_scope()
        event = sut._find_start_event(ScopeFinishEvent)
        self.assertEqual(event.event, mock_scope_1)

        sut.finish_scope()
        with self.assertRaises(JobException):
            _ = sut._find_start_event(ScopeFinishErrorsEvent)

    def test_find_start_event_negative(self) -> None:
        sut = JobStatusWriter(MagicMock())
        with self.assertRaises(JobException) as e:
            _ = sut._find_start_event(ErrorEvent)
        self.assertEqual("Event type does not have start/finish pairs.", str(e.exception))

        with self.assertRaises(JobException) as e:
            _ = sut._find_start_event(ScopeFinishEvent)
        self.assertEqual("Did not find start event.", str(e.exception))

        with self.assertRaises(JobException) as e:
            _ = sut._find_start_event(ScopeStartEvent)
        self.assertEqual("Event type is a start event.", str(e.exception))

    def test(self) -> None:
        expected: list[str] = []

        stream: StringIO = StringIO()
        sut: JobStatusWriter = JobStatusWriter(stream=stream)

        expected.append("# Job Job\n\n")
        sut.start_scope(StubScope("Job", "Job"), include_duration=False)

        expected.append("## Stage Stage1\n\n")
        sut.start_scope(StubScope("Stage1", "Stage"), include_duration=False)

        expected.append("### Step Step1.1\n\n")
        sut.start_scope(StubScope("Step1.1", "Step"), include_duration=False)

        expected.append(" - Step1.1.1...done.\n\n")
        sut.start_item("Step1.1.1")
        sut.finish_item("done.")

        expected.append("#### Section\n\n")
        sut.start_section("Section", include_duration=False)

        expected.append(" - Step1.1.2...done.\n\n")
        sut.start_item("Step1.1.2")
        sut.finish_item("done.")

        expected.append("Finished **Section**\n\n")
        sut.finish_section()

        expected.append("✅ Finished **Step Step1.1**\n\n")
        sut.finish_scope()

        expected.append("### Step Step1.2\n\n")
        sut.start_scope(StubScope("Step1.2", "Step"), include_duration=False)

        expected.append("✅ Finished **Step Step1.2**\n\n")
        sut.finish_scope()

        expected.append("✅ Finished **Stage Stage1**\n\n")
        sut.finish_scope()

        expected.append("## Stage Stage2\n\n")
        sut.start_scope(StubScope("Stage2", "Stage"), include_duration=False)

        expected.append("### Step Step2.1\n\n")
        sut.start_scope(StubScope("Step2.1", "Step"), include_duration=False)

        expected.append("✅ Finished **Step Step2.1**\n\n")
        sut.finish_scope()

        expected.append("### Step Step2.2\n\n")
        sut.start_scope(StubScope("Step2.2", "Step"), include_duration=False)

        expected.append(" - Step2.2.1...\n")
        sut.start_item("Step2.2.1")

        expected.append("   - Step2.2.2...done.\n")
        sut.start_item("Step2.2.2")
        sut.finish_item("done.")

        expected.append("   - Step2.2.3...done.\n")
        sut.start_item("Step2.2.3")
        sut.finish_item("done.")

        expected.append("   done.\n\n")
        sut.finish_item()

        expected.append("✅ Finished **Step Step2.2**\n\n")
        sut.finish_scope()

        expected.append("✅ Finished **Stage Stage2**\n\n")
        sut.finish_scope()

        expected.append("✅ Finished **Job Job**\n\n")
        sut.finish_scope()

        self.assertEqual("".join(expected), stream.getvalue())

    def test_get_errors(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)

        self.assertEqual([], sut._get_errors(ErrorEvent))

        sut.start_scope(StubScope("name", "type"))
        sut.error("error1")
        sut.start_section("section")
        sut.error("error2")
        sut.start_item("item")
        sut.error("error3")
        self.assertEqual(["error3"], sut._get_errors(ItemFinishEvent))
        self.assertEqual(["error3"], sut._get_errors(ItemFinishEvent, include_children=False))
        sut.finish_item()
        self.assertEqual(["error2", "error3"], sut._get_errors(SectionFinishEvent))
        self.assertEqual(["error2"], sut._get_errors(SectionFinishEvent, include_children=False))
        sut.finish_section()
        self.assertEqual(["error1", "error2", "error3"], sut._get_errors(ScopeFinishEvent))
        self.assertEqual(["error1"], sut._get_errors(ScopeFinishEvent, include_children=False))
        sut.finish_scope()

    def test_start_finish_scope(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)

        sut.start_scope(StubScope("name", "type"))

        self.assertEqual("# type name\n\n", stream.getvalue())

        sut.start_scope(StubScope("name2", "type2"), include_duration=False)
        self.assertEqual("# type name\n\n## type2 name2\n\n", stream.getvalue())

        sut.finish_scope()
        self.assertEqual("# type name\n\n## type2 name2\n\n✅ Finished **type2 name2**\n\n", stream.getvalue())

        sut.error("error1")
        sut.error("error2")
        sut.finish_scope()
        self.assertEqual(
            "# type name\n\n"
            "## type2 name2\n\n"
            "✅ Finished **type2 name2**\n\n"
            "❌ error1\n\n"
            "❌ error2\n\n"
            "❌ Finished **type name** (0s)\n"
            " - ❌ error1\n"
            " - ❌ error2\n\n",
            stream.getvalue(),
        )

    def test_skip_scope(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        sut.skip_scope(StubScope("name", "type"), "Disabled")
        self.assertEqual("**Skipping type name (Disabled)**\n\n", stream.getvalue())

    def test_start_finish_section(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)

        sut.start_section("name")
        self.assertEqual("# name\n\n", stream.getvalue())

        sut.start_section("name2", include_duration=False)
        self.assertEqual("# name\n\n## name2\n\n", stream.getvalue())

        sut.finish_section("name2")
        self.assertEqual("# name\n\n## name2\n\nFinished **name2**\n\n", stream.getvalue())

        sut.error("error")
        sut.finish_section("name")
        self.assertEqual(
            "# name\n\n## name2\n\nFinished **name2**\n\n❌ error\n\n\u274c Finished **name** (0s)\n❌ error\n\n",
            stream.getvalue(),
        )

    def test_start_finish_item(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        sut.start_item("foo")
        self.assertEqual(" - foo...", stream.getvalue())

        sut.finish_item("done.")
        self.assertEqual(" - foo...done.\n", stream.getvalue())

    def test_start_finish_item_include_duration(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        sut.start_item("foo", include_duration=True)
        self.assertEqual(" - foo...", stream.getvalue())

        sut.finish_item("done.")
        self.assertEqual(" - foo...done. (0s)\n", stream.getvalue())

    def test_start_finish_item_error(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)

        sut.start_item("foo")
        self.assertEqual(" - foo...", stream.getvalue())

        sut.error("error")
        sut.finish_item("foo")
        self.assertEqual(" - foo...❌ error\n", stream.getvalue())

    def test_start_finish_item_error_multiple(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)

        sut.start_item("foo")
        self.assertEqual(" - foo...", stream.getvalue())

        sut.error("error1")
        sut.error("error2")
        sut.error(Exception("error3"))
        sut.finish_item("foo")

        self.assertEqual(" - foo...❌\n   - ❌ error1\n" "   - ❌ error2\n" "   - ❌ error3\n", stream.getvalue())

    def test_start_finish_inner_item_error_multiple(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)

        sut.start_item("foo")
        self.assertEqual(" - foo...", stream.getvalue())

        sut.start_item("bar")
        self.assertEqual(" - foo...\n" "   - bar...", stream.getvalue())

        sut.error("error1")
        sut.error("error2")
        sut.error(Exception("error3"))
        sut.finish_item("bar")
        sut.finish_item("foo")

        self.assertEqual(
            " - foo...\n" "   - bar...❌\n" "     - ❌ error1\n" "     - ❌ error2\n" "     - ❌ error3\n   foo\n",
            stream.getvalue(),
        )

    def test_duration_format(self) -> None:
        self.assertEqual("0s", JobStatusWriterEvent._format_duration(timedelta()))
        self.assertEqual("1.000s", JobStatusWriterEvent._format_duration(timedelta(seconds=1)))
        self.assertEqual("5s", JobStatusWriterEvent._format_duration(timedelta(seconds=5, milliseconds=1)))
        self.assertEqual("0.001s", JobStatusWriterEvent._format_duration(timedelta(milliseconds=1)))
        self.assertEqual("1.001s", JobStatusWriterEvent._format_duration(timedelta(seconds=1, milliseconds=1)))
        self.assertEqual("4m1s", JobStatusWriterEvent._format_duration(timedelta(minutes=4, seconds=1, milliseconds=1)))
        self.assertEqual(
            "26h3m",
            JobStatusWriterEvent._format_duration(timedelta(days=1, hours=2, minutes=3, seconds=4, milliseconds=5)),
        )

    def test_info(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        sut.info("info")
        self.assertEqual("info\n\n", stream.getvalue())

    def test_detail(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        sut.detail("detail")
        self.assertEqual("🔎 detail\n\n", stream.getvalue())

    def test_detail_quiet(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream, show_detail=False)
        sut.detail("detail")
        self.assertEqual("", stream.getvalue())

    def test_warning(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        sut.warning("warning")
        self.assertEqual("⚠️ warning\n\n", stream.getvalue())

    def test_error(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        sut.error("error")
        self.assertEqual("❌ error\n\n", stream.getvalue())

    def test_output(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        sut.start_section("Some code")
        sut.info("Here it is:")
        sut.output(["some Code {\n", "  var foo = bar;\n  print(foo);\n", "};\n"], label="Some code")
        sut.finish_section()
        self.assertEqual(
            "# Some code\n\n"
            "Here it is:\n\n"
            "Some code:\n\n"
            "    some Code {\n"
            "      var foo = bar;\n"
            "      print(foo);\n"
            "    };\n\n"
            "Finished **Some code** (0s)\n\n",
            stream.getvalue(),
        )

    def test_output_as_str(self) -> None:
        stream: StringIO = StringIO()
        sut = JobStatusWriter(stream=stream)
        sut.output("Some output")
        self.assertEqual("output:\n\n    Some output\n\n", stream.getvalue())


class StubScopeType(Enum):
    JOB = auto()
    STAGE = auto()
    STEP = auto()


class TestJobContextImpl(TestCase):
    def test_in_scope(self):
        sut = JobContextImpl()
        mock_scope = MagicMock()
        with sut.in_scope(mock_scope):
            self.assertEqual(mock_scope, sut._state_stack[0].scope)
        self.assertEqual([], sut._state_stack)

    def test_get_state(self):
        sut = JobContextImpl()
        with self.assertRaises(JobException) as e:
            _ = sut._get_state(None)
        self.assertEqual("No state found", str(e.exception))

        mock_scope_1 = MagicMock()
        mock_scope_1.name = "scope_1"
        mock_scope_2 = MagicMock()
        mock_scope_2.name = "scope_2"
        with sut.in_scope(mock_scope_1):
            self.assertIsNotNone(sut._get_state(mock_scope_1))

            with sut.in_scope(mock_scope_2):
                self.assertIsNotNone(sut._get_state(mock_scope_2))

            with self.assertRaises(JobException) as e:
                _ = sut._get_state(mock_scope_2)
            self.assertEqual("No state found for scope 'scope_2'", str(e.exception))

        with self.assertRaises(JobException):
            _ = sut._get_state(None)

    def test_scope(self):
        sut = JobContextImpl()
        mock_scope_1 = MagicMock()
        mock_scope_1.name = "scope_1"
        mock_scope_2 = MagicMock()
        mock_scope_2.name = "scope_2"
        with sut.in_scope(mock_scope_1):
            self.assertIs(mock_scope_1, sut.scope)

            with sut.in_scope(mock_scope_2):
                self.assertIs(mock_scope_2, sut.scope)

            self.assertIs(mock_scope_1, sut.scope)

    def test_scopes(self) -> None:
        mock_scope_1 = MagicMock()
        mock_scope_1.name = "scope_1"
        mock_scope_2 = MagicMock()
        mock_scope_2.name = "scope_2"
        mock_scope_3 = MagicMock()
        mock_scope_3.name = "scope_3"

        sut = JobContextImpl()
        with sut.in_scope(mock_scope_1):
            with sut.in_scope(mock_scope_2):
                with sut.in_scope(mock_scope_3):
                    self.assertEqual((mock_scope_1, mock_scope_2, mock_scope_3), sut.scopes)
                self.assertEqual((mock_scope_1, mock_scope_2), sut.scopes)
            self.assertEqual((mock_scope_1,), sut.scopes)
        self.assertEqual(tuple(), sut.scopes)

    def test_error(self):
        self.assertEqual("JobException('Foo')", repr(JobContextImpl().error("Foo")))
        bar_exception = Exception("Bar")
        self.assertEqual(bar_exception, JobContextImpl().error(bar_exception))

    def test_get_errors(self):
        sut = JobContextImpl()

        foo_error = Exception("Foo")
        bar_error = Exception("Bar")
        baz_error = Exception("Baz")
        buz_error = Exception("Buz")
        boz_error = Exception("Boz")

        sut.status.error(foo_error)
        sut.status.error(bar_error)

        mock_scope = MagicMock()
        sut.status.start_scope(mock_scope)
        sut.status.error(baz_error)

        mock_scope_2 = MagicMock()
        sut.status.start_scope(mock_scope_2)
        sut.status.error(buz_error)
        sut.status.finish_scope(mock_scope_2)

        sut.status.error(boz_error)
        sut.status.finish_scope(mock_scope)

        self.assertEqual([foo_error, bar_error, baz_error, boz_error, buz_error], sut.get_errors())
        self.assertEqual([baz_error, boz_error, buz_error], sut.get_errors(mock_scope))
        self.assertEqual([buz_error], sut.get_errors(mock_scope_2))

    def test_values(self) -> None:
        sut = JobContextImpl()
        self.assertIsInstance(sut.values, Values)
