import shlex
from os import PathLike
from pathlib import Path
from typing import Any

from rkojob import (
    JobContext,
    JobException,
    JobResolvableValue,
    assign_value,
    resolve_map,
    resolve_value,
    resolve_values,
    unassign_value,
)
from rkojob.job import JobBaseAction
from rkojob.util import (
    Shell,
    ShellException,
    ShellResult,
    ToolBuilder,
    ToolRunner,
    as_path,
)
from rkojob.values import (
    ValueRef,
    as_value_ref,
)


class ShellAction(JobBaseAction):
    def __init__(
        self, *args: Any, result: ValueRef[ShellResult] | None = None, raise_on_error: bool = False, **kwargs
    ) -> None:
        self._args: tuple[Any, ...] = args
        self._kwargs: dict[str, Any] = kwargs
        self.result: ValueRef[ShellResult] = result or ValueRef(name="result")
        self._raise_on_error: bool = raise_on_error

    def action(self, context: JobContext) -> None:
        args: list[Any] = resolve_values(self._args, context=context)
        kwargs: dict[str, Any] = resolve_map(self._kwargs, context=context)
        shell: Shell = Shell(**kwargs)
        command: str = shlex.join(args)

        result: ShellResult | None = None
        with context.status.section(f"Executing {command}"):
            try:
                result = shell(*args)
            except ShellException as e:
                result = e.result
                if self._raise_on_error:
                    raise
                else:
                    # Record the error instead of raising it
                    context.status.error(e)
            finally:
                if result:
                    assign_value(self.result, result)
                    if result.stdout:
                        context.status.output(result.stdout, label="stdout")
                    if result.stderr:
                        context.status.output(result.stderr, label="stderr")
                else:
                    unassign_value(self.result)


class ToolActionBuilder:
    def __init__(
        self, *parts: str, runner_type: type[ToolRunner] | None = None, tool_builder: ToolBuilder | None = None
    ) -> None:
        self._tool_builder: ToolBuilder = tool_builder or ToolBuilder(*parts)
        self._runner_type: type[ToolRunner] | None = runner_type

    def __getattr__(self, name: str):
        return ToolActionBuilder(runner_type=self._runner_type, tool_builder=self._tool_builder.__getattr__(name))

    def __call__(self, *args, **kwargs) -> ShellAction:
        # Return a ShellAction which will execute the actual command.
        return ShellAction(
            *self._tool_builder.prepare(*args, **kwargs, runner_type=self._runner_type).command,
            show_stdout=False,
            show_stderr=False,
        )


class VerifyTestStructure(JobBaseAction):
    def __init__(
        self,
        *,
        src_path: JobResolvableValue[str | PathLike],
        tests_path: JobResolvableValue[str | PathLike],
        errors: ValueRef[list[str]] | None = None,
    ) -> None:
        super().__init__()
        self.src_path: JobResolvableValue[str | PathLike] = src_path or ValueRef(name="src_path")
        self.tests_path: JobResolvableValue[str | PathLike] = tests_path or ValueRef(name="tests_path")
        self.errors: ValueRef[list[str]] = as_value_ref(errors, name="errors")

    def action(self, context: JobContext) -> None:
        resolved_value: str | PathLike | None = resolve_value(self.src_path, context=context)
        src_path: Path | None = as_path(resolved_value)
        tests_path: Path | None = as_path(resolve_value(self.tests_path, context=context))

        if src_path is None or not src_path.is_dir():
            raise JobException(f"src_path must be a directory: {src_path}")
        if tests_path is None or not tests_path.is_dir():
            raise JobException(f"tests_path must be a directory: {tests_path}")

        errors: list[str] = []
        # Iterate over source path, predict the name of the test file, and assert that it exists
        self._verify_directory(context, src_path, tests_path, src_path, errors)
        assign_value(self.errors, errors, context=context)
        if errors:
            raise JobException(f"Missing tests: {errors}")

    def _verify_directory(
        self, context: JobContext, src_path: Path, tests_path: Path, source_dir: Path, errors: list[str]
    ) -> None:
        child: Path
        for child in source_dir.iterdir():
            if self._skip(child):
                context.status.detail(f"Skipping {child}")
                continue

            if child.is_dir():
                self._verify_directory(context, src_path, tests_path, child, errors)
            else:
                expected_test_path: Path | None = self._expected_test_path(src_path, tests_path, child)
                if expected_test_path is None:  # pragma: no cover
                    context.status.detail(f"Skipping {child}")
                    continue

                context.status.start_item(str(child.relative_to(src_path)))
                error: str | None = "missing" if not expected_test_path.exists() else None
                context.status.finish_item(str(expected_test_path.relative_to(tests_path)), error=error)

                if error:
                    message: str = (
                        f"Test path for source path '{child.relative_to(src_path)}' not found: "
                        f"{expected_test_path.relative_to(tests_path)}"
                    )
                    errors.append(message)

    def _expected_test_path(self, src_path: Path, tests_path: Path, source_path: Path) -> Path | None:
        if source_path == src_path:
            return None
        test_name: str = self._test_name(source_path)
        parent_test_path: Path | None = self._expected_test_path(src_path, tests_path, source_path.parent)
        if parent_test_path:
            return parent_test_path / test_name
        return tests_path / test_name

    def _skip(self, source_path: Path) -> bool:
        if source_path.name.startswith("."):
            return True
        if source_path.name in ("__pycache__", "__main__.py"):
            return True
        if source_path.name.endswith(".egg-info"):
            return True
        return False

    def _test_name(self, source_path: Path) -> str:
        if source_path.name == "__init__.py":
            return f"test_{source_path.parent.name}.py"
        return f"test_{source_path.name}"
