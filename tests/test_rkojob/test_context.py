# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from enum import Enum, auto
from typing import cast
from unittest import TestCase
from unittest.mock import MagicMock

from rkojob import (
    Delegate,
    JobContext,
    JobEvent,
    JobException,
    JobScopeStatus,
    Values,
    create_scope_id,
)
from rkojob.context import (
    JobContextImpl,
    JobScopeStatuses,
)
from rkojob.events import (
    JobErrorEvent,
    JobFinishItemEvent,
    JobFinishScopeEvent,
    JobSkipScopeEvent,
    JobStartItemEvent,
    JobStartScopeEvent,
)
from rkojob.job import JobScopeIDMixin
from tests.test_rkojob.test_runner import StubGroupScope


class TestJobScopeStatuses(TestCase):
    def test(self) -> None:
        mock_context = MagicMock()
        mock_scope_1 = MagicMock()
        mock_scope_2 = MagicMock()
        mock_scope_3 = MagicMock()

        sut = JobScopeStatuses()
        self.assertEqual(JobScopeStatus.UNKNOWN, sut.get_status(mock_scope_1))
        self.assertEqual(JobScopeStatus.UNKNOWN, sut.get_status(mock_scope_2))
        self.assertEqual(JobScopeStatus.UNKNOWN, sut.get_status(mock_scope_3))

        sut.handle(JobStartScopeEvent(mock_context, None, started_scope=mock_scope_1))
        self.assertEqual(JobScopeStatus.RUNNING, sut.get_status(mock_scope_1))
        self.assertEqual(JobScopeStatus.UNKNOWN, sut.get_status(mock_scope_2))
        self.assertEqual(JobScopeStatus.UNKNOWN, sut.get_status(mock_scope_3))

        sut.handle(JobSkipScopeEvent(mock_context, mock_scope_1, skipped_scope=mock_scope_2))
        self.assertEqual(JobScopeStatus.RUNNING, sut.get_status(mock_scope_1))
        self.assertEqual(JobScopeStatus.SKIPPED, sut.get_status(mock_scope_2))
        self.assertEqual(JobScopeStatus.UNKNOWN, sut.get_status(mock_scope_3))

        with self.assertRaises(JobException) as e:
            sut.handle(JobFinishScopeEvent(mock_context, None, finished_scope=mock_scope_2))
        self.assertEqual("Scope does not match scope on stack.", str(e.exception))

        with self.assertRaises(JobException) as e:
            sut.handle(JobStartScopeEvent(mock_context, mock_scope_1, started_scope=mock_scope_2))
        self.assertEqual("Scope status already set.", str(e.exception))

        sut.handle(JobStartScopeEvent(mock_context, mock_scope_1, started_scope=mock_scope_3))
        self.assertEqual(JobScopeStatus.RUNNING, sut.get_status(mock_scope_1))
        self.assertEqual(JobScopeStatus.SKIPPED, sut.get_status(mock_scope_2))
        self.assertEqual(JobScopeStatus.RUNNING, sut.get_status(mock_scope_3))

        sut.handle(JobFinishScopeEvent(mock_context, mock_scope_1, finished_scope=mock_scope_3))
        self.assertEqual(JobScopeStatus.RUNNING, sut.get_status(mock_scope_1))
        self.assertEqual(JobScopeStatus.SKIPPED, sut.get_status(mock_scope_2))
        self.assertEqual(JobScopeStatus.PASSED, sut.get_status(mock_scope_3))

        sut.handle(JobErrorEvent(mock_context, mock_scope_1, "error"))
        sut.handle(JobFinishScopeEvent(mock_context, None, finished_scope=mock_scope_1))
        self.assertEqual(JobScopeStatus.FAILED, sut.get_status(mock_scope_1))
        self.assertEqual(JobScopeStatus.SKIPPED, sut.get_status(mock_scope_2))
        self.assertEqual(JobScopeStatus.PASSED, sut.get_status(mock_scope_3))

    def test_finish_item(self) -> None:
        mock_context = MagicMock()
        mock_scope_1 = MagicMock()

        sut = JobScopeStatuses()
        self.assertEqual(JobScopeStatus.UNKNOWN, sut.get_status(mock_scope_1))

        sut.handle(JobStartScopeEvent(mock_context, None, started_scope=mock_scope_1))
        self.assertEqual(JobScopeStatus.RUNNING, sut.get_status(mock_scope_1))

        sut.handle(JobStartItemEvent(mock_context, mock_scope_1, "item"))
        self.assertEqual(JobScopeStatus.RUNNING, sut.get_status(mock_scope_1))

        sut.handle(JobErrorEvent(mock_context, mock_scope_1, "error"))
        sut.handle(JobFinishItemEvent(mock_context, mock_scope_1, "item"))
        self.assertEqual(JobScopeStatus.FAILING, sut.get_status(mock_scope_1))

        sut.handle(JobFinishScopeEvent(mock_context, None, finished_scope=mock_scope_1))
        self.assertEqual(JobScopeStatus.FAILED, sut.get_status(mock_scope_1))

    def test_get_errors(self) -> None:
        mock_context = MagicMock()
        mock_scope_1 = MagicMock()
        mock_scope_2 = MagicMock()
        mock_scope_3 = MagicMock()

        sut = JobScopeStatuses()
        sut.handle(JobStartScopeEvent(mock_context, None, started_scope=mock_scope_1))
        sut.handle(JobStartScopeEvent(mock_context, mock_scope_1, started_scope=mock_scope_2))
        sut.handle(JobStartScopeEvent(mock_context, mock_scope_2, started_scope=mock_scope_3))

        self.assertEqual([], sut.get_errors(mock_scope_1))
        self.assertEqual([], sut.get_errors(mock_scope_2))
        self.assertEqual([], sut.get_errors(mock_scope_3))
        self.assertEqual([], sut.get_errors(None))

        sut.handle(JobErrorEvent(mock_context, mock_scope_3, "error"))
        self.assertEqual(["error"], sut.get_errors(mock_scope_1))
        self.assertEqual(["error"], sut.get_errors(mock_scope_2))
        self.assertEqual(["error"], sut.get_errors(mock_scope_3))
        self.assertEqual(["error"], sut.get_errors(None))

        sut.handle(JobFinishScopeEvent(mock_context, mock_scope_2, finished_scope=mock_scope_3))

        sut.handle(JobErrorEvent(mock_context, mock_scope_2, "error2"))
        self.assertEqual(["error", "error2"], sut.get_errors(mock_scope_1))
        self.assertEqual(["error", "error2"], sut.get_errors(mock_scope_2))
        self.assertEqual(["error"], sut.get_errors(mock_scope_3))
        self.assertEqual(["error", "error2"], sut.get_errors(None))

        sut.handle(JobFinishScopeEvent(mock_context, mock_scope_1, finished_scope=mock_scope_2))

        sut.handle(JobErrorEvent(mock_context, mock_scope_1, "error3"))
        self.assertEqual(["error", "error2", "error3"], sut.get_errors(mock_scope_1))
        self.assertEqual(["error", "error2"], sut.get_errors(mock_scope_2))
        self.assertEqual(["error"], sut.get_errors(mock_scope_3))
        self.assertEqual(["error", "error2", "error3"], sut.get_errors(None))

        sut.handle(JobFinishScopeEvent(mock_context, None, finished_scope=mock_scope_1))

        sut.handle(JobErrorEvent(mock_context, None, "error4"))
        self.assertEqual(["error", "error2", "error3"], sut.get_errors(mock_scope_1))
        self.assertEqual(["error", "error2"], sut.get_errors(mock_scope_2))
        self.assertEqual(["error"], sut.get_errors(mock_scope_3))
        self.assertEqual(["error", "error2", "error3", "error4"], sut.get_errors(None))

    def test_get_report(self) -> None:
        mock_context = MagicMock()
        stub_scope_1 = StubScopeID("scope-1")
        stub_scope_2 = StubScopeID("scope-2")
        stub_scope_3 = StubScopeID("scope-3")

        sut = JobScopeStatuses()
        sut.handle(JobStartScopeEvent(mock_context, None, started_scope=stub_scope_1))
        sut.handle(JobStartScopeEvent(mock_context, stub_scope_1, started_scope=stub_scope_2))
        sut.handle(JobStartScopeEvent(mock_context, stub_scope_2, started_scope=stub_scope_3))

        sut.handle(JobErrorEvent(mock_context, stub_scope_3, "error"))

        sut.handle(JobFinishScopeEvent(mock_context, stub_scope_2, finished_scope=stub_scope_3))

        sut.handle(JobErrorEvent(mock_context, stub_scope_2, "error2"))

        sut.handle(JobFinishScopeEvent(mock_context, stub_scope_1, finished_scope=stub_scope_2))

        sut.handle(JobErrorEvent(mock_context, stub_scope_1, "error3"))

        sut.handle(JobFinishScopeEvent(mock_context, None, finished_scope=stub_scope_1))

        sut.handle(JobErrorEvent(mock_context, None, "error4"))

        self.assertEqual(
            {
                stub_scope_1: {
                    "status": JobScopeStatus.FAILED,
                    "errors": ["error3"],
                    "scopes": {
                        stub_scope_2: {
                            "status": JobScopeStatus.FAILED,
                            "errors": ["error2"],
                            "scopes": {
                                stub_scope_3: {"status": JobScopeStatus.FAILED, "errors": ["error"], "scopes": {}}
                            },
                        }
                    },
                }
            },
            sut.get_report(),
        )
        self.assertEqual(
            {stub_scope_3: {"status": JobScopeStatus.FAILED, "errors": ["error"], "scopes": {}}},
            sut.get_report(stub_scope_3),
        )


class StubScopeID(JobScopeIDMixin):
    def __init__(self, id):
        self._id = id

    def __repr__(self):
        return repr(self.id)


class StubScope(JobScopeIDMixin):
    def __init__(self, name, type, teardown=None, id=None):
        self.name = name
        self.type = type
        self.teardown = Delegate[[JobContext], None](continue_on_error=True, reverse=True)
        if teardown:
            self.teardown += teardown
        self._id = id or create_scope_id()
        self.concurrent = False

    def __str__(self):
        return f"{self.type} {self.name}"


class StubScopeType(Enum):
    JOB = auto()
    STAGE = auto()
    STEP = auto()

    def __str__(self):
        return self.name.capitalize()


class TestJobContextImpl(TestCase):
    def test_push_pop_scope(self):
        sut = JobContextImpl()
        stub_scope = StubScope("scope", "type")
        sut.push_scope(stub_scope)
        self.assertIs(stub_scope, sut._scope_stack.scope)
        sut.pop_scope()
        self.assertFalse(sut._scope_stack)
        with self.assertRaises(JobException) as e:
            sut.pop_scope()
        self.assertEqual("Scope stack underflow.", str(e.exception))

    def test_start_finish_scope_react(self):
        sut = JobContextImpl()
        stub_scope = StubScope("scope", "type")
        with sut.events.scope(stub_scope):
            self.assertIs(stub_scope, sut._scope_stack.scope)
        self.assertFalse(sut._scope_stack)

    def test_scope(self):
        sut = JobContextImpl()
        stub_scope_1 = StubScope("scope_1", "type")
        stub_scope_2 = StubScope("scope_2", "type")

        with sut.events.scope(stub_scope_1):
            self.assertIs(stub_scope_1, sut.scope)

            with sut.events.scope(stub_scope_2):
                self.assertIs(stub_scope_2, sut.scope)

            self.assertIs(stub_scope_1, sut.scope)

    def test_get_scope(self) -> None:
        sut = JobContextImpl()

        self.assertIsNone(sut.get_scope())

        stub_scope_1 = StubScope("scope_1", "type", id="scope_id")
        sut.push_scope(stub_scope_1)
        self.assertIs(stub_scope_1, sut.get_scope())
        self.assertIs(stub_scope_1, sut.get_scope(StubScopeID("scope_id")))

        # generation == 0: current scope
        self.assertIs(stub_scope_1, sut.get_scope(generation=0))
        # generation == -1: root scope
        self.assertIs(stub_scope_1, sut.get_scope(generation=-1))

        stub_scope_2 = StubScope("scope_2", "type")

        sut.push_scope(stub_scope_2)
        self.assertIs(stub_scope_1, sut.get_scope(generation=1))
        self.assertIs(stub_scope_1, sut.get_scope(generation=-1))

        stub_scope_3 = StubScope("scope_3", "type")

        sut.push_scope(stub_scope_3)
        self.assertIs(stub_scope_3, sut.get_scope())
        self.assertIs(stub_scope_2, sut.get_scope(generation=1))
        self.assertIs(stub_scope_1, sut.get_scope(generation=2))
        self.assertIs(stub_scope_1, sut.get_scope(generation=-1))
        self.assertIs(stub_scope_2, sut.get_scope(generation=-2))

        with self.assertRaises(JobException) as e:
            _ = sut.get_scope(stub_scope_3, generation=-4)
        self.assertEqual("Unable to get scope relative to root using generation=-4", str(e.exception))

        self.assertIsNone(sut.get_scope(stub_scope_3, generation=3))

        sut.pop_scope()

        with self.assertRaises(JobException) as e:
            _ = sut.get_scope(stub_scope_3, generation=1)
        self.assertEqual(f"Scope '{stub_scope_3}' is not in scope", str(e.exception))

    def test_resolve_scope(self) -> None:
        mock_scope = MagicMock(id="scope_id")

        sut = JobContextImpl()
        stub_scope_id = StubScopeID("scope_id")

        with self.assertRaises(JobException) as e:
            _ = sut._resolve_scope(stub_scope_id)
        self.assertEqual("Scope with ID 'scope_id' is not known to this context.", str(e.exception))

        sut.push_scope(mock_scope)
        self.assertEqual(mock_scope, sut._resolve_scope(stub_scope_id))
        sut.pop_scope()

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
        sut.push_scope(mock_scope_1)
        sut.push_scope(mock_scope_2)
        sut.push_scope(mock_scope_3)
        self.assertEqual((mock_scope_1, mock_scope_2, mock_scope_3), sut.scopes)

        sut.pop_scope()
        self.assertEqual((mock_scope_1, mock_scope_2), sut.scopes)

        sut.pop_scope()
        self.assertEqual((mock_scope_1,), sut.scopes)

        sut.pop_scope()
        self.assertEqual(tuple(), sut.scopes)

    def test_teardown(self) -> None:
        def callback(context):
            pass

        sut = JobContextImpl()
        scope = StubScope("scope", 0)
        with self.assertRaises(JobException) as e:
            sut.add_teardown(scope, callback)
        self.assertEqual(f"Scope {scope} is not an active scope.", str(e.exception))

        with self.assertRaises(JobException) as e:
            sut.remove_teardown(scope, callback)
        self.assertEqual(f"Scope {scope} is not an active scope.", str(e.exception))

        with self.assertRaises(JobException) as e:
            sut.get_teardown(scope)
        self.assertEqual(f"Scope {scope} is not an active scope.", str(e.exception))

        sut.push_scope(scope)
        sut.add_teardown(scope, callback)
        self.assertEqual([callback], sut._scope_stack[scope].teardown._callbacks)

        sut.remove_teardown(scope, callback)
        self.assertEqual([], sut._scope_stack[scope].teardown._callbacks)
        sut.pop_scope()

        class NonTeardownScope:
            name = "scope"
            type = StubScopeType.JOB
            id = "id"
            concurrent = False

        non_teardown_scope = NonTeardownScope()
        sut.push_scope(non_teardown_scope)
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
        stub_scope = StubScope("name", "type")
        with sut.events.scope(stub_scope):
            sut.events.error("error")
            self.assertEqual(JobScopeStatus.FAILING, sut.get_scope_status(stub_scope))
        self.assertEqual(JobScopeStatus.FAILED, sut.get_scope_status(stub_scope))

    def test_error(self):
        sut = JobContextImpl()
        stub_scope = StubScope("name", "type")
        with sut.events.scope(stub_scope):
            self.assertEqual("JobException('Foo')", repr(sut.error("Foo")))
            bar_exception = Exception("Bar")
            self.assertEqual(bar_exception, sut.error(bar_exception))

    def test_get_errors(self):
        sut = JobContextImpl()

        foo_error = Exception("Foo")
        bar_error = Exception("Bar")
        baz_error = Exception("Baz")
        buz_error = Exception("Buz")
        boz_error = Exception("Boz")

        stub_scope_0 = StubScope("stub_scope_0", "type")
        with sut.events.scope(stub_scope_0):

            sut.events.error(foo_error)
            sut.events.error(bar_error)

            stub_scope_1 = StubScope("stub_scope_1", "type")
            with sut.events.scope(stub_scope_1):
                sut.events.error(baz_error)

                stub_scope_2 = StubScope("stub_scope_2", "type")
                with sut.events.scope(stub_scope_2):
                    sut.events.error(buz_error)

                sut.events.error(boz_error)

        self.assertEqual([buz_error, baz_error, boz_error, foo_error, bar_error], sut.get_errors())
        self.assertEqual([buz_error, baz_error, boz_error], sut.get_errors(stub_scope_1))
        self.assertEqual([buz_error], sut.get_errors(stub_scope_2))

    def test_values(self) -> None:
        sut = JobContextImpl()
        self.assertIsInstance(sut.values, Values)

    def test_get_report(self) -> None:
        sut = JobContextImpl()
        self.assertEqual({}, sut.get_report())

    def test_fork_join(self) -> None:
        class StubHandler:
            def __init__(self) -> None:
                self.events: list[JobEvent] = []

            def handle(self, event: JobEvent) -> None:
                self.events.append(event)

        sut = JobContextImpl()
        with sut.events.scope(StubScope("scope", "type")):
            handler = StubHandler()
            sut._shared_state.events.add_handler(handler)
            fork = cast(JobContextImpl, sut.fork())
            self.assertIs(fork._shared_state, sut._shared_state)
            self.assertIsNot(fork._scope_stack, sut._scope_stack)

            fork.events.info("Hello!")
            self.assertEqual([], handler.events)

            fork.join()
            self.assertEqual([{"message": "Hello!"}], [event.data for event in handler.events])

    def test_get_futures(self) -> None:
        stub_scope = StubScope("scope", "scope")
        stub_group_scope = StubGroupScope("group-scope", "group", scopes=[stub_scope])

        side_effects: list[str] = []

        sut: JobContextImpl = JobContextImpl()
        with sut.events.scope(stub_group_scope):
            with sut.events.scope(stub_scope):
                futures = sut.get_futures(stub_group_scope)

                def task(context: JobContext, format: str) -> None:
                    side_effects.append(format.format(context.scope))

                futures.submit(sut, task, sut, "Hello from {0}!")
            futures.futures[0].result()
        self.assertEqual([f"Hello from {stub_scope}!"], side_effects)

    def test_get_futures_negative(self) -> None:
        sut: JobContextImpl = JobContextImpl()

        stub_scope = StubScope("scope", "scope")
        stub_group_scope = StubGroupScope("group-scope", "group", scopes=[stub_scope])
        with self.assertRaises(JobException) as e:
            _ = sut.get_futures(stub_group_scope)
        self.assertEqual(f"Scope {stub_group_scope} is not an active scope.", str(e.exception))

        with sut.events.scope(stub_scope):
            with self.assertRaises(JobException) as e:
                _ = sut.get_futures(stub_scope)
            self.assertEqual(f"Scope {stub_scope} does not support futures.", str(e.exception))
