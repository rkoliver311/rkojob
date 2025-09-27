# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from __future__ import annotations

import functools
import os
import re
import signal
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from functools import singledispatch
from os import PathLike
from pathlib import Path
from threading import Thread
from typing import (
    IO,
    Any,
    Callable,
    Iterable,
    Literal,
    Mapping,
    Sequence,
    TextIO,
    Type,
    TypeVar,
)


class ShellResult:
    def __init__(self, return_code: int, stdout: str, stderr: str):
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr


class ShellException(Exception):
    def __init__(self, result: ShellResult) -> None:
        super().__init__(result.stderr if result.stderr else f"return_code={result.return_code}")
        self.result: ShellResult = result


class Shell:
    def __init__(
        self,
        show_stdout: bool = True,
        show_stderr: bool = True,
        cwd: str | PathLike | None = None,
        env: dict[str, Any] | None = None,
        tee_stdout: str | PathLike | IO[str] | None = None,
        tee_stderr: str | PathLike | IO[str] | None = None,
        stderr_to_stdout: bool = False,
        raise_on_error: bool = True,
        shell: bool = False,
    ) -> None:
        self._show_stdout: bool = show_stdout
        self._show_stderr: bool = show_stderr
        self._cwd: str | PathLike | None = cwd
        self._env: dict[str, Any] | None = env
        self._tee_stdout: str | PathLike | IO[str] | None = tee_stdout
        self._tee_stderr: str | PathLike | IO[str] | None = tee_stderr
        self._stderr_to_stdout: bool = stderr_to_stdout
        self._raise_on_error: bool = raise_on_error
        self._shell: bool = shell

        # for mocking
        self._popen: Any = subprocess.Popen

    def __call__(
        self,
        *args: Any,
        show_stdout: bool | None = None,
        show_stderr: bool | None = None,
        cwd: str | PathLike | None = None,
        env: dict[str, Any] | None = None,
        tee_stdout: str | PathLike | IO[str] | None = None,
        tee_stderr: str | PathLike | IO[str] | None = None,
        stderr_to_stdout: bool | None = None,
        raise_on_error: bool | None = None,
        shell: bool | None = None,
    ) -> ShellResult:
        if show_stdout is None:
            show_stdout = self._show_stdout
        if show_stderr is None:
            show_stderr = self._show_stderr
        if cwd is None:
            cwd = self._cwd
        if env is None:
            env = self._env
        if tee_stdout is None:
            tee_stdout = self._tee_stdout
        if tee_stderr is None:
            tee_stderr = self._tee_stderr
        if stderr_to_stdout is None:
            stderr_to_stdout = self._stderr_to_stdout
        if raise_on_error is None:
            raise_on_error = self._raise_on_error
        if shell is None:
            shell = self._shell

        def _normalize_tee(target: str | PathLike | IO[str] | None) -> str | IO[str] | None:
            if isinstance(target, (str, PathLike)):
                return os.fspath(target)
            return target

        def _open_tee(target: str | PathLike | IO[str] | None) -> tuple[IO[str] | None, bool]:
            if isinstance(target, (str, PathLike)):
                return open(target, "w", encoding="utf-8"), True
            elif target is not None:
                return target, False
            return None, False

        def _read_stream(
            stream: TextIO, lines: list[str], tee_stream: TextIO | None, show_stream: TextIO | None
        ) -> None:
            for line in stream:
                lines.append(line)
                if show_stream:
                    show_stream.write(line)
                if tee_stream:
                    tee_stream.write(line)
                    tee_stream.flush()

        tee_stdout = _normalize_tee(tee_stdout)
        tee_stderr = _normalize_tee(tee_stderr)

        stdout_tee: IO[str] | None
        close_stdout: bool
        stdout_tee, close_stdout = _open_tee(tee_stdout)

        stderr_tee: IO[str] | None
        close_stderr: bool
        if tee_stdout == tee_stderr:
            stderr_tee = stdout_tee
            close_stderr = False
        else:
            stderr_tee, close_stderr = _open_tee(tee_stderr)

        # Choose stderr handling mode
        stderr_setting: int = subprocess.STDOUT if stderr_to_stdout else subprocess.PIPE

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        stdout_thread: Thread | None = None
        stderr_thread: Thread | None = None

        if env is not None:
            combined_env: dict[str, Any] = {**os.environ}
            combined_env.update(**env)
            env = combined_env

        proc = self._popen(
            args,
            stdout=subprocess.PIPE,
            stderr=stderr_setting,
            text=True,
            cwd=cwd,
            env=env,
            shell=shell,
        )

        # Capture and route stdout
        if proc.stdout:
            stdout_thread = Thread(
                target=_read_stream,
                args=(proc.stdout, stdout_lines, sys.stdout if show_stdout else None, stdout_tee),
                name="stdout_thread",
            )
            stdout_thread.start()

        # Capture stderr if separate
        if not stderr_to_stdout and proc.stderr:
            stderr_thread = Thread(
                target=_read_stream,
                args=(proc.stderr, stderr_lines, sys.stderr if show_stderr else None, stderr_tee),
                name="stderr_thread",
            )
            stderr_thread.start()

        try:
            proc.wait()
            if stdout_thread:
                stdout_thread.join()
            if stderr_thread:
                stderr_thread.join()
        except KeyboardInterrupt:  # pragma: no cover
            if proc is not None:
                proc.send_signal(signal.SIGINT)

        if stdout_tee and close_stdout:
            stdout_tee.close()
        if stderr_tee and close_stderr:
            stderr_tee.close()

        result: ShellResult = ShellResult(
            return_code=proc.returncode,
            stdout="".join(stdout_lines),
            stderr="".join(stderr_lines) if not stderr_to_stdout else "",
        )

        if raise_on_error and result.return_code != 0:
            raise ShellException(result)

        return result


def to_kebab(name: str) -> str:
    # Insert dashes before capital letters
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1-\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", s)
    # Replace underscores with dashes
    s = s.replace("_", "-")
    # Normalize consecutive dashes and lowercase
    return re.sub(r"-+", "-", s).lower()


def to_camel(name: str) -> str:
    parts = re.split(r"[-_]", name)
    return parts[0].lower() + "".join(word.capitalize() for word in parts[1:])


class ToolBuilder:
    """
    A command builder class for constructing and executing CLI tools.

    `ToolBuilder` enables dynamic construction of shell commands through chained
    attribute access, followed by immediate execution when called with arguments.

    This class is primarily intended to be used as a front-end for tools like `git`,
    `docker`, or `kubectl`, where subcommands and options are commonly used.

    Example usage::

        git = ToolBuilder("git")
        git.clone("https://github.com/user/repo.git", depth=1)

        # Executes: git clone https://github.com/user/repo.git --depth 1
    ::

    Attribute access appends subcommands::

        git.remote.add("origin", "git@github.com:user/repo.git")
        # Executes: git remote add origin git@github.com:user/repo.git
    ::

    Keyword arguments are converted to CLI options:
        - Underscores (`_`) are converted to dashes (`-`)
        - Single-letter keywords become short flags (e.g., `v=True` → `-v`)
        - Boolean flags are added if True, omitted if False or None
        - Positional arguments can be passed as strings or iterables

    Optional:
        A custom `Shell` instance can be passed to override execution behavior,
        allowing features like dry-run, logging, or mocking.

    Parameters:
        *commands (str): Initial command parts (e.g., "git", "docker").
        shell (Shell | None): Optional Shell executor instance.

    See also:
        - `Shell`: Responsible for actually running the command.
        - `ToolRunner` (optional): If using deferred execution or richer context control.

    """

    def __init__(
        self, *commands: str, runner_factory: Callable[..., ToolRunner] | None = None, shell: Shell | None = None
    ):
        """
        :param commands: Optional initial command parts.
        :param runner_factory: Optional `ToolRunner` factory to use prepare
         and execute the tool.
        :param shell: Optional `Shell` instance to use instead of default.
        """
        self._commands: list[str] = list(commands)
        self._shell: Shell | None = shell

        self._builder_type: Type[ToolBuilder] = type(self)
        self._runner_factory: Callable[..., ToolRunner] = runner_factory or ToolRunner

    def prepare(self, *args, **kwargs) -> ToolRunner:
        """
        Prepare the command and create a `ToolRunner` for deferred execution.
        :param args: Additional args to be passed into the command.
        :param kwargs: Additional kwargs to be passed into the command.
        """
        return self._runner_factory(self._commands, *args, **kwargs, shell=self._shell)

    def __getattr__(self, name: str):
        return self._builder_type(*self._commands, name, runner_factory=self._runner_factory, shell=self._shell)

    def __call__(self, *args: Any, **kwargs) -> ShellResult:
        runner: ToolRunner = self.prepare(*args, **kwargs)
        return runner()


ArgsRenderer = Callable[[Any], list[str]]
KwArgsRenderer = Callable[[str, Any], list[str]]
KeyRenderer = Callable[[str], str]
ValueRenderer = Callable[[Any], list[str]]


@singledispatch
def render_value(v: Any) -> list[str]:
    # Default: str() it
    return [str(v)]


@render_value.register(type(None))
def _render_none(_: None) -> list[str]:
    return []


@render_value.register(bool)
def _render_bool(v: bool) -> list[str]:
    # Typically we'll just key off of whether
    # the list is empty or not but include a
    # meaningful value anyway.
    return ["true"] if v else []


@render_value.register(Path)
def _render_path(p: Path) -> list[str]:
    return [str(p)]


@render_value.register(list)
@render_value.register(tuple)
def _render_list(seq: Sequence[Any]) -> list[str]:
    out: list[str] = []
    for x in seq:
        out.extend(render_value(x))
    return out


@render_value.register(dict)
def _render_dict(d: dict[Any, Any]) -> list[str]:
    # Omit keys with values that are None
    return [f"{key}={value}" for key, value in d.items() if value is not None]


# Enums → value or name
@render_value.register(Enum)
def _render_enum(e: Enum) -> list[str]:
    return [str(e.value)]


def default_value_render(value: Any) -> list[str]:
    return render_value(value)


def csv_value_render(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [",".join(value)]
    return default_value_render(value)


def default_flag_render(key: str) -> str:
    if key.startswith("-"):
        return key
    if len(key) == 1:
        return f"-{key}"
    return f"--{to_kebab(key)}"


OptionStyle = Literal["auto", "flag_and_value", "flag_only", "flag_only_negate", "value_only"]
"""
auto:
  If value is `True`, `False`, or `None`, act like `FLAG_ONLY`. Otherwise act like `FLAG_AND_VALUE`.

flag_and_value:
  `--option-name value` Repeatable options can be achieved by rendering values as a list.

flag_only: `--option-name` if value is True

flag_only_negate: `--option-name` if value is False

value_only: `value` (positional)
"""


class OptionRenderer:
    def __init__(
        self,
        style: OptionStyle = "auto",
        flag_value_separator: str | None = None,
        flag_renderer: KeyRenderer = default_flag_render,
        value_renderer: ValueRenderer = default_value_render,
    ) -> None:
        self.style: OptionStyle = style
        self.flag_value_separator: str | None = flag_value_separator
        self.flag_renderer: KeyRenderer = flag_renderer
        self.value_render: ValueRenderer = value_renderer

    def __call__(self, key: str, value: Any) -> list[str]:
        return self.render(key, value)

    def render(self, key: str, value: Any) -> list[str]:
        style: OptionStyle = self.style
        if style == "auto":
            if value is None or value is True or value is False:
                style = "flag_only"
            else:
                style = "flag_and_value"

        flag: str = self.flag_renderer(key)
        rendered_value: list[str] = self.value_render(value)

        match style:
            case "flag_and_value":
                if self.flag_value_separator is None:
                    out: list[str] = []
                    for v in rendered_value:
                        out.append(flag)
                        out.append(v)
                    return out
                else:
                    return [f"{flag}{self.flag_value_separator}{v}" for v in rendered_value]

            case "flag_only":
                if rendered_value:
                    return [flag]
                else:
                    return []

            case "flag_only_negate":
                if rendered_value:
                    return []
                else:
                    return [flag]

            case "value_only":
                return rendered_value

            case _:
                raise ValueError(f"Unknown style type: {self.style!r}")


@dataclass
class ToolRunnerConfig:
    args_renderer: ArgsRenderer
    kwarg_renderers: Mapping[str, KwArgsRenderer]
    default_kwarg_renderer: KwArgsRenderer


DEFAULT_TOOL_RUNNER_CONFIG = ToolRunnerConfig(
    args_renderer=default_value_render,
    kwarg_renderers={},
    default_kwarg_renderer=OptionRenderer(),
)


class ToolRunner:
    """
    Represents a fully constructed command ready for execution.

    `ToolRunner` is created by `ToolBuilder` to hold the finalized command parts,
    positional arguments, keyword-based options, and any execution context
    (e.g., environment variables, working directory). Calling a `ToolRunner` instance
    executes the command using the associated `Shell`.

    Unlike `ToolBuilder`, which focuses on command construction, `ToolRunner` is
    responsible for formatting the complete command line and running it.

    Example::

        runner = ToolBuilder("git").clone.prepare("https://repo", depth=1)
        runner.with_env(GIT_TERMINAL_PROMPT="0").in_dir("/tmp")()
        # Executes: git clone https://repo --depth 1 with env and cwd set
    ::

    Notes:
        - Keyword arguments are converted to CLI options using the same logic as `ToolBuilder`
        - Command-line arguments are "fixed up" just before execution (e.g., `_ → -`, bools handled)
        - This class enables richer features like dry-run, logging, or command introspection

    See also:
        - `ToolBuilder.prepare(...)`: Returns a `ToolRunner` instead of executing immediately
        - `Shell`: Responsible for actual subprocess execution
    """

    def __init__(
        self,
        commands: list[str],
        *args,
        shell: Shell | None = None,
        config: ToolRunnerConfig | None = None,
        **kwargs,
    ) -> None:
        """
        Create a new `ToolRunner` instance. An instance is typically created
        by a `ToolBuilder` instance.

        :param commands: Command(s) for the runner.
        :param args: Positional arguments to the command(s).
        :param shell: Optional `Shell` instance used to run the command.
        :param config: Optional `ToolRunnerConfig` used to influence how
         options rendered for execution.
        :param kwargs:
        """
        self._commands: list[str] = commands
        self._args: list[Any] = list(args)
        self._kwargs: dict[str, Any] = kwargs
        self._shell: Shell = shell or Shell()

        self._config: ToolRunnerConfig = config or DEFAULT_TOOL_RUNNER_CONFIG

        self._env: dict[str, str] | None = None
        self._cwd: str | PathLike | None = None

    @classmethod
    def factory(
        cls,
        args_renderer: ArgsRenderer | None = None,
        kwarg_renderers: Mapping[str, KwArgsRenderer] | None = None,
        default_kwarg_renderer: KwArgsRenderer | None = None,
        config: ToolRunnerConfig | None = None,
    ) -> Callable[..., ToolRunner]:
        if config is None:
            config = ToolRunnerConfig(
                args_renderer=args_renderer or default_value_render,
                kwarg_renderers=kwarg_renderers or {},
                default_kwarg_renderer=default_kwarg_renderer or OptionRenderer(),
            )
        return functools.partial(ToolRunner, config=config)

    def __call__(self, *_, **kwargs) -> ShellResult:
        """
        Run the command represented by this `ToolRunner`
        :param kwargs: Additional kwargs to pass into the runner's `shell`.
        """
        if self._env:
            kwargs.update(env=self._env)
        if self._cwd:
            kwargs.update(cwd=self._cwd)
        return self._shell(*self.command, **kwargs)

    @property
    def command(self) -> list[Any]:
        """:returns: The rendered command to be run."""
        return self._fixup_commands(self._commands) + self._fixup_args(self._args) + self._fixup_kwargs(self._kwargs)

    def with_env(self, **kwargs) -> ToolRunner:
        """
        Run the command with the provided environment variables.
        This method can be called multiple times to build up
        the map of environment variables.
        :param kwargs: The environment variables to add to the runner's
         environment.
        """
        if self._env is None:
            self._env = {}
        self._env.update(**kwargs)
        return self

    def in_dir(self, cwd: str | PathLike) -> ToolRunner:
        """
        Run the command in the provided directory.
        :param cwd: The directory to run the command in.
        """
        self._cwd = cwd
        return self

    def _fixup_commands(self, parts: list[str]) -> list[str]:
        return [part.replace("_", "-") for part in parts]

    def _fixup_args(self, args: Iterable[Any]) -> list[str]:
        out: list[str] = []
        for a in args:
            if a:
                out.extend(self._config.args_renderer(a))
        return out

    def _fixup_kwargs(self, kwargs: dict[str, Any]) -> list[str]:
        out: list[str] = []
        for k, v in kwargs.items():  # insertion-order stable
            renderer: KwArgsRenderer = self._config.kwarg_renderers.get(k, self._config.default_kwarg_renderer)
            out.extend(renderer(k, v))
        return out


def deep_flatten(xs: Iterable[Any]) -> Iterable[Any]:
    for x in xs:
        if isinstance(x, Iterable) and not isinstance(x, (str, bytes)):
            yield from deep_flatten(x)
        else:
            yield x


T = TypeVar("T")


def not_none(value: T | None, name: str | None = None) -> T:
    if value is None:
        raise ValueError(f"{name if name else 'Value'} must not be {None}.")
    return value
