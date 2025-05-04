from enum import Enum, auto
from unittest import TestCase
from unittest.mock import MagicMock

from rkojob import JobException
from rkojob.context import JobContextImpl


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

    def test_exception(self):
        self.assertEqual("JobException('Foo')", repr(JobContextImpl().exception("Foo")))
        bar_exception = Exception("Bar")
        self.assertEqual(bar_exception, JobContextImpl().exception(bar_exception))

    def test_get_exceptions(self):
        sut = JobContextImpl()

        foo_error = Exception("Foo")
        bar_error = Exception("Bar")
        baz_error = Exception("Baz")
        buz_error = Exception("Buz")
        boz_error = Exception("Boz")

        sut.exception(foo_error)
        sut.exception(bar_error)

        mock_scope = MagicMock()
        with sut.in_scope(mock_scope):
            sut.exception(baz_error)

            mock_scope_2 = MagicMock()
            with sut.in_scope(mock_scope_2):
                sut.exception(buz_error)
            sut.exception(boz_error)
        self.assertEqual(
            {
                tuple(): [foo_error, bar_error],
                (mock_scope,): [baz_error, boz_error],
                (mock_scope, mock_scope_2): [buz_error],
            },
            sut._exceptions,
        )

        self.assertEqual([foo_error, bar_error, baz_error, boz_error, buz_error], sut.get_exceptions())
        self.assertEqual([baz_error, boz_error, buz_error], sut.get_exceptions(mock_scope))
        self.assertEqual([buz_error], sut.get_exceptions(mock_scope_2))
