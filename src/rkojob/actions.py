# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.
from __future__ import annotations

import shlex
from enum import Enum, auto
from os import PathLike
from pathlib import Path
from typing import Any, Callable, Final

from rkojob import (
    JobAction,
    JobContext,
    JobException,
    JobResolvableValue,
    assign_value,
    job_workspace,
    resolve_map,
    resolve_value,
    resolve_values,
    unassign_value,
)
from rkojob.coerce import as_path
from rkojob.util import (
    Shell,
    ShellException,
    ShellResult,
    ToolBuilder,
    ToolRunner,
)
from rkojob.values import (
    ValueRef,
    as_value_ref,
)


class ShellActionOnError(Enum):
    ERROR = auto()
    WARN = auto()
    RAISE = auto()
    IGNORE = auto()


class ShellAction(JobAction):
    """
    A `JobAction` that executes a shell command.
    """

    ERROR: Final[ShellActionOnError] = ShellActionOnError.ERROR
    WARN: Final[ShellActionOnError] = ShellActionOnError.WARN
    RAISE: Final[ShellActionOnError] = ShellActionOnError.RAISE
    IGNORE: Final[ShellActionOnError] = ShellActionOnError.IGNORE

    def __init__(
        self,
        *args: Any,
        result: ValueRef[ShellResult] | None = None,
        on_error: ShellActionOnError | None = None,
        **kwargs,
    ) -> None:
        """
        :param args: Arguments to execute as a shell command.
        :param result: An optional `ValueRef` to return the `ShellResult` in.
        :param on_error: On a non-zero return code, whether to raise an error, log an error, log a warning,
         or do nothing.
        :param kwargs: Additional keyword args to pass to `Shell()`.
        """
        super().__init__()
        self._args: tuple[Any, ...] = args
        self._kwargs: dict[str, Any] = kwargs
        self.result: ValueRef[ShellResult] = result or ValueRef(name="result")
        self._on_error: ShellActionOnError = on_error or ShellActionOnError.ERROR

    def action(self, context: JobContext) -> None:
        args: list[Any] = resolve_values(self._args, context=context)
        kwargs: dict[str, Any] = resolve_map(self._kwargs, context=context)

        if "cwd" not in kwargs:
            # If cwd was not provided, default to job_workspace (if set)
            workspace: Path | str | None = resolve_value(job_workspace, context=context)
            if workspace is not None:
                workspace_path: Path = Path(workspace).absolute()
                if workspace_path is not None and workspace_path != Path.cwd():
                    kwargs["cwd"] = workspace

        shell: Shell = Shell(**kwargs)

        command: str = shlex.join(args)
        options: str = ", ".join(f"{key}={value}" for key, value in kwargs.items() if key in ("cwd", "env"))
        if options:
            command = f"{command} ({options})"

        result: ShellResult | None = None
        with context.events.section(f"Executing {command}"):
            try:
                result = shell(*args)
            except ShellException as e:
                result = e.result
                match self._on_error:
                    case ShellActionOnError.ERROR:
                        context.events.error(e)
                    case ShellActionOnError.WARN:
                        context.events.warning(e)
                    case ShellActionOnError.RAISE:
                        raise
                    case ShellActionOnError.IGNORE:
                        pass
            finally:
                if result:
                    assign_value(self.result, result)
                    if result.stdout:
                        context.events.output(result.stdout, label="stdout")
                    if result.stderr:
                        context.events.output(result.stderr, label="stderr")
                else:
                    unassign_value(self.result)

    def with_env(self, **kwargs) -> ShellAction:
        """
        Update default environment variables set when executing the shell command.

        :param kwargs: Additional environment variables to set.
        :returns: This instance for call chaining.
        """
        env: dict[str, Any] = self._kwargs.get("env", {})
        env.update(**kwargs)
        self._kwargs["env"] = env
        return self

    def in_dir(self, cwd: JobResolvableValue[str | PathLike]) -> ShellAction:
        """
        Set the current working directory that the shell command will be executed in.

        :param cwd: The directory to execute the shell command.
        :returns: This instance for call chaining.
        """
        self._kwargs["cwd"] = cwd
        return self


class ShellActionBuilder:
    """
    A command builder class for constructing and later executing CLI tools as a
    ``ShellAction``. This class is used similarly to ``ToolBuilder`` but rather
    than executing the command at the end of building, this class returns a
    ``ShellAction`` to be executed later.
    """

    def __init__(
        self,
        *parts: str,
        runner_type: type[ToolRunner] | None = None,
        tool_builder: ToolBuilder | None = None,
        **kwargs,
    ) -> None:
        """
        :param parts: CLI command and sub-commands to be executed.
        :param runner_type: The type of ``ToolRunner`` that will be used to
         prepare, but not execute, the command.
        :param tool_builder: Used internally for building sub-commands.
        :param kwargs: Additional keyword arguments to pass to ``ShellAction``.
        """
        self._tool_builder: ToolBuilder = tool_builder or ToolBuilder(*parts, runner_type=runner_type)
        self._shell_kwargs: dict[str, Any] = kwargs
        # Default to not showing any output
        self._shell_kwargs.setdefault("show_stdout", False)
        self._shell_kwargs.setdefault("show_stderr", False)

    def __getattr__(self, name: str):
        return ShellActionBuilder(tool_builder=self._tool_builder.__getattr__(name), **self._shell_kwargs)

    def __call__(self, *args, **kwargs) -> ShellAction:
        # Return a ShellAction which will execute the actual command.
        return ShellAction(*self._tool_builder.prepare(*args, **kwargs).command, **self._shell_kwargs)


class VerifyTestStructure(JobAction):
    """
    Verify that all expected test files exist in their expected locations.
    """

    def __init__(
        self,
        *,
        source_root: JobResolvableValue[str | PathLike],
        test_root: JobResolvableValue[str | PathLike],
        source_to_test_func: Callable[[str | PathLike, str | PathLike, str | PathLike], str | PathLike | None],
        errors: ValueRef[list[str]] | None = None,
    ) -> None:
        """
        :param source_root: The source root of the project.
        :param test_root: The test root of the project.
        :param source_to_test_func: A function that maps a source file path to an expected test file path.
        :param errors: `ValueRef` in which to return errors.
        """
        super().__init__()
        self.source_root: JobResolvableValue[str | PathLike] = source_root or ValueRef(name="source_root")
        self.test_root: JobResolvableValue[str | PathLike] = test_root or ValueRef(name="test_root")
        self.source_to_test_func: Callable[[str | PathLike, str | PathLike, str | PathLike], str | PathLike | None] = (
            source_to_test_func
        )
        self.errors: ValueRef[list[str]] = as_value_ref(errors, name="errors")

    def action(self, context: JobContext) -> None:
        source_root: Path | None = as_path(resolve_value(self.source_root, context=context))
        test_root: Path | None = as_path(resolve_value(self.test_root, context=context))

        if source_root is None or not source_root.is_dir():
            raise JobException(f"source_root must be a directory: {source_root}")
        if test_root is None or not test_root.is_dir():
            raise JobException(f"test_root must be a directory: {test_root}")

        errors: list[str] = []
        # Iterate over source paths, predict the name of the test file, and assert that it exists
        for source_path in source_root.glob("**/*"):
            relative_source_path: str = str(source_path.relative_to(source_root))

            test_path: Path | None = as_path(self.source_to_test_func(source_root, test_root, source_path))
            if test_path is None:
                context.events.detail(f"Skipping {relative_source_path}")
                continue

            relative_test_path: str = str(test_path.relative_to(test_root))
            context.events.start_item(f"{relative_source_path} -> {relative_test_path}")
            error: str | None = f"{test_path} not found!" if not test_path.exists() else None
            context.events.finish_item("\u2705", error=error)

            if error:
                message: str = f"Test path for source path '{relative_source_path}' not found: {relative_test_path}"
                errors.append(message)

        assign_value(self.errors, errors, context=context)


class VerifyPythonTestStructure(VerifyTestStructure):
    def __init__(
        self,
        *,
        source_root: JobResolvableValue[str | PathLike],
        test_root: JobResolvableValue[str | PathLike],
        errors: ValueRef[list[str]] | None = None,
    ) -> None:
        super().__init__(
            source_root=source_root, test_root=test_root, source_to_test_func=self._expected_test_path, errors=errors
        )

    def _expected_test_path(
        self, source_root: str | PathLike, test_root: str | PathLike, source_path: str | PathLike
    ) -> Path | None:
        source_root_path: Path = Path(source_root)
        test_root_path: Path = Path(test_root)
        source_path_as_path: Path = Path(source_path)

        if source_path_as_path == source_root_path:
            return None

        if self._skip(source_root_path, source_path_as_path):
            return None

        test_name: str = self._test_name(source_path_as_path)
        parent_test_path: Path | None = self._expected_test_path(source_root, test_root, source_path_as_path.parent)
        if parent_test_path:
            return parent_test_path / test_name
        return test_root_path / test_name

    def _skip(self, source_root: Path, source_path: Path) -> bool:
        if source_path.name.startswith("."):
            return True
        if source_path.name.endswith(".egg-info"):
            return True
        if source_path.name in ("__pycache__", "__main__.py"):
            return True

        for parent in source_path.parents:
            if parent == source_root:
                break
            if self._skip(source_root, parent):
                return True
        return False

    def _test_name(self, source_path: Path) -> str:
        if source_path.name == "__init__.py":
            return f"test_{source_path.parent.name}.py"
        return f"test_{source_path.name}"
