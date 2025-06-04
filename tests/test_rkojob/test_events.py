# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from unittest import TestCase
from unittest.mock import MagicMock

from rkojob import JobEvent, JobScopeStack, create_context_id, create_scope_id
from rkojob.events import (
    JobDetailEvent,
    JobDirectEventDispatcher,
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
    JobStatusImpl,
    JobWarningEvent,
)


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
