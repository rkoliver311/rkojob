# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from unittest import TestCase
from unittest.mock import MagicMock, call

from rkojob import (
    JobEvent,
    JobException,
    JobScopeStack,
    create_context_id,
    create_scope_id,
)
from rkojob.events import (
    JobBufferedEventHandler,
    JobDetailEvent,
    JobDirectEventDispatcher,
    JobErrorEvent,
    JobFinishItemEvent,
    JobFinishScopeEvent,
    JobFinishScopeTeardownEvent,
    JobFinishSectionEvent,
    JobForkContextEvent,
    JobInfoEvent,
    JobInterruptScopeEvent,
    JobJoinContextEvent,
    JobLocalEventDispatcher,
    JobOutputEvent,
    JobRoutingEventDispatcher,
    JobSkipScopeEvent,
    JobStartItemEvent,
    JobStartScopeEvent,
    JobStartScopeTeardownEvent,
    JobStartSectionEvent,
    JobStatusImpl,
    JobWarningEvent,
)


class TestJobForkContextEvent(TestCase):
    def test(self) -> None:
        mock_context = MagicMock()
        mock_scope = MagicMock()
        forked_context = MagicMock()
        sut = JobForkContextEvent(mock_context, mock_scope, forked_context=forked_context)
        self.assertIs(mock_context, sut.context)
        self.assertIs(mock_scope, sut.scope)
        self.assertIs(forked_context, sut.forked_context)


class TestJobJoinContextEvent(TestCase):
    def test(self) -> None:
        mock_context = MagicMock()
        mock_scope = MagicMock()
        joined_context = MagicMock()
        sut = JobJoinContextEvent(mock_context, mock_scope, joined_context=joined_context)
        self.assertIs(mock_context, sut.context)
        self.assertIs(mock_scope, sut.scope)
        self.assertIs(joined_context, sut.joined_context)


class StubContext:
    def __init__(self):
        self.id = create_context_id()
        self._scopes = JobScopeStack()

    def handle(self, event):
        if event.context.id == self.id:
            if isinstance(event, JobStartScopeEvent):
                self._scopes.push(event.started_scope)
            elif isinstance(event, JobFinishScopeEvent):
                self._scopes.pop()

    @property
    def scope(self):
        return self._scopes.scope

    def get_scope(self, scope=None, generation=0):
        if scope and generation:
            path = self._scopes.path_to(scope)
            if generation >= len(path):
                return None
            index = -1 - generation
            return path[index]
        return self._scopes.get_scope()


class StubDispatcher:
    def __init__(self):
        self.handlers = []

    def add_handler(self, handler):
        self.handlers.append(handler)

    def remove_handler(self, handler):
        self.handlers.remove(handler)

    def handle(self, event):
        for handler in self.handlers:
            handler.handle(event)


class StubScope:
    def __init__(self, name, type="scope", id=None):
        self.name = name
        self.type = type
        self.id = id or create_scope_id()
        self.concurrent = False


class TestJobStatusImpl(TestCase):
    def _create_sut(self) -> tuple[StubContext, StubScope, MagicMock, JobStatusImpl]:
        stub_context = StubContext()
        stub_scope = StubScope("scope-name")
        mock_handler = MagicMock()

        stub_handler = StubDispatcher()
        stub_handler.add_handler(stub_context)
        stub_handler.add_handler(mock_handler)

        sut = JobStatusImpl(stub_handler, stub_context)  # type: ignore[arg-type]

        return stub_context, stub_scope, mock_handler, sut

    def assertHandledEvent(
        self, mock_handle: MagicMock, event_type: type[JobEvent], context, scope, index: int = 0, **data
    ) -> None:
        calls = mock_handle.call_args_list
        event = calls[index][0][0]  # First call, first positional arg

        self.assertIsInstance(
            event, event_type, f"Expected event type {event_type.__name__}, got {type(event).__name__}."
        )

        self.assertEqual(
            event.context, context, f"Mismatch in event context: expected {context!r}, got {event.context!r}."
        )
        self.assertEqual(event.scope, scope, f"Mismatch in event scope: expected {scope!r}, got {event.scope!r}.")

        for key, expected_value in data.items():
            actual_value = event.data.get(key)
            self.assertEqual(
                actual_value,
                expected_value,
                f"Mismatch in event field '{key}': expected {expected_value!r}, got {actual_value!r}.",
            )

    def test_add_remove_handler(self) -> None:
        dispatcher = JobDirectEventDispatcher()
        sut = JobStatusImpl(dispatcher, MagicMock())
        handler = MagicMock()

        sut.add_handler(handler)
        self.assertTrue(dispatcher._delegate.has_callback(handler.handle))

        sut.remove_handler(handler)
        self.assertFalse(dispatcher._delegate.has_callback(handler.handle))

    def test_add_remove_handler_negative(self) -> None:
        handler = JobBufferedEventHandler(MagicMock())
        sut = JobStatusImpl(handler, MagicMock())

        with self.assertRaises(JobException) as e:
            sut.add_handler(MagicMock())
        self.assertEqual("Wrapped handler is not an event dispatcher.", str(e.exception))

        with self.assertRaises(JobException) as e:
            sut.remove_handler(MagicMock())
        self.assertEqual("Wrapped handler is not an event dispatcher.", str(e.exception))

    def test_fork_context(self) -> None:
        stub_context, _, mock_handler, sut = self._create_sut()

        sut.fork_context(stub_context)  # type: ignore[arg-type]
        self.assertHandledEvent(
            mock_handler.handle, JobForkContextEvent, stub_context, None, forked_context=stub_context
        )

    def test_join_context(self) -> None:
        stub_context, _, mock_handler, sut = self._create_sut()

        sut.join_context(stub_context)  # type: ignore[arg-type]
        self.assertHandledEvent(
            mock_handler.handle, JobJoinContextEvent, stub_context, None, joined_context=stub_context
        )

    def test_start_scope(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        sut.start_scope(mock_scope)
        self.assertHandledEvent(mock_handler.handle, JobStartScopeEvent, stub_context, None, started_scope=mock_scope)

    def test_finish_scope(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        sut.start_scope(mock_scope)
        mock_handler.reset_mock()

        sut.finish_scope(mock_scope)
        self.assertHandledEvent(mock_handler.handle, JobFinishScopeEvent, stub_context, None, finished_scope=mock_scope)

    def test_finish_scope_no_scope(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        sut.start_scope(mock_scope)
        mock_handler.reset_mock()

        sut.finish_scope()
        self.assertHandledEvent(mock_handler.handle, JobFinishScopeEvent, stub_context, None, finished_scope=mock_scope)

    def test_skip_scope(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        sut.skip_scope(mock_scope, "skipped")
        self.assertHandledEvent(
            mock_handler.handle, JobSkipScopeEvent, stub_context, None, skipped_scope=mock_scope, reason="skipped"
        )

    def test_interrupt_scope(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        sut.start_scope(mock_scope)
        mock_handler.reset_mock()

        sut.interrupt_scope(mock_scope)
        self.assertHandledEvent(mock_handler.handle, JobInterruptScopeEvent, stub_context, mock_scope)

    def test_interrupt_scope_no_scope(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        sut.start_scope(mock_scope)
        mock_handler.reset_mock()

        sut.interrupt_scope()
        self.assertHandledEvent(mock_handler.handle, JobInterruptScopeEvent, stub_context, mock_scope)

    def test_start_scope_teardown(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        sut.start_scope(mock_scope)
        sut.start_scope_teardown(mock_scope)
        self.assertHandledEvent(
            mock_handler.handle, JobStartScopeEvent, stub_context, None, started_scope=mock_scope, index=0
        )
        self.assertHandledEvent(mock_handler.handle, JobStartScopeTeardownEvent, stub_context, mock_scope, index=1)

    def test_start_scope_teardown_no_scope(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        sut.start_scope(mock_scope)
        mock_handler.reset_mock()

        sut.start_scope_teardown()
        self.assertHandledEvent(mock_handler.handle, JobStartScopeTeardownEvent, stub_context, mock_scope)

    def test_finish_scope_teardown(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        sut.start_scope(mock_scope)
        sut.start_scope_teardown(mock_scope)
        mock_handler.reset_mock()

        sut.finish_scope_teardown(mock_scope)
        self.assertHandledEvent(mock_handler.handle, JobFinishScopeTeardownEvent, stub_context, mock_scope)

    def test_finish_scope_teardown_no_scope(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        sut.start_scope(mock_scope)
        sut.start_scope_teardown(mock_scope)
        mock_handler.reset_mock()

        sut.finish_scope_teardown()
        self.assertHandledEvent(mock_handler.handle, JobFinishScopeTeardownEvent, stub_context, mock_scope)

    def test_start_section(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        sut.start_scope(mock_scope)
        mock_handler.reset_mock()

        sut.start_section("section")
        self.assertHandledEvent(mock_handler.handle, JobStartSectionEvent, stub_context, mock_scope, section="section")

    def test_finish_section(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        sut.start_scope(mock_scope)
        mock_handler.reset_mock()

        sut.finish_section("section")
        self.assertHandledEvent(mock_handler.handle, JobFinishSectionEvent, stub_context, mock_scope, section="section")

    def test_start_item(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        sut.start_scope(mock_scope)
        mock_handler.reset_mock()

        sut.start_item("item")
        self.assertHandledEvent(mock_handler.handle, JobStartItemEvent, stub_context, mock_scope, item="item")

    def test_finish_item(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        sut.start_scope(mock_scope)
        mock_handler.reset_mock()

        sut.finish_item("ok")
        self.assertHandledEvent(mock_handler.handle, JobFinishItemEvent, stub_context, mock_scope, outcome="ok")

    def test_finish_item_with_error(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        sut.start_scope(mock_scope)
        mock_handler.reset_mock()

        sut.finish_item(outcome="fail", error="timeout")
        self.assertHandledEvent(mock_handler.handle, JobErrorEvent, stub_context, mock_scope, error="timeout", index=0)
        self.assertHandledEvent(
            mock_handler.handle, JobFinishItemEvent, stub_context, mock_scope, outcome="fail", index=1
        )

    def test_info(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        sut.start_scope(mock_scope)
        mock_handler.reset_mock()

        sut.info("step done")
        self.assertHandledEvent(mock_handler.handle, JobInfoEvent, stub_context, mock_scope, message="step done")

    def test_detail(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        sut.start_scope(mock_scope)
        mock_handler.reset_mock()

        sut.detail("debug")
        self.assertHandledEvent(mock_handler.handle, JobDetailEvent, stub_context, mock_scope, message="debug")

    def test_warning(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        sut.start_scope(mock_scope)
        mock_handler.reset_mock()

        sut.warning("warning")
        self.assertHandledEvent(mock_handler.handle, JobWarningEvent, stub_context, mock_scope, warning="warning")

    def test_error(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        sut.start_scope(mock_scope)
        mock_handler.reset_mock()

        sut.error("error")
        self.assertHandledEvent(mock_handler.handle, JobErrorEvent, stub_context, mock_scope, error="error")

    def test_output(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        sut.start_scope(mock_scope)
        mock_handler.reset_mock()

        sut.output(["line 1", "line 2"], label="stdout")
        self.assertHandledEvent(
            mock_handler.handle,
            JobOutputEvent,
            stub_context,
            mock_scope,
            output=["line 1", "line 2"],
            label="stdout",
        )

    def test_scope(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        with sut.scope(mock_scope):
            pass

        self.assertHandledEvent(
            mock_handler.handle, JobStartScopeEvent, stub_context, None, started_scope=mock_scope, index=0
        )
        self.assertHandledEvent(
            mock_handler.handle, JobFinishScopeEvent, stub_context, None, finished_scope=mock_scope, index=1
        )

    def test_scope_error(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        error = Exception("boom")

        with self.assertRaises(Exception):
            with sut.scope(mock_scope):
                raise error

        self.assertHandledEvent(
            mock_handler.handle, JobStartScopeEvent, stub_context, None, started_scope=mock_scope, index=0
        )
        self.assertHandledEvent(mock_handler.handle, JobErrorEvent, stub_context, mock_scope, error=error, index=1)
        self.assertHandledEvent(
            mock_handler.handle, JobFinishScopeEvent, stub_context, None, finished_scope=mock_scope, index=2
        )

    def test_scope_teardown(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        with sut.scope(mock_scope):
            with sut.scope_teardown(mock_scope):
                pass

        self.assertHandledEvent(
            mock_handler.handle, JobStartScopeEvent, stub_context, None, started_scope=mock_scope, index=0
        )
        self.assertHandledEvent(mock_handler.handle, JobStartScopeTeardownEvent, stub_context, mock_scope, index=1)
        self.assertHandledEvent(mock_handler.handle, JobFinishScopeTeardownEvent, stub_context, mock_scope, index=2)
        self.assertHandledEvent(
            mock_handler.handle, JobFinishScopeEvent, stub_context, None, finished_scope=mock_scope, index=3
        )

    def test_scope_teardown_error(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        error = Exception("boom")

        with sut.scope(mock_scope):
            with sut.scope_teardown(mock_scope):
                raise error

        self.assertHandledEvent(
            mock_handler.handle, JobStartScopeEvent, stub_context, None, started_scope=mock_scope, index=0
        )
        self.assertHandledEvent(mock_handler.handle, JobStartScopeTeardownEvent, stub_context, mock_scope, index=1)
        self.assertHandledEvent(mock_handler.handle, JobWarningEvent, stub_context, mock_scope, warning=error, index=2)
        self.assertHandledEvent(mock_handler.handle, JobFinishScopeTeardownEvent, stub_context, mock_scope, index=3)
        self.assertHandledEvent(
            mock_handler.handle, JobFinishScopeEvent, stub_context, None, finished_scope=mock_scope, index=4
        )

    def test_section(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        with sut.scope(mock_scope):
            with sut.section("section"):
                pass

        self.assertHandledEvent(
            mock_handler.handle, JobStartScopeEvent, stub_context, None, started_scope=mock_scope, index=0
        )
        self.assertHandledEvent(
            mock_handler.handle, JobStartSectionEvent, stub_context, mock_scope, section="section", index=1
        )
        self.assertHandledEvent(
            mock_handler.handle, JobFinishSectionEvent, stub_context, mock_scope, section="section", index=2
        )
        self.assertHandledEvent(
            mock_handler.handle, JobFinishScopeEvent, stub_context, None, finished_scope=mock_scope, index=3
        )

    def test_section_error(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        error = Exception("boom")

        with self.assertRaises(Exception):
            with sut.scope(mock_scope):
                with sut.section("section"):
                    raise error

        self.assertHandledEvent(
            mock_handler.handle, JobStartScopeEvent, stub_context, None, started_scope=mock_scope, index=0
        )
        self.assertHandledEvent(
            mock_handler.handle, JobStartSectionEvent, stub_context, mock_scope, section="section", index=1
        )
        self.assertHandledEvent(mock_handler.handle, JobErrorEvent, stub_context, mock_scope, error=error, index=2)
        self.assertHandledEvent(
            mock_handler.handle, JobFinishSectionEvent, stub_context, mock_scope, section="section", index=3
        )
        self.assertHandledEvent(mock_handler.handle, JobErrorEvent, stub_context, mock_scope, error=error, index=4)
        self.assertHandledEvent(
            mock_handler.handle, JobFinishScopeEvent, stub_context, None, finished_scope=mock_scope, index=5
        )

    def test_item(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        with sut.scope(mock_scope):
            with sut.item("item"):
                pass

        self.assertHandledEvent(
            mock_handler.handle, JobStartScopeEvent, stub_context, None, started_scope=mock_scope, index=0
        )
        self.assertHandledEvent(mock_handler.handle, JobStartItemEvent, stub_context, mock_scope, item="item", index=1)
        self.assertHandledEvent(
            mock_handler.handle, JobFinishItemEvent, stub_context, mock_scope, outcome="done.", index=2
        )
        self.assertHandledEvent(
            mock_handler.handle, JobFinishScopeEvent, stub_context, None, finished_scope=mock_scope, index=3
        )

    def test_item_error(self) -> None:
        stub_context, mock_scope, mock_handler, sut = self._create_sut()

        error = Exception("boom")

        with self.assertRaises(Exception):
            with sut.scope(mock_scope):
                with sut.item("item"):
                    raise error

            self.assertHandledEvent(
                mock_handler.handle, JobStartScopeEvent, stub_context, None, started_scope=mock_scope, index=0
            )
            self.assertHandledEvent(
                mock_handler.handle, JobStartItemEvent, stub_context, mock_scope, item="item", index=1
            )
            self.assertHandledEvent(mock_handler.handle, JobErrorEvent, stub_context, mock_scope, error=error, index=2)
            self.assertHandledEvent(
                mock_handler.handle, JobFinishItemEvent, stub_context, mock_scope, outcome="done.", index=3
            )
            self.assertHandledEvent(mock_handler.handle, JobErrorEvent, stub_context, mock_scope, error=error, index=4)
            self.assertHandledEvent(
                mock_handler.handle, JobFinishScopeEvent, stub_context, None, finished_scope=mock_scope, index=5
            )


class TestJobDirectEventDispatcher(TestCase):
    def test(self) -> None:
        sut = JobDirectEventDispatcher()

        mock_handler_1 = MagicMock()
        mock_handler_1.handle = MagicMock()

        mock_handler_2 = MagicMock()
        mock_handler_2.handle = MagicMock()

        sut.add_handler(mock_handler_1)
        sut.add_handler(mock_handler_2)

        mock_event = MagicMock()
        sut.handle(mock_event)

        mock_handler_1.handle.assert_called_once_with(mock_event)
        mock_handler_2.handle.assert_called_once_with(mock_event)

        mock_handler_1.reset_mock()
        mock_handler_2.reset_mock()

        sut.remove_handler(mock_handler_1)

        mock_event_2 = MagicMock()
        sut.handle(mock_event_2)

        mock_handler_1.handle.assert_not_called()
        mock_handler_2.handle.assert_called_once_with(mock_event_2)

    def test_one_error(self) -> None:
        sut = JobDirectEventDispatcher()

        mock_handler_1 = MagicMock()
        mock_handler_1.handle = MagicMock(side_effect=Exception("boom"))

        mock_handler_2 = MagicMock()
        mock_handler_2.handle = MagicMock()

        sut.add_handler(mock_handler_1)
        sut.add_handler(mock_handler_2)

        mock_event = MagicMock()

        with self.assertRaises(Exception) as e:
            sut.handle(mock_event)
        self.assertEqual("boom", str(e.exception))

        # Both still called
        mock_handler_1.handle.assert_called_once_with(mock_event)
        mock_handler_2.handle.assert_called_once_with(mock_event)

    def test_errors(self) -> None:
        sut = JobDirectEventDispatcher()

        mock_handler_1 = MagicMock()
        mock_handler_1.handle = MagicMock(side_effect=Exception("boom"))

        mock_handler_2 = MagicMock()
        mock_handler_2.handle = MagicMock(side_effect=Exception("boom!"))

        sut.add_handler(mock_handler_1)
        sut.add_handler(mock_handler_2)

        mock_event = MagicMock()

        with self.assertRaises(Exception) as e:
            sut.handle(mock_event)
        self.assertEqual("Handle event failed: [Exception('boom'), Exception('boom!')]", str(e.exception))

        # Both still called
        mock_handler_1.handle.assert_called_once_with(mock_event)
        mock_handler_2.handle.assert_called_once_with(mock_event)


class TestJobBufferedEventHandler(TestCase):
    def test(self) -> None:
        mock_handler = MagicMock(handle=MagicMock())
        mock_event1 = MagicMock(field="abc")
        mock_event2 = MagicMock(field="xyz")

        sut = JobBufferedEventHandler(mock_handler)
        sut.handle(mock_event1)
        sut.handle(mock_event2)
        mock_handler.handle.assert_not_called()

        sut.flush()
        mock_handler.handle.assert_has_calls([call(mock_event1), call(mock_event2)])

        sut.flush()
        mock_handler.handle.assert_has_calls([call(mock_event1), call(mock_event2)])

    def test_with_size(self) -> None:
        mock_handler = MagicMock(handle=MagicMock())
        mock_event1 = MagicMock(field="abc")
        mock_event2 = MagicMock(field="xyz")

        sut = JobBufferedEventHandler(mock_handler, size=1)
        sut.handle(mock_event1)
        sut.handle(mock_event2)
        mock_handler.handle.assert_has_calls([call(mock_event1)])

        sut.flush()
        mock_handler.handle.assert_has_calls([call(mock_event1), call(mock_event2)])


class StubHandler:
    def __init__(self):
        self.events = []

    def handle(self, event):
        self.events.append(event)


class TestJobLocalEventDispatcher(TestCase):
    def test(self) -> None:
        flush_to = StubDispatcher()
        handler1 = StubHandler()
        flush_to.add_handler(handler1)

        sut = JobLocalEventDispatcher(flush_to)
        handler2 = StubHandler()
        sut.add_handler(handler2)

        mock_event = MagicMock()
        sut.handle(mock_event)

        self.assertEqual([], handler1.events)
        self.assertEqual([mock_event], handler2.events)

        sut.flush()
        self.assertEqual([mock_event], handler1.events)

        sut.remove_handler(handler2)
        sut.handle(MagicMock())
        self.assertEqual([mock_event], handler2.events)


class TestJobRoutingEventDispatcher(TestCase):
    def test(self) -> None:
        mock_handler1 = MagicMock(handle=MagicMock())
        mock_handler2 = MagicMock(handle=MagicMock())
        mock_event1 = MagicMock(data={"field": "abc"})
        mock_event2 = MagicMock(data={"field": "xyz"})
        mock_event3 = MagicMock(data={"field": "123"})

        def predicate1(event: JobEvent) -> bool:
            return event.data["field"] == "abc"

        def predicate2(event: JobEvent) -> bool:
            return event.data["field"] == "xyz"

        def predicate3(event: JobEvent) -> bool:
            return event.data["field"] == "123"

        sut = JobRoutingEventDispatcher()
        # Do some various operations to reach a final state
        sut.add_handler(mock_handler1, predicate=predicate1)
        sut.add_handler(mock_handler2, predicate=predicate1)
        sut.add_handler(mock_handler2, predicate=predicate3)
        sut.add_handler(mock_handler2, predicate=predicate2)
        sut.remove_handler(mock_handler2, predicate=predicate1)
        sut.add_handler(mock_handler1, predicate=predicate3)

        sut.handle(mock_event1)
        sut.handle(mock_event2)
        sut.handle(mock_event3)

        mock_handler1.handle.assert_has_calls([call(mock_event1), call(mock_event3)])
        mock_handler2.handle.assert_has_calls([call(mock_event2), call(mock_event3)])

    def test_no_predicate(self) -> None:
        mock_handler1 = MagicMock(handle=MagicMock())
        mock_handler2 = MagicMock(handle=MagicMock())
        mock_event1 = MagicMock(data={"field": "abc"})
        mock_event2 = MagicMock(data={"field": "xyz"})
        mock_event3 = MagicMock(data={"field": "123"})

        sut = JobRoutingEventDispatcher()

        sut.add_handler(mock_handler1)
        sut.add_handler(mock_handler2)

        sut.handle(mock_event1)
        sut.handle(mock_event2)
        sut.handle(mock_event3)

        mock_handler1.handle.assert_has_calls([call(mock_event1), call(mock_event2), call(mock_event3)])
        mock_handler2.handle.assert_has_calls([call(mock_event1), call(mock_event2), call(mock_event3)])

        mock_handler1.reset_mock()
        mock_handler2.reset_mock()

        sut.remove_handler(mock_handler2)

        sut.handle(mock_event1)
        sut.handle(mock_event2)
        sut.handle(mock_event3)

        mock_handler1.handle.assert_has_calls([call(mock_event1), call(mock_event2), call(mock_event3)])
        mock_handler2.handle.assert_not_called()
