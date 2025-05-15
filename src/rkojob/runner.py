# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from typing import Any, cast

from rkojob import (
    JobActionScope,
    JobConditionalScope,
    JobConditionalType,
    JobConditionalValueType,
    JobContext,
    JobException,
    JobGroupScope,
    JobScope,
    JobTeardownScope,
    job_failing,
    job_never,
    resolve_value,
)
from rkojob.delegates import Delegate
from rkojob.util import deep_flatten


class JobRunnerImpl:
    """
    Runner for job scopes.
    """

    def run(self, context: JobContext, scope: JobScope) -> None:
        """
        Runs a job scope
        :param context: The current context.
        :param scope: The scope to run.
        """
        self._run_scope(context, scope)
        errors: list[Exception] = context.get_errors()
        if errors:
            raise JobException("\n".join([str(e) for e in errors]))

    def _run_scope(self, context: JobContext, scope: JobScope) -> None:
        # Run and then teardown a scope.
        # If the scope is a group, recursively run and teardown child scopes.

        group: JobGroupScope | None = scope if isinstance(scope, JobGroupScope) else None
        action: JobActionScope | None = scope if isinstance(scope, JobActionScope) else None
        teardown: JobTeardownScope | None = scope if isinstance(scope, JobTeardownScope) else None
        if not (group or action or teardown):
            raise self._unknown_scope(context, scope)

        should_skip: bool
        skip_reason: str
        should_skip, skip_reason = self._should_skip(context, scope)
        if should_skip:
            context.status.skip_scope(scope, reason=skip_reason or None)
            return

        with context.in_scope(scope), context.status.scope(scope):
            try:
                if group:
                    self._run_group(context, group)
                elif action:
                    self._run_action(context, action)
            finally:
                if teardown:
                    self._run_teardown(context, teardown)

    def _run_group(self, context: JobContext, group: JobGroupScope) -> None:
        # Recursively run a group's child scopes
        for child in group.scopes:
            self._run_scope(context, child)

    def _run_action(self, context: JobContext, action: JobActionScope) -> None:
        # Run a scope's action
        if action.action:
            try:
                action.action(context)
            except Exception as e:
                # Add error to current scope's list of errors
                context.status.error(e)

    def _run_teardown(self, context: JobContext, teardown: JobTeardownScope) -> None:
        all_teardowns: Delegate[[JobContext], None] = Delegate(continue_on_error=True)
        all_teardowns += context.get_teardown(teardown)
        all_teardowns += teardown.teardown
        if all_teardowns:
            with context.status.section(f"Teardown {teardown}"):
                results: list[Any] = all_teardowns(context)
                for result in deep_flatten(results):
                    if isinstance(result, Exception):
                        context.status.warning(result)
        else:
            context.status.detail(f"Skipping Teardown {teardown}")

    def _should_skip(self, context: JobContext, scope: JobScope) -> tuple[bool, str]:
        if isinstance(scope, JobConditionalScope):
            run_if: JobConditionalType | None = scope.run_if
            skip_if: JobConditionalType | None = scope.skip_if

            if skip_if is None and run_if is None:
                # No condition specified; Use the default.
                return self._resolve_conditional(context, job_failing)
            if run_if is None:
                assert skip_if is not None
                # No run condition. Check only the skip condition.
                return self._resolve_conditional(context, skip_if)

            assert run_if is not None

            could_run: bool
            reason: str
            could_run, reason = self._resolve_conditional(context, run_if)

            if not could_run or skip_if is None:
                # The scope should not run or there is no additional condition to consider.
                # Use the run condition.
                return not could_run, reason

            # Scope could run but may still be skipped.
            return self._resolve_conditional(context, skip_if)

        # If it is not a conditional scope, never skip.
        return self._resolve_conditional(context, job_never)

    def _resolve_conditional(self, context: JobContext, conditional: JobConditionalType) -> tuple[bool, str]:
        value: JobConditionalValueType | None = cast(
            JobConditionalValueType, resolve_value(conditional, context=context)
        )
        if isinstance(value, tuple):
            return value
        return bool(value), ""

    def _unknown_scope(self, context: JobContext, scope: JobScope) -> Exception:
        return JobException(f"Unknown scope type: {scope.type}")
