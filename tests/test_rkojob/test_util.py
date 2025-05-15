# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest import TestCase
from unittest.mock import MagicMock

from rkojob.util import (
    Shell,
    ShellException,
    ShellResult,
    ToolBuilder,
    ToolRunner,
    deep_flatten,
    to_camel,
    to_kebab,
)


class TestShellException(TestCase):
    def test(self) -> None:
        result = ShellResult(return_code=1, stdout="Working...", stderr="error")
        sut = ShellException(result=result)
        self.assertIs(result, sut.result)
        self.assertEqual("error", str(sut))


class TestShell(TestCase):
    def mock_popen(self, return_code: int = 0, stdout: list[str] | None = None, stderr: list[str] | None = None):
        if stdout is None:
            stdout = []
        if stderr is None:
            stderr = []
        mock_proc: MagicMock = MagicMock()
        mock_proc.returncode = return_code
        mock_proc.stdout = stdout
        mock_proc.stderr = stderr
        return MagicMock(return_value=mock_proc)

    def test(self) -> None:
        sut = Shell()
        sut._popen = self.mock_popen(stdout=["Hello, world!\n"], stderr=["Secret hello!\n"])

        result: ShellResult = sut("greet", "Hello, world!")

        sut._popen.assert_called_with(
            ("greet", "Hello, world!"), stdout=-1, stderr=-1, text=True, cwd=None, env=None, shell=False
        ),

        self.assertEqual("Hello, world!\n", result.stdout)
        self.assertEqual("Secret hello!\n", result.stderr)
        self.assertEqual(0, result.return_code)

    def test_raise(self) -> None:
        sut = Shell()
        sut._popen = self.mock_popen(return_code=1, stdout=[], stderr=["error\n"])

        with self.assertRaises(ShellException) as e:
            sut("greet", "Hello, world!")
        result = e.exception.result

        sut._popen.assert_called_with(
            ("greet", "Hello, world!"), stdout=-1, stderr=-1, text=True, cwd=None, env=None, shell=False
        ),

        self.assertEqual("", result.stdout)
        self.assertEqual("error\n", result.stderr)
        self.assertEqual(1, result.return_code)

    def test_do_not_raise(self) -> None:
        sut = Shell(raise_on_error=False)
        sut._popen = self.mock_popen(return_code=1, stdout=[], stderr=["error\n"])

        result = sut("greet", "Hello, world!")

        sut._popen.assert_called_with(
            ("greet", "Hello, world!"), stdout=-1, stderr=-1, text=True, cwd=None, env=None, shell=False
        ),

        self.assertEqual("", result.stdout)
        self.assertEqual("error\n", result.stderr)
        self.assertEqual(1, result.return_code)

    def test_show_redirect_stderr(self) -> None:
        sut = Shell()
        sut._popen = self.mock_popen()
        sut("greet", "Hello, world!", stderr_to_stdout=True)
        sut._popen.assert_called_with(
            ("greet", "Hello, world!"), stdout=-1, stderr=-2, text=True, cwd=None, env=None, shell=False
        ),

    def test_tee_stderr(self) -> None:
        sut = Shell()
        sut._popen = self.mock_popen(stdout=["Hello, world!\n"], stderr=["Secret hello!\n"])
        sut("greet", "Hello, world!", tee_stderr="/dev/null")
        sut._popen.assert_called_with(
            ("greet", "Hello, world!"), stdout=-1, stderr=-1, text=True, cwd=None, env=None, shell=False
        )

    def test_tee_stdout(self) -> None:
        with NamedTemporaryFile(mode="wt+") as temp_file:
            sut = Shell()
            sut._popen = self.mock_popen(stdout=["Hello, world!\n"], stderr=["Secret hello!\n"])
            sut("greet", "Hello, world!", tee_stdout=temp_file.file)
            sut._popen.assert_called_with(
                ("greet", "Hello, world!"), stdout=-1, stderr=-1, text=True, cwd=None, env=None, shell=False
            )
            self.assertEqual("Hello, world!\n", Path(temp_file.name).read_text())

    def test_tee_stdout_and_stderr_same(self) -> None:
        with NamedTemporaryFile(mode="wt+") as temp_file:
            sut = Shell()
            sut._popen = self.mock_popen(stdout=["Hello, world!\n"], stderr=["Secret hello!\n"])
            sut("greet", "Hello, world!", tee_stdout=temp_file.name, tee_stderr=temp_file.name)
            sut._popen.assert_called_with(
                ("greet", "Hello, world!"), stdout=-1, stderr=-1, text=True, cwd=None, env=None, shell=False
            )
            self.assertEqual("Hello, world!\nSecret hello!\n", Path(temp_file.name).read_text())

    def test_real(self) -> None:
        sut = Shell()
        result: ShellResult = sut("echo", "Hello, world!")
        self.assertEqual("Hello, world!\n", result.stdout)


class TestToCamel(TestCase):
    def test_kebab_to_camel(self):
        self.assertEqual(to_camel("tool-runner"), "toolRunner")
        self.assertEqual(to_camel("parse-http-response"), "parseHttpResponse")
        self.assertEqual(to_camel("get-url-from-html"), "getUrlFromHtml")

    def test_snake_to_camel(self):
        self.assertEqual(to_camel("tool_runner"), "toolRunner")
        self.assertEqual(to_camel("parse_http_response"), "parseHttpResponse")
        self.assertEqual(to_camel("get_url_from_html"), "getUrlFromHtml")

    def test_single_word(self):
        self.assertEqual(to_camel("tool"), "tool")
        self.assertEqual(to_camel("tool_"), "tool")
        self.assertEqual(to_camel("tool-"), "tool")

    def test_mixed_case(self):
        self.assertEqual(to_camel("tool-Runner"), "toolRunner")
        self.assertEqual(to_camel("tool_Runner"), "toolRunner")


class TestToKebab(TestCase):
    def test_camel_to_kebab(self):
        self.assertEqual(to_kebab("ToolRunner"), "tool-runner")
        self.assertEqual(to_kebab("parseHTTPResponse"), "parse-http-response")
        self.assertEqual(to_kebab("getURLFromHTML"), "get-url-from-html")

    def test_snake_to_kebab(self):
        self.assertEqual(to_kebab("tool_runner"), "tool-runner")
        self.assertEqual(to_kebab("parse_http_response"), "parse-http-response")
        self.assertEqual(to_kebab("get_url_from_html"), "get-url-from-html")

    def test_kebab_to_kebab(self):
        self.assertEqual(to_kebab("tool-runner"), "tool-runner")
        self.assertEqual(to_kebab("parse-http-response"), "parse-http-response")

    def test_mixed_and_redundant(self):
        self.assertEqual(to_kebab("tool__Runner"), "tool-runner")
        self.assertEqual(to_kebab("tool--Runner"), "tool-runner")
        self.assertEqual(to_kebab("Tool__Runner--X"), "tool-runner-x")

    def test_single_word(self):
        self.assertEqual(to_kebab("Tool"), "tool")
        self.assertEqual(to_kebab("tool"), "tool")


class TestToolBuilder(TestCase):
    def test_commands(self) -> None:
        sut = ToolBuilder("command")
        self.assertEqual(["command"], sut._commands)
        self.assertEqual(["command", "sub_command"], sut.sub_command._commands)

    def test_prepare(self) -> None:
        runner: ToolRunner = ToolBuilder().command.sub_command.prepare(
            "arg1", "--arg2", "value2", arg3="value3", arg_4=1234
        )
        self.assertEqual(
            ["command", "sub-command", "arg1", "--arg2", "value2", "--arg3", "value3", "--arg-4", 1234],
            runner.command,
        )

    def test_call(self) -> None:
        mock_shell = MagicMock()
        ToolBuilder(shell=mock_shell).command.sub_command("arg1", "--arg2", "value2", arg3="value3", arg_4=1234)
        mock_shell.assert_called_once_with(
            "command", "sub-command", "arg1", "--arg2", "value2", "--arg3", "value3", "--arg-4", 1234
        )


class TestToolRunner(TestCase):
    def test_call(self) -> None:
        mock_shell = MagicMock()
        sut: ToolRunner = ToolRunner(
            ["command", "sub_command"], "arg1", "--arg2", "value2", arg3="value3", arg_4=1234, shell=mock_shell
        )
        sut()
        mock_shell.assert_called_once_with(
            "command", "sub-command", "arg1", "--arg2", "value2", "--arg3", "value3", "--arg-4", 1234
        )

    def test_fixup_commands(self) -> None:
        self.assertEqual(
            ["part1", "part-2", "part-three"], ToolRunner._fixup_commands(["part1", "part_2", "part-three"])
        )

    def test_fixup_args(self) -> None:
        self.assertEqual(
            ["arg1", "--arg2", "arg3", True, 123, "a", 1, True, False],
            ToolRunner._fixup_args(["arg1", "--arg2", None, "arg3", True, 123, ["a", 1, (True, False)]]),
        )

    def test_fixup_kwargs(self) -> None:
        self.assertEqual(
            ["--arg-one", "one", "--arg_2", "two", "-a", "--a-list", "a", "b", "c"],
            ToolRunner._fixup_kwargs(
                {"arg_one": "one", "--arg_2": "two", "a": True, "enable_arg": False, "a_list": ["a", "b", "c"]}
            ),
        )


class TestDeepFlatten(TestCase):
    def test(self) -> None:
        self.assertEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 0], list(deep_flatten([1, [2, [3, 4, 5], [6, 7], 8], 9, 0])))
