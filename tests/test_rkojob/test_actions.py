# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

import shlex
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import MagicMock, patch

from rkojob import JobContext, JobException, NoValue, ValueRef, Values, create_scope_id
from rkojob.actions import ShellAction, ShellActionBuilder, VerifyPythonTestStructure
from rkojob.factories import JobContextFactory
from rkojob.util import ShellException, ShellResult


class TestShellAction(TestCase):
    def make_context(self) -> JobContext:
        context = MagicMock(spec=JobContext)
        context.events.section = MagicMock()
        context.events.output = MagicMock()
        context.values = Values()
        context.get_value = lambda key, coercer=None, default=NoValue: context.values.get_or_else(key, default)

        return context

    @patch("rkojob.actions.Shell")
    def test_success(self, mock_shell_cls):
        shell_result = ShellResult(stdout="ok", stderr="", return_code=0)
        mock_shell_cls.return_value = lambda *args: shell_result

        context = self.make_context()

        sut = ShellAction("echo", "ok")
        sut.action(context)

        expected_command = shlex.join(("echo", "ok"))
        context.events.section.assert_called_once_with(f"Executing {expected_command}")
        context.events.output.assert_called_once_with("ok", label="stdout")
        self.assertEqual(shell_result, sut.result.get())

    @patch("rkojob.actions.Shell")
    def test_with_env(self, mock_shell_cls):
        context = self.make_context()

        sut = ShellAction("echo", "ok")
        sut.with_env(VAR="value")
        sut.action(context)
        expected_command = shlex.join(("echo", "ok")) + " (env={'VAR': 'value'})"
        context.events.section.assert_called_once_with(f"Executing {expected_command}")
        mock_shell_cls.assert_called_once_with(env={"VAR": "value"})
        mock_shell_cls().assert_called_once_with("echo", "ok")

    @patch("rkojob.actions.Shell")
    def test_job_workspace(self, mock_shell_cls):
        context = self.make_context()
        context.values.set("workspace", "/some/path")

        sut = ShellAction("echo", "ok")
        sut.action(context)
        mock_shell_cls.assert_called_once_with(cwd="/some/path")
        mock_shell_cls().assert_called_once_with("echo", "ok")

    @patch("rkojob.actions.Shell")
    def test_in_dir(self, mock_shell_cls):
        context = self.make_context()

        sut = ShellAction("echo", "ok")
        sut.in_dir("/some/path")
        sut.action(context)
        mock_shell_cls.assert_called_once_with(cwd="/some/path")
        mock_shell_cls().assert_called_once_with("echo", "ok")

    @patch("rkojob.actions.Shell")
    def test_in_dir_as_resolvable(self, mock_shell_cls):
        context = self.make_context()

        sut = ShellAction("echo", "ok")
        sut.in_dir(ValueRef("/some/path"))
        sut.action(context)
        mock_shell_cls.assert_called_once_with(cwd="/some/path")
        mock_shell_cls().assert_called_once_with("echo", "ok")

    @patch("rkojob.actions.Shell")
    def test_shell_exception(self, mock_shell_cls):
        result = ShellResult(stdout="", stderr="boom", return_code=99)
        exception = ShellException(result=result)
        mock_shell_cls.return_value = MagicMock(side_effect=exception)

        context = self.make_context()
        result_ref = ValueRef()

        sut = ShellAction("explode", result=result_ref)
        sut.action(context)

        context.events.error.assert_called_once_with(exception)
        context.events.output.assert_called_once_with("boom", label="stderr")
        self.assertEqual(result, result_ref.value)

    @patch("rkojob.actions.Shell")
    def test_shell_raise_on_error(self, mock_shell_cls):
        result = ShellResult(stdout="", stderr="boom", return_code=99)
        exception = ShellException(result=result)
        mock_shell_cls.return_value = MagicMock(side_effect=exception)

        context = self.make_context()
        result_ref = ValueRef()

        sut = ShellAction("explode", result=result_ref, on_error=ShellAction.RAISE)
        with self.assertRaises(ShellException) as e:
            sut.action(context)
        self.assertEqual("boom", str(e.exception))

        context.events.error.assert_not_called()
        context.events.output.assert_called_once_with("boom", label="stderr")
        self.assertEqual(result, result_ref.value)

    @patch("rkojob.actions.Shell")
    def test_shell_warn_on_error(self, mock_shell_cls):
        result = ShellResult(stdout="", stderr="boom", return_code=99)
        exception = ShellException(result=result)
        mock_shell_cls.return_value = MagicMock(side_effect=exception)

        context = self.make_context()
        result_ref = ValueRef()

        sut = ShellAction("explode", result=result_ref, on_error=ShellAction.WARN)
        sut.action(context)

        context.events.error.assert_not_called()
        context.events.warning.assert_called_once_with(exception)
        self.assertEqual(result, result_ref.value)

    @patch("rkojob.actions.Shell")
    def test_shell_ignore_on_error(self, mock_shell_cls):
        result = ShellResult(stdout="", stderr="boom", return_code=99)
        exception = ShellException(result=result)
        mock_shell_cls.return_value = MagicMock(side_effect=exception)

        context = self.make_context()
        result_ref = ValueRef()

        sut = ShellAction("explode", result=result_ref, on_error=ShellAction.IGNORE)
        sut.action(context)

        context.events.error.assert_not_called()
        context.events.warning.assert_not_called()
        context.events.output.assert_called_once_with("boom", label="stderr")
        self.assertEqual(result, result_ref.value)

    @patch("rkojob.actions.Shell")
    def test_result_is_none(self, mock_shell_cls):
        mock_shell_cls.return_value = lambda *args: None

        context = self.make_context()
        result_ref = ValueRef()

        action = ShellAction("nothing", result=result_ref)
        action.action(context)

        context.events.output.assert_not_called()
        self.assertFalse(result_ref.has_value)

    @patch("rkojob.actions.Shell")
    def test_arg_as_list(self, mock_shell_cls):
        context = self.make_context()

        args2_3_4 = ["arg2", "arg3", "arg4"]
        sut = ShellAction("arg1", args2_3_4, "arg5")
        sut.action(context)

        mock_shell_cls().assert_called_once_with("arg1", "arg2", "arg3", "arg4", "arg5")


class TestShellActionBuilder(TestCase):
    @patch("rkojob.actions.Shell")
    def test(self, mock_shell_type) -> None:
        sut = ShellActionBuilder("tool").command.sub_command("-v", enable_feature=True, keyword_arg="value")
        self.assertIsInstance(sut, ShellAction)
        sut.action(MagicMock(get_value=lambda key, coercer=None, default=None: None))
        mock_shell_type.assert_called_once_with(show_stdout=False, show_stderr=False)
        mock_shell_type().assert_called_once_with(
            "tool", "command", "sub-command", "-v", "--enable-feature", "--keyword-arg", "value"
        )

    @patch("rkojob.actions.Shell")
    def test_with_shell_kwargs(self, mock_shell_type) -> None:
        sut = ShellActionBuilder("tool", show_stdout=True, env={"var": "value"}).command.sub_command(
            "-v", enable_feature=True, keyword_arg="value"
        )
        self.assertIsInstance(sut, ShellAction)
        sut.action(MagicMock(get_value=lambda key, coercer=None, default=None: None))
        mock_shell_type.assert_called_once_with(show_stdout=True, env={"var": "value"}, show_stderr=False)
        mock_shell_type().assert_called_once_with(
            "tool", "command", "sub-command", "-v", "--enable-feature", "--keyword-arg", "value"
        )

    @patch("rkojob.actions.Shell")
    def test_with_shell_kwargs_with_resolvable(self, mock_shell_type) -> None:
        sut = ShellActionBuilder("tool", show_stdout=True, env={"var": "value"}).command.sub_command(
            "-v", enable_feature=True, keyword_arg=ValueRef(True), keyword_arg2=ValueRef(False)
        )
        self.assertIsInstance(sut, ShellAction)
        sut.action(MagicMock(get_value=lambda key, coercer=None, default=None: None))
        mock_shell_type.assert_called_once_with(show_stdout=True, env={"var": "value"}, show_stderr=False)
        mock_shell_type().assert_called_once_with(
            "tool", "command", "sub-command", "-v", "--enable-feature", "--keyword-arg"
        )


class StubScope:
    def __init__(self, name, type, id=None):
        self.name = name
        self.type = type
        self.id = id or create_scope_id()
        self.concurrent = False
        self.values = Values()


class TestVerifyPythonTestStructure(TestCase):
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

            sut = VerifyPythonTestStructure(source_root=src_path, test_root=tests_path)
            context = JobContextFactory.create()
            stub_scope = StubScope("scope", "type")
            with context.events.scope(stub_scope):
                sut.action(context)
            self.assertEqual(
                ["Test path for source path 'foo/baz.py' not found: test_foo/test_baz.py"], sut.errors.value
            )

    def test_src_not_dir(self) -> None:
        sut = VerifyPythonTestStructure(source_root=Path() / "foo.bar", test_root=Path())
        with self.assertRaises(JobException) as e:
            sut.action(JobContextFactory.create())
        self.assertEqual("source_root must be a directory: foo.bar", str(e.exception))

    def test_tests_not_dir(self) -> None:
        sut = VerifyPythonTestStructure(source_root=Path(), test_root=Path() / "foo.bar")
        with self.assertRaises(JobException) as e:
            sut.action(JobContextFactory.create())
        self.assertEqual("test_root must be a directory: foo.bar", str(e.exception))

    def test_skip(self) -> None:
        sut = VerifyPythonTestStructure(source_root=MagicMock(), test_root=MagicMock())
        cwd = Path()
        self.assertTrue(sut._skip(cwd, Path(".DS_Store")))
        self.assertTrue(sut._skip(cwd, Path(".gitignore")))
        self.assertTrue(sut._skip(cwd, Path("__pycache__")))
        self.assertTrue(sut._skip(cwd, cwd / "Foo.egg-info"))
        self.assertTrue(sut._skip(cwd, cwd / "Foo.egg-info" / "foo.py"))
        self.assertFalse(sut._skip(cwd, cwd / "foo.py"))

    def test_expected_test_path(self) -> None:
        src_path = Path("src")
        tests_path = Path("tests")
        sut = VerifyPythonTestStructure(source_root=src_path, test_root=tests_path)

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
        sut = VerifyPythonTestStructure(source_root=MagicMock(), test_root=MagicMock())
        self.assertEqual("test_foo.py", sut._test_name(Path("foo.py")))
        self.assertEqual("test_foo.py", sut._test_name(Path("foo") / "__init__.py"))
