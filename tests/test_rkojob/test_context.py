# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from enum import Enum, auto
from unittest import TestCase
from unittest.mock import MagicMock

from rkojob import (
    Delegate,
    JobContext,
    JobException,
    JobScopeStatus,
    Values,
    create_scope_id,
)
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
    def __init__(self, name, type, teardown=None, id=None):
        self.name = name
        self.type = type
        self.teardown = Delegate[[JobContext], None](continue_on_error=True, reverse=True)
        if teardown:
            self.teardown += teardown
        self.id = id or create_scope_id()

    def __str__(self):
        return f"{self.type} {self.name}"


class StubScopeType(Enum):
    JOB = auto()
    STAGE = auto()
    STEP = auto()

    def __str__(self):
        return self.name.capitalize()


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
        self.assertEqual("Context has no scope", str(e.exception))

        mock_scope_1 = StubScope("scope_1", StubScopeType.JOB)
        mock_scope_2 = StubScope("scope_2", StubScopeType.STAGE)
        mock_scope_2_id = MagicMock(id=mock_scope_2.id)

        with sut.in_scope(mock_scope_1):
            self.assertIs(mock_scope_1, sut._get_state(mock_scope_1).scope)

            with sut.in_scope(mock_scope_2):
                self.assertIs(mock_scope_2, sut._get_state(mock_scope_2_id).scope)

            with self.assertRaises(JobException) as e:
                _ = sut._get_state(mock_scope_2)
            self.assertEqual("No state found for scope 'Stage scope_2'", str(e.exception))

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

    def test_get_scope(self) -> None:
        class StubScopeID:
            def __init__(self, id):
                self.id = id

        sut = JobContextImpl()

        with self.assertRaises(JobException) as e:
            _ = sut.get_scope()
        self.assertEqual("Context has no scope", str(e.exception))

        mock_scope_1 = MagicMock()
        mock_scope_1.name = "scope_1"
        mock_scope_1.id = "scope_id"
        with sut.in_scope(mock_scope_1):
            self.assertIs(mock_scope_1, sut.get_scope())
            self.assertIs(mock_scope_1, sut.get_scope(StubScopeID("scope_id")))

            # generation == 0: current scope
            self.assertIs(mock_scope_1, sut.get_scope(generation=0))
            # generation == -1: root scope
            self.assertIs(mock_scope_1, sut.get_scope(generation=-1))

            mock_scope_2 = MagicMock()
            mock_scope_2.name = "scope_2"

            with sut.in_scope(mock_scope_2):
                self.assertIs(mock_scope_1, sut.get_scope(generation=1))
                self.assertIs(mock_scope_1, sut.get_scope(generation=-1))

                mock_scope_3 = MagicMock()
                mock_scope_3.name = "scope_3"

                with sut.in_scope(mock_scope_3):
                    self.assertIs(mock_scope_3, sut.get_scope())
                    self.assertIs(mock_scope_2, sut.get_scope(generation=1))
                    self.assertIs(mock_scope_1, sut.get_scope(generation=2))
                    self.assertIs(mock_scope_1, sut.get_scope(generation=-1))
                    self.assertIs(mock_scope_2, sut.get_scope(generation=-2))

                    with self.assertRaises(JobException) as e:
                        _ = sut.get_scope(mock_scope_3, generation=-4)
                    self.assertEqual("Unable to get scope relative to root using generation=-4", str(e.exception))

                    with self.assertRaises(JobException) as e:
                        _ = sut.get_scope(mock_scope_3, generation=3)
                    self.assertEqual(
                        f"Unable to get scope relative to {mock_scope_3} using generation=3", str(e.exception)
                    )

                with self.assertRaises(JobException) as e:
                    _ = sut.get_scope(mock_scope_3, generation=1)
                self.assertEqual(f"Scope '{mock_scope_3}' is not in scope", str(e.exception))

    def test_resolve_scope(self) -> None:
        class StubScopeID:
            def __init__(self, id):
                self.id = id

        mock_scope = MagicMock(id="scope_id")

        sut = JobContextImpl()
        stub_scope_id = StubScopeID("scope_id")

        with self.assertRaises(JobException) as e:
            _ = sut._resolve_scope(stub_scope_id)
        self.assertEqual("Scope with ID 'scope_id' is not known to this context.", str(e.exception))

        with sut.in_scope(mock_scope):
            self.assertEqual(mock_scope, sut._resolve_scope(stub_scope_id))

        # resolves even after leaving scope
        self.assertEqual(mock_scope, sut._resolve_scope(stub_scope_id))

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

    def test_teardown(self) -> None:
        def callback(context):
            pass

        sut = JobContextImpl()
        scope = StubScope("scope", 0)
        with self.assertRaises(JobException) as e:
            sut.add_teardown(scope, callback)
        self.assertEqual("Context has no scope", str(e.exception))

        with sut.in_scope(scope):
            sut.add_teardown(scope, callback)
            self.assertEqual([callback], sut._get_state(scope).teardown._callbacks)

            sut.remove_teardown(scope, callback)
            self.assertEqual([], sut._get_state(scope).teardown._callbacks)

        class NonTeardownScope:
            name = "scope"
            type = StubScopeType.JOB
            id = "id"

        with sut.in_scope(NonTeardownScope()) as non_teardown_scope:
            with self.assertRaises(JobException) as e:
                sut.add_teardown(non_teardown_scope, callback)
            self.assertEqual(f"Scope {non_teardown_scope} does not support teardown.", str(e.exception))
            with self.assertRaises(JobException) as e:
                sut.remove_teardown(non_teardown_scope, callback)
            self.assertEqual(f"Scope {non_teardown_scope} does not support teardown.", str(e.exception))
            with self.assertRaises(JobException) as e:
                sut.get_teardown(non_teardown_scope)
            self.assertEqual(f"Scope {non_teardown_scope} does not support teardown.", str(e.exception))

    def test_get_scope_status(self) -> None:
        sut = JobContextImpl()
        with sut.in_scope(MagicMock()) as mock_scope:
            sut.status.start_scope(mock_scope)
            sut.status.error(mock_scope)
            self.assertEqual(JobScopeStatus.FAILING, sut.get_scope_status(mock_scope))
            sut.status.finish_scope(mock_scope)
            self.assertEqual(JobScopeStatus.FAILED, sut.get_scope_status(mock_scope))

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
