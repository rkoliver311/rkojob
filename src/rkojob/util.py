import os
import subprocess
import sys
from os import PathLike
from pathlib import Path
from typing import IO, Any


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
