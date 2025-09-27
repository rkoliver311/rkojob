# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.
import os
from enum import Enum
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Any
from unittest import TestCase, mock
from unittest.mock import MagicMock

from rkojob.util import (
    OptionRenderer,
    Shell,
    ShellException,
    ShellResult,
    ToolBuilder,
    ToolRunner,
    csv_value_render,
    deep_flatten,
    default_flag_render,
    default_value_render,
    not_none,
    render_value,
    to_camel,
    to_kebab,
)


class TestShellException(TestCase):
    def test(self) -> None:
        result = ShellResult(return_code=1, stdout="Working...", stderr="error")
        sut = ShellException(result=result)
        self.assertIs(result, sut.result)
        self.assertEqual("error", str(sut))

    def test_no_stderr(self) -> None:
        result = ShellResult(return_code=1, stdout="Working...", stderr="")
        sut = ShellException(result=result)
        self.assertIs(result, sut.result)
        self.assertEqual("return_code=1", str(sut))


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
        with TemporaryDirectory() as temp_dir:
            temp_file_path = Path(temp_dir) / "temp_file.out"
            with temp_file_path.open(mode="wt+") as temp_file:
                sut = Shell()
                sut._popen = self.mock_popen(stdout=["Hello, world!\n"], stderr=["Secret hello!\n"])
                sut("greet", "Hello, world!", tee_stdout=temp_file)
                sut._popen.assert_called_with(
                    ("greet", "Hello, world!"), stdout=-1, stderr=-1, text=True, cwd=None, env=None, shell=False
                )
            self.assertEqual("Hello, world!\n", temp_file_path.read_text())

    def test_tee_stdout_and_stderr_same(self) -> None:
        with NamedTemporaryFile(mode="wt+") as temp_file:
            sut = Shell()
            sut._popen = self.mock_popen(stdout=["Hello, world!\n"], stderr=["Secret hello!\n"])
            sut("greet", "Hello, world!", tee_stdout=temp_file.name, tee_stderr=temp_file.name)
            sut._popen.assert_called_with(
                ("greet", "Hello, world!"), stdout=-1, stderr=-1, text=True, cwd=None, env=None, shell=False
            )
            self.assertEqual("Hello, world!\nSecret hello!\n", Path(temp_file.name).read_text())

    @mock.patch.dict(os.environ, {"var1": "value1", "var2": "value2"}, clear=True)
    def test_env(self) -> None:
        sut = Shell()
        sut._popen = self.mock_popen(stdout=["Hello, world!\n"], stderr=["Secret hello!\n"])

        result: ShellResult = sut("greet", "Hello, world!", env={"var2": "override"})

        sut._popen.assert_called_with(
            ("greet", "Hello, world!"),
            stdout=-1,
            stderr=-1,
            text=True,
            cwd=None,
            env={"var1": "value1", "var2": "override"},
            shell=False,
        ),

        self.assertEqual("Hello, world!\n", result.stdout)
        self.assertEqual("Secret hello!\n", result.stderr)
        self.assertEqual(0, result.return_code)

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
            ["command", "sub-command", "arg1", "--arg2", "value2", "--arg3", "value3", "--arg-4", "1234"],
            runner.command,
        )

    def test_call(self) -> None:
        mock_shell = MagicMock()
        ToolBuilder(shell=mock_shell).command.sub_command("arg1", "--arg2", "value2", arg3="value3", arg_4=1234)
        mock_shell.assert_called_once_with(
            "command", "sub-command", "arg1", "--arg2", "value2", "--arg3", "value3", "--arg-4", "1234"
        )

    def test_sub_class(self) -> None:
        class SubClassRunner(ToolRunner):
            pass

        class SubClassBuilder(ToolBuilder):
            def __init__(self, *args, **kwargs):
                kwargs.setdefault("runner_factory", SubClassRunner)
                super().__init__(*args, **kwargs)

        sut = SubClassBuilder("tool").sub_command
        self.assertIsInstance(sut, SubClassBuilder)
        runner = sut.prepare(arg="value")
        self.assertIsInstance(runner, SubClassRunner)


class TestRenderValue(TestCase):
    def test(self) -> None:
        self.assertEqual(["123"], render_value(123))

    def test_none(self) -> None:
        self.assertEqual([], render_value(None))

    def test_true(self) -> None:
        self.assertEqual(["true"], render_value(True))

    def test_false(self) -> None:
        self.assertEqual([], render_value(False))

    def test_path(self) -> None:
        self.assertEqual(["/path/to/file"], render_value(Path("/path") / "to" / "file"))

    def test_list(self) -> None:
        self.assertEqual(["a", "1"], render_value(["a", 1, False]))

    def test_tuple(self) -> None:
        self.assertEqual(["a", "1"], render_value(("a", 1, False)))

    def test_dict(self) -> None:
        self.assertEqual(["a=1", "b=2", "c=3.14"], render_value(dict(a="1", b=2, c=3.14, d=None)))

    def test_enum(self) -> None:
        class Foo(Enum):
            BAR = "bar"

        self.assertEqual(["bar"], render_value(Foo.BAR))


class TestCsvValueRender(TestCase):
    def test_list(self) -> None:
        self.assertEqual(["a,b,c"], csv_value_render(["a", "b", "c"]))

    def test_tuple(self) -> None:
        self.assertEqual(["a,b,c"], csv_value_render(("a", "b", "c")))

    def test_non_list(self) -> None:
        self.assertEqual(["abc"], csv_value_render("abc"))


class TestDefaultFlagFormat(TestCase):
    def test_sort_key(self) -> None:
        self.assertEqual("-f", default_flag_render("f"))

    def test_long_key(self) -> None:
        self.assertEqual("--flag-key", default_flag_render("flag_key"))

    def test_key_with_dash(self) -> None:
        self.assertEqual("-flag", default_flag_render("-flag"))


class TestOptionRenderer(TestCase):
    # --- Defaults / basic formatting ---

    def test_default(self) -> None:
        # AUTO + str -> FLAG_AND_VALUE (space)
        self.assertEqual(
            ["--flag-name", "value"],
            OptionRenderer().render("flag_name", "value"),
        )

    def test_single_letter_flag_short_form(self) -> None:
        self.assertEqual(
            ["-f", "v"],
            OptionRenderer().render("f", "v"),
        )

    # --- FLAG_AND_VALUE ---

    def test_flag_and_value_space_single(self) -> None:
        self.assertEqual(
            ["--name", "alice"],
            OptionRenderer(style="flag_and_value").render("name", "alice"),
        )

    def test_flag_and_value_space_list_repeats_flag(self) -> None:
        # list => repeat: --name v1 --name v2
        self.assertEqual(
            ["--name", "a", "--name", "b"],
            OptionRenderer(style="flag_and_value").render("name", ["a", "b"]),
        )

    def test_flag_and_value_space_list_csv(self):
        # list  => csv: --name v1,v2
        self.assertEqual(
            ["--name", "a,b"],
            OptionRenderer(style="flag_and_value", value_renderer=csv_value_render).render("name", ["a", "b"]),
        )

    def test_flag_and_value_equals_single(self) -> None:
        self.assertEqual(
            ["--cfg=on"],
            OptionRenderer(style="flag_and_value", flag_value_separator="=").render("cfg", "on"),
        )

    def test_flag_and_value_equals_list_each_pair(self) -> None:
        # equals + list => ["--opt=a", "--opt=b"]
        self.assertEqual(
            ["--opt=a", "--opt=b"],
            OptionRenderer(style="flag_and_value", flag_value_separator="=").render("opt", ["a", "b"]),
        )

    def test_flag_and_value_dict_pairs(self) -> None:
        # default value renderer should map dict -> ["k=v", ...]
        self.assertEqual(
            ["--build-arg", "K1=V1", "--build-arg", "K2=V2"],
            OptionRenderer(style="flag_and_value").render("build_arg", {"K1": "V1", "K2": "V2"}),
        )

    # --- FLAG_ONLY ---

    def test_flag_only_true_renders_flag(self) -> None:
        # default_value_render(True) should be non-empty (e.g., ["true"])
        self.assertEqual(
            ["--verbose"],
            OptionRenderer(style="flag_only").render("verbose", True),
        )

    def test_flag_only_false_omits_flag(self) -> None:
        # default_value_render(False) should be empty => omit
        self.assertEqual(
            [],
            OptionRenderer(style="flag_only").render("verbose", False),
        )

    def test_flag_only_none_omits_flag(self) -> None:
        self.assertEqual(
            [],
            OptionRenderer(style="flag_only").render("verbose", None),
        )

    # --- FLAG_ONLY_NEGATE ---

    def test_flag_only_negate_true_omits_flag(self) -> None:
        # negate: show flag only when value is falsy/None
        self.assertEqual(
            [],
            OptionRenderer(style="flag_only_negate").render("http2", True),
        )

    def test_flag_only_negate_false_renders_flag(self) -> None:
        self.assertEqual(
            ["--http2"],
            OptionRenderer(style="flag_only_negate").render("http2", False),
        )

    def test_flag_only_negate_none_renders_flag(self) -> None:
        self.assertEqual(
            ["--http2"],
            OptionRenderer(style="flag_only_negate").render("http2", None),
        )

    def test_flag_only_negate_with_flag_format(self) -> None:
        self.assertEqual(
            ["--no-http2"],
            OptionRenderer(style="flag_only_negate", flag_renderer=lambda _: "--no-http2").render("http2", False),
        )

    # --- VALUE_ONLY ---

    def test_value_only_scalar(self) -> None:
        self.assertEqual(
            ["file.txt"],
            OptionRenderer(style="value_only").render("files", "file.txt"),
        )

    def test_value_only_list(self) -> None:
        self.assertEqual(
            ["a.txt", "b.txt"],
            OptionRenderer(style="value_only").render("files", ["a.txt", "b.txt"]),
        )

    def test_value_only_dict_pairs(self) -> None:
        self.assertEqual(
            ["K=V", "A=B"],
            OptionRenderer(style="value_only").render("env", {"K": "V", "A": "B"}),
        )

    # --- AUTO ---

    def test_auto_with_string_behaves_like_flag_and_value(self) -> None:
        self.assertEqual(
            ["--mode", "fast"],
            OptionRenderer(style="auto").render("mode", "fast"),
        )

    def test_auto_with_true_behaves_like_flag_only_true(self) -> None:
        self.assertEqual(
            ["--debug"],
            OptionRenderer(style="auto").render("debug", True),
        )

    def test_auto_with_false_behaves_like_flag_only_false(self) -> None:
        self.assertEqual(
            [],
            OptionRenderer(style="auto").render("debug", False),
        )

    def test_auto_with_none_behaves_like_flag_only_none(self) -> None:
        self.assertEqual(
            [],
            OptionRenderer(style="auto").render("debug", None),
        )

    # --- Custom renderers hooks ---

    def test_custom_flag_renderer_used(self) -> None:
        def short_dash(_k: str) -> str:
            return "-J"

        self.assertEqual(
            ["-J", "4"],
            OptionRenderer(flag_renderer=short_dash).render("jobs", 4),
        )

    def test_custom_value_renderer_used(self) -> None:
        def csv_values(v: object) -> list[str]:
            if isinstance(v, (list, tuple)):
                return [",".join(map(str, v))]
            return [str(v)]

        self.assertEqual(
            ["--include", "a,b,c"],
            OptionRenderer(value_renderer=csv_values).render("include", ["a", "b", "c"]),
        )

    def test_bad_style(self) -> None:
        with self.assertRaises(ValueError) as e:
            _ = OptionRenderer(style="foo").render("key", "value")  # type: ignore[arg-type]
        self.assertEqual("Unknown style type: 'foo'", str(e.exception))


class TestToolRunner(TestCase):
    def test_call(self) -> None:
        mock_shell = MagicMock()
        sut: ToolRunner = ToolRunner(
            ["command", "sub_command"], "arg1", "--arg2", "value2", arg3="value3", arg_4=1234, shell=mock_shell
        )
        sut(env={"VAR": "value"})
        mock_shell.assert_called_once_with(
            "command",
            "sub-command",
            "arg1",
            "--arg2",
            "value2",
            "--arg3",
            "value3",
            "--arg-4",
            "1234",
            env={"VAR": "value"},
        )

    def test_with_env(self) -> None:
        mock_shell = MagicMock()
        sut: ToolRunner = ToolRunner(["command", "sub_command"], "arg", arg2="value", shell=mock_shell)
        sut.with_env(VAR="value")
        sut()
        mock_shell.assert_called_once_with("command", "sub-command", "arg", "--arg2", "value", env={"VAR": "value"})

    def test_in_dir(self) -> None:
        mock_shell = MagicMock()
        sut: ToolRunner = ToolRunner(["command", "sub_command"], "arg", arg2="value", shell=mock_shell)
        sut = sut.in_dir(Path("/some/dir"))
        sut()
        mock_shell.assert_called_once_with("command", "sub-command", "arg", "--arg2", "value", cwd=Path("/some/dir"))

    def test_fixup_commands(self) -> None:
        sut = ToolRunner([])
        self.assertEqual(["part1", "part-2", "part-three"], sut._fixup_commands(["part1", "part_2", "part-three"]))

    def test_commands_only(self) -> None:
        mock_shell = MagicMock()
        sut = ToolRunner(["command", "sub"], shell=mock_shell)
        sut()
        mock_shell.assert_called_once_with("command", "sub")

    def test_with_args(self) -> None:
        mock_shell = MagicMock()
        sut = ToolRunner(["command", "sub"], "arg1", "arg2", shell=mock_shell)
        sut()
        mock_shell.assert_called_once_with("command", "sub", "arg1", "arg2")

    def test_path_arg(self) -> None:
        mock_shell = MagicMock()
        sut = ToolRunner(["command", "sub"], "arg1", Path("path", "to", "file"), shell=mock_shell)
        sut()
        mock_shell.assert_called_once_with("command", "sub", "arg1", "path/to/file")

    def test_enum_arg(self) -> None:
        class Foo(Enum):
            BAR = "bar"

        mock_shell = MagicMock()
        sut = ToolRunner(["command", "sub"], "arg1", Foo.BAR, shell=mock_shell)
        sut()
        mock_shell.assert_called_once_with("command", "sub", "arg1", "bar")

    def test_with_kwargs(self) -> None:
        mock_shell = MagicMock()
        sut = ToolRunner(["command", "sub"], "arg1", "arg2", shell=mock_shell, foo="value")
        sut()
        mock_shell.assert_called_once_with("command", "sub", "arg1", "arg2", "--foo", "value")

    def test_with_value_renderer(self) -> None:
        def render_value(value: Any) -> list[str]:
            if value is True:
                return ["YES"]
            if value is False:
                return ["NO"]
            return default_value_render(value)

        mock_shell = MagicMock()
        sut = ToolRunner.factory(args_renderer=render_value)(["command", "sub"], "arg1", True, shell=mock_shell)
        sut()
        mock_shell.assert_called_once_with("command", "sub", "arg1", "YES")

    def test_with_kwarg_renderers(self) -> None:
        kwarg_renderers = dict(flag_name=OptionRenderer("flag_only"))
        mock_shell = MagicMock()
        sut = ToolRunner.factory(kwarg_renderers=kwarg_renderers)(
            ["command", "sub"],
            "arg1",
            "arg2",
            shell=mock_shell,
            flag_name=True,
        )
        sut()
        mock_shell.assert_called_once_with("command", "sub", "arg1", "arg2", "--flag-name")

    def test_with_csv(self) -> None:
        kwarg_renderers = {
            "csv_option": OptionRenderer(value_renderer=csv_value_render),
        }

        mock_shell = MagicMock()
        sut = ToolRunner.factory(kwarg_renderers=kwarg_renderers)(
            ["command", "sub"],
            "arg1",
            "arg2",
            shell=mock_shell,
            repeating_option=["value1", "value2", "value3"],
            csv_option=["value1", "value2", "value3"],
        )
        sut()
        mock_shell.assert_called_once_with(
            "command",
            "sub",
            "arg1",
            "arg2",
            "--repeating-option",
            "value1",
            "--repeating-option",
            "value2",
            "--repeating-option",
            "value3",
            "--csv-option",
            "value1,value2,value3",
        )


class TestDeepFlatten(TestCase):
    def test(self) -> None:
        self.assertEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 0], list(deep_flatten([1, [2, [3, 4, 5], [6, 7], 8], 9, 0])))


class TestNotNone(TestCase):
    def test_with_none(self) -> None:
        with self.assertRaises(ValueError) as e:
            _ = not_none(None)
        self.assertEqual("Value must not be None.", str(e.exception))

    def test_with_name(self) -> None:
        with self.assertRaises(ValueError) as e:
            _ = not_none(None, name="Foo")
        self.assertEqual("Foo must not be None.", str(e.exception))

    def test_with_value(self) -> None:
        foo = "Foo"
        self.assertIs(foo, not_none(foo))
