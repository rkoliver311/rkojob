import shlex
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import MagicMock, patch

from rkojob import JobContext, JobException, ValueRef
from rkojob.actions import ShellAction, VerifyTestStructure
from rkojob.factories import JobContextFactory
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


class TestVerifyTestStructure(TestCase):
    def test(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            src_path = temp_path / "src"
            foo_path = src_path / "foo"
            foo_path.mkdir(parents=True)
            (foo_path / "baz.py").touch()
            (foo_path / ".gitignore").touch()
            foo_bar_path = src_path / "foo" / "bar"
            foo_bar_path.mkdir(parents=True)
            (foo_bar_path / "__init__.py").touch()

            tests_path = temp_path / "tests"
            test_foo_bar_path = tests_path / "test_foo" / "test_bar"
            test_foo_bar_path.mkdir(parents=True)
            (test_foo_bar_path / "test_bar.py").touch()

            sut = VerifyTestStructure(src_path=src_path, tests_path=tests_path)
            with self.assertRaises(JobException) as e:
                sut.action(JobContextFactory.create())
            self.assertEqual(
                "Missing tests: [\"Test path for source path 'foo/baz.py' not found: test_foo/test_baz.py\"]",
                str(e.exception),
            )
            self.assertEqual(
                ["Test path for source path 'foo/baz.py' not found: test_foo/test_baz.py"], sut.errors.value
            )

    def test_src_not_dir(self) -> None:
        sut = VerifyTestStructure(src_path=Path() / "foo.bar", tests_path=Path())
        with self.assertRaises(JobException) as e:
            sut.action(JobContextFactory.create())
        self.assertEqual("src_path must be a directory: foo.bar", str(e.exception))

    def test_tests_not_dir(self) -> None:
        sut = VerifyTestStructure(src_path=Path(), tests_path=Path() / "foo.bar")
        with self.assertRaises(JobException) as e:
            sut.action(JobContextFactory.create())
        self.assertEqual("tests_path must be a directory: foo.bar", str(e.exception))

    def test_skip(self) -> None:
        sut = VerifyTestStructure(src_path=MagicMock(), tests_path=MagicMock())
        self.assertTrue(sut._skip(Path(".DS_Store")))
        self.assertTrue(sut._skip(Path(".gitignore")))
        self.assertTrue(sut._skip(Path("__pycache__")))
        self.assertTrue(sut._skip(Path() / "Foo.egg-info"))
        self.assertFalse(sut._skip(Path() / "foo.py"))

    def test_expected_test_path(self) -> None:
        src_path = Path("src")
        tests_path = Path("tests")
        sut = VerifyTestStructure(src_path=src_path, tests_path=tests_path)

        self.assertEqual(tests_path / "test_foo.py", sut._expected_test_path(src_path, tests_path, src_path / "foo.py"))
        self.assertEqual(
            tests_path / "test_foo" / "test_foo.py",
            sut._expected_test_path(src_path, tests_path, src_path / "foo" / "__init__.py"),
        )
        self.assertEqual(
            tests_path / "test_foo" / "test_bar.py",
            sut._expected_test_path(src_path, tests_path, src_path / "foo" / "bar.py"),
        )

    def test_test_name(self) -> None:
        sut = VerifyTestStructure(src_path=MagicMock(), tests_path=MagicMock())
        self.assertEqual("test_foo.py", sut._test_name(Path("foo.py")))
        self.assertEqual("test_foo.py", sut._test_name(Path("foo") / "__init__.py"))
