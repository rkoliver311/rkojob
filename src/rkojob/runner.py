# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from typing import Any, cast

import yaml

from rkojob import (
    JobActionScope,
    JobConditionalScope,
    JobConditionalType,
    JobConditionalValueType,
    JobContext,
    JobException,
    JobFuture,
    JobFutures,
    JobGroupScope,
    JobInterrupt,
    JobScope,
    JobScopeID,
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
        self._check_for_errors(context)

    def _check_for_errors(self, context: JobContext):
        report: dict[JobScopeID, Any] = context.get_report()

        if self._has_errors(report):
            errors = self._gather_errors(report)
            report_str: str = yaml.dump(errors)
            raise JobException(report_str)

    def _has_errors(self, report: dict[JobScopeID, Any]) -> bool:
        for scope in report:
            if report[scope].get("errors"):
                return True
            if self._has_errors(report[scope].get("scopes")):
                return True
        return False

    def _gather_errors(self, report: dict[JobScopeID, Any]) -> dict[str, Any] | None:
        if not self._has_errors(report):
            return None
        errors: dict[str, Any] = {}
        for scope in report:
            scope_str: str = str(scope)
            scope_report = report[scope]

            scope_errors: list[str | Exception] = scope_report.get("errors")
            if scope_errors:
                errors[scope_str] = {"errors": [str(error) for error in scope_errors]}

            child_errors: dict[str, Any] | None = self._gather_errors(scope_report.get("scopes", {}))
            if child_errors:
                if scope_str not in errors:
                    errors[scope_str] = {}
                errors[scope_str].update(**child_errors)
        return errors

    def _run_scope(self, context: JobContext, scope: JobScope) -> None:
        # Run and then teardown a scope.
        # If the scope is a group, recursively run and teardown child scopes.

        should_skip: bool
        skip_reason: str
        should_skip, skip_reason = self._should_skip(context, scope)
        if should_skip:
            context.events.skip_scope(scope, reason=skip_reason or None)
            return

        if scope.concurrent:
            # The scope will be run concurrently and will be joined
            # during the teardown of the current (i.e. parent) scope.
            self._run_concurrent_scope(context, scope)
        else:
            self._real_run_scope(context, scope)

    def _run_concurrent_scope(self, context: JobContext, scope: JobScope) -> None:
        futures: JobFutures = context.get_futures(context.scope)

        interrupt: JobInterrupt = futures.create_interrupt()
        forked_context: JobContext = context.fork(interrupt=interrupt)
        context.events.fork_context(forked_context)

        futures.submit(forked_context, self._real_run_scope, forked_context, scope)

    def _join_concurrent_scope(self, context: JobContext, future: JobFuture[None]) -> None:
        forked_context: JobContext = future.context
        try:
            # Request concurrent scopes to stop
            interrupt: JobInterrupt | None = forked_context.get_interrupt()
            if interrupt:
                interrupt.set()
            future.result()
        except Exception as e:  # pragma: no cover
            forked_context.events.error(e)
            raise
        finally:
            forked_context.join()
            context.events.join_context(forked_context)

    def _join_concurrent_scopes(self, context: JobContext, scope: JobScope) -> None:
        futures: JobFutures = context.get_futures(scope)
        for future in futures.futures:
            self._join_concurrent_scope(context, future)

    def _real_run_scope(self, context: JobContext, scope: JobScope) -> None:
        group: JobGroupScope | None = scope if isinstance(scope, JobGroupScope) else None
        action: JobActionScope | None = scope if isinstance(scope, JobActionScope) else None
        teardown: JobTeardownScope | None = scope if isinstance(scope, JobTeardownScope) else None
        if not (group or action or teardown):
            raise self._unknown_scope(context, scope)

        with context.events.scope(scope):
            try:
                if group:
                    self._run_group(context, group)
                elif action:
                    self._run_action(context, action)
            finally:
                if group:
                    self._join_concurrent_scopes(context, group)
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
                context.events.error(e)

    def _run_teardown(self, context: JobContext, teardown: JobTeardownScope) -> None:
        all_teardowns: Delegate[[JobContext], None] = Delegate(continue_on_error=True)
        all_teardowns += context.get_teardown(teardown)
        all_teardowns += teardown.teardown
        if all_teardowns:
            with context.events.scope_teardown(teardown):
                results: list[Any] = all_teardowns(context)
                for result in deep_flatten(results):
                    if isinstance(result, Exception):
                        context.events.warning(result)
        else:
            context.events.detail(f"Skipping Teardown {teardown}")

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
