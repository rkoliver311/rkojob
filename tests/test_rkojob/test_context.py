from enum import Enum, auto
from unittest import TestCase
from unittest.mock import MagicMock

from rkojob import JobException, JobScopeStatus, Values
from rkojob.context import (
    JobContextImpl,
    JobScopeStatuses,
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
