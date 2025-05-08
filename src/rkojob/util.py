from __future__ import annotations

import os
import re
import subprocess
import sys
from os import PathLike
from pathlib import Path
from typing import IO, Any, Iterable


def as_path(value: str | PathLike | None) -> Path | None:
    """
    Returns a `Path` instance for the provided value.
    :param value: The value to return as a `Path` instance. If `value` is a `Path`, return it unchanged.
    :return: A `Path` instance or `None` if `value` is `None`.
    """
    if value is None or isinstance(value, Path):
        return value
    return Path(os.fspath(value))


class ShellResult:
    def __init__(self, return_code: int, stdout: str, stderr: str):
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr


class ShellException(Exception):
    def __init__(self, result: ShellResult) -> None:
        super().__init__(result.stderr)
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

        proc = self._popen(
            args,
            stdout=subprocess.PIPE,
            stderr=stderr_setting,
            text=True,
            cwd=cwd,
            env=env,
            shell=shell,
        )

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        # Capture and route stdout
        if proc.stdout:
            for line in proc.stdout:
                stdout_lines.append(line)
                if show_stdout:
                    sys.stdout.write(line)
                if stdout_tee:
                    stdout_tee.write(line)
                    stdout_tee.flush()

        # Capture stderr if separate
        if not stderr_to_stdout and proc.stderr:
            for line in proc.stderr:
                stderr_lines.append(line)
                if show_stderr:
                    sys.stderr.write(line)
                if stderr_tee:
                    stderr_tee.write(line)
                    stderr_tee.flush()

        proc.wait()

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

    def __init__(self, *commands: str, shell: Shell | None = None):
        """
        :param commands: Optional initial command parts.
        :param shell: Optional `Shell` instance to use instead of default.
        """
        self._commands: list[str] = list(commands)
        self._shell: Shell | None = shell

    def prepare(self, *args, runner_type: type[ToolRunner] | None = None, **kwargs) -> ToolRunner:
        """
        Prepare the command and create a `ToolRunner` for deferred execution.
        :param args: Additional args to be passed into the command.
        :param runner_type: The type of `ToolRunner` instance to create and return.
        :param kwargs: Additional kwargs to be passed into the command.
        """
        if runner_type is None:
            runner_type = ToolRunner
        return runner_type(self._commands, *args, **kwargs, shell=self._shell)

    def __getattr__(self, name: str):
        return ToolBuilder(*self._commands, name, shell=self._shell)

    def __call__(self, *args: Any, **kwargs) -> ShellResult:
        runner: ToolRunner = self.prepare(*args, **kwargs)
        return runner()


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

    def __init__(self, commands: list[str], *args, shell: Shell | None = None, **kwargs) -> None:
        self._commands: list[str] = commands
        self._args: list[Any] = list(args)
        self._kwargs: dict[str, Any] = kwargs
        self._shell: Shell = shell or Shell()

    def __call__(self, *args, **kwargs) -> ShellResult:
        return self._shell(*self.command)

    @property
    def command(self) -> list[Any]:
        return self._fixup_commands(self._commands) + self._fixup_args(self._args) + self._fixup_kwargs(self._kwargs)

    @classmethod
    def _fixup_commands(cls, parts: list[str]) -> list[str]:
        return [part.replace("_", "-") for part in parts]

    @classmethod
    def _fixup_args(cls, args: Iterable[Any]) -> list[Any]:
        fixed_up: list[Any] = []
        for arg in args:
            if arg is None:
                continue
            if isinstance(arg, (list, tuple)):
                fixed_up.extend(cls._fixup_args(arg))
            else:
                fixed_up.append(cls._fixup_arg(arg))
        return fixed_up

    @classmethod
    def _fixup_arg(cls, arg: Any) -> Any:
        return arg

    @classmethod
    def _fixup_kwargs(cls, kwargs: dict[str, Any]) -> list[Any]:
        fixed_up: list[Any] = []

        for key, arg in kwargs.items():
            if arg is None or arg is False:
                continue
            fixed_up.append(cls._fixup_key(key))

            if isinstance(arg, (list, tuple)):
                fixed_up.extend(ToolRunner._fixup_args(arg))
            elif arg is not True:
                fixed_up.append(arg)

        return fixed_up

    @classmethod
    def _fixup_key(cls, key: str) -> str:
        if key.startswith("-"):
            return key
        if len(key) == 1:
            return f"-{key}"
        return f"--{to_kebab(key)}"
