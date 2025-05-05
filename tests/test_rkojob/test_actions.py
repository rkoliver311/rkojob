import shlex
from unittest import TestCase
from unittest.mock import MagicMock, patch

from rkojob import JobContext, ValueRef
from rkojob.actions import ShellAction
from rkojob.util import ShellException, ShellResult


class TestShellAction(TestCase):
    def make_context(self) -> JobContext:
        context = MagicMock(spec=JobContext)
        context.status.start_item = MagicMock()
        context.status.finish_item = MagicMock()
        context.status.output = MagicMock()
        return context

    @patch("rkojob.actions.Shell")
    def test_success(self, mock_shell_cls):
        shell_result = ShellResult(stdout="ok", stderr="", return_code=0)
        mock_shell_cls.return_value = lambda *args: shell_result

        context = self.make_context()

        sut = ShellAction("echo", "ok")
        sut.action(context)

        expected_command = shlex.join(("echo", "ok"))
        context.status.start_item.assert_called_once_with(f"Executing {expected_command}")
        context.status.finish_item.assert_called_once_with()
        context.status.output.assert_called_once_with("ok", label="stdout")
        self.assertEqual(shell_result, sut.result.get())

    @patch("rkojob.actions.Shell")
    def test_shell_exception(self, mock_shell_cls):
        result = ShellResult(stdout="", stderr="boom", return_code=99)
        exception = ShellException(result=result)
        mock_shell_cls.return_value = MagicMock(side_effect=exception)

        context = self.make_context()
        result_ref = ValueRef()

        sut = ShellAction("explode", result=result_ref)
        sut.action(context)

        context.status.finish_item.assert_called_once_with(error=exception)
        context.status.output.assert_called_once_with("boom", label="stderr")
        self.assertEqual(result, result_ref.value)

    @patch("rkojob.actions.Shell")
    def test_shell_raise_on_error(self, mock_shell_cls):
        result = ShellResult(stdout="", stderr="boom", return_code=99)
        exception = ShellException(result=result)
        mock_shell_cls.return_value = MagicMock(side_effect=exception)

        context = self.make_context()
        result_ref = ValueRef()

        sut = ShellAction("explode", result=result_ref, raise_on_error=True)
        with self.assertRaises(ShellException) as e:
            sut.action(context)
        self.assertEqual("boom", str(e.exception))

        context.status.finish_item.assert_called_once_with("return_code=99")
        context.status.output.assert_called_once_with("boom", label="stderr")
        self.assertEqual(result, result_ref.value)

    @patch("rkojob.actions.Shell")
    def test_result_is_none(self, mock_shell_cls):
        mock_shell_cls.return_value = lambda *args: None

        context = self.make_context()
        result_ref = ValueRef()

        action = ShellAction("nothing", result=result_ref)
        action.action(context)

        context.status.output.assert_not_called()
        self.assertFalse(result_ref.has_value)
