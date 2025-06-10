from unittest import TestCase
from unittest.mock import MagicMock, patch

from rkojob import JobIdType, create_scope_id
from rkojob.concurrent import JobFutureImpl, JobFuturesImpl, JobInterruptImpl
from rkojob.job import JobScopeIDMixin


class TestJobFutureImpl(TestCase):
    def test_context(self) -> None:
        mock_context = MagicMock()
        mock_future = MagicMock()
        sut: JobFutureImpl[None] = JobFutureImpl(mock_context, mock_future)
        self.assertIs(mock_context, sut.context)

    def test_done(self) -> None:
        mock_context = MagicMock()
        mock_future = MagicMock(done=MagicMock(return_value=True))
        sut: JobFutureImpl[None] = JobFutureImpl(mock_context, mock_future)
        self.assertTrue(sut.done)
        mock_future.done.assert_called_once_with()

    def test_running(self) -> None:
        mock_context = MagicMock()
        mock_future = MagicMock(running=MagicMock(return_value=False))
        sut: JobFutureImpl[None] = JobFutureImpl(mock_context, mock_future)
        self.assertFalse(sut.running)
        mock_future.running.assert_called_once_with()

    def test_result(self) -> None:
        mock_context = MagicMock()
        mock_future = MagicMock(result=MagicMock(return_value="result"))
        sut: JobFutureImpl[str] = JobFutureImpl(mock_context, mock_future)
        self.assertEqual("result", sut.result(timeout=1.23))
        mock_future.result.assert_called_once_with(timeout=1.23)

    def test_future(self) -> None:
        mock_context = MagicMock()
        mock_future = MagicMock()
        sut: JobFutureImpl[None] = JobFutureImpl(mock_context, mock_future)
        self.assertIs(mock_future, sut.future)


class TestJobFuturesImpl(TestCase):
    @patch("rkojob.concurrent.ThreadPoolExecutor")
    def test_with_prefix(self, mock_executor_type) -> None:
        _ = JobFuturesImpl(prefix="prefix")
        mock_executor_type.assert_called_once_with(thread_name_prefix="prefix")

    @patch("rkojob.concurrent.ThreadPoolExecutor")
    def test_submit(self, _mock_executor_type) -> None:
        mock_context = MagicMock()
        mock_task = MagicMock
        arg1 = MagicMock()
        arg2 = MagicMock()
        arg3 = MagicMock()

        sut: JobFuturesImpl = JobFuturesImpl()
        sut.submit(mock_context, mock_task, arg1, arg2, arg3=arg3)
        sut._executor.submit.assert_called_once_with(mock_task, arg1, arg2, arg3=arg3)  # type: ignore[attr-defined]

    @patch("rkojob.concurrent.ThreadPoolExecutor")
    def test_futures(self, mock_executor_type) -> None:
        mock_future_1 = MagicMock()
        mock_future_2 = MagicMock()
        mock_executor_type().submit = MagicMock(side_effect=[mock_future_1, mock_future_2])
        mock_context = MagicMock()
        mock_task = MagicMock
        arg1 = MagicMock()
        arg2 = MagicMock()
        arg3 = MagicMock()

        sut: JobFuturesImpl = JobFuturesImpl()
        sut.submit(mock_context, mock_task, arg1, arg3=arg3)
        sut.submit(mock_context, mock_task, arg2, arg3=arg3)
        self.assertEqual(2, len(sut.futures))
        self.assertEqual([mock_future_1, mock_future_2], [future.future for future in sut.futures])

    @patch("rkojob.concurrent.ThreadPoolExecutor")
    def test_shutdown(self, _mock_executor_type) -> None:
        sut: JobFuturesImpl = JobFuturesImpl()
        sut.shutdown()
        sut._executor.shutdown.assert_called_once_with()  # type: ignore[attr-defined]


class StubScopeID(JobScopeIDMixin):
    def __init__(self, id: JobIdType | None = None) -> None:
        self._id = id or create_scope_id()


class TestJobInterrupt(TestCase):
    @patch("rkojob.concurrent.Event")
    def test(self, mock_event_type) -> None:
        mock_event = mock_event_type()
        sut = JobInterruptImpl()
        sut.is_set()
        mock_event.is_set.assert_called_once_with()

        sut.set()
        mock_event.set.assert_called_once_with()

        sut.clear()
        mock_event.clear.assert_called_once_with()

        sut.wait(timeout=1.2)
        mock_event.wait.assert_called_once_with(timeout=1.2)
