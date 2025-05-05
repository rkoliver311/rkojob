import shlex
from typing import Any

from rkojob import (
    JobContext,
    assign_value,
    unassign_value,
)
from rkojob.job import JobBaseAction
from rkojob.util import Shell, ShellException, ShellResult
from rkojob.values import (
    ValueRef,
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
        shell: Shell = Shell(**self._kwargs)
        command: str = shlex.join(self._args)

        result: ShellResult | None = None
        try:
            context.status.start_item(f"Executing {command}")
            result = shell(*self._args)
            context.status.finish_item()
        except ShellException as e:
            result = e.result
            if self._raise_on_error:
                # To avoid double-reporting the error, record only the non-zero return code before raising the error
                context.status.finish_item(f"return_code={result.return_code}")
                raise
            else:
                # Record the error since we will not raise it.
                context.status.finish_item(error=e)
        finally:
            if result:
                assign_value(self.result, result)
                if result.stdout:
                    context.status.output(result.stdout, label="stdout")
                if result.stderr:
                    context.status.output(result.stderr, label="stderr")
            else:
                unassign_value(self.result)
