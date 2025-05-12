from typing import cast

from rkojob import (
    JobActionScope,
    JobConditionalScope,
    JobConditionalType,
    JobConditionalValueType,
    JobContext,
    JobException,
    JobGroupScope,
    JobScope,
    JobScopeStatus,
    JobTeardownScope,
    job_failing,
    job_never,
    resolve_value,
)


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
                if group:
                    self._run_group_teardown(context, group)
                elif teardown:
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

    def _run_group_teardown(
        self, context: JobContext, group: JobGroupScope, *, scope_to_teardown: JobScope | None = None
    ) -> None:
        # Run teardowns of a group's descendants on the give scope.
        if scope_to_teardown is None:
            # Self-teardown
            scope_to_teardown = group
        child: JobScope
        for child in reversed(group.scopes):
            child_as_group: JobGroupScope | None = child if isinstance(child, JobGroupScope) else None
            child_as_teardown: JobTeardownScope | None = child if isinstance(child, JobTeardownScope) else None
            if not (child_as_group or child_as_teardown):  # pragma: no cover
                continue
            if child_as_group:
                self._run_group_teardown(context, child_as_group, scope_to_teardown=scope_to_teardown)
            elif child_as_teardown:
                self._run_teardown(context, child_as_teardown, scope_to_teardown=scope_to_teardown)

    def _run_teardown(
        self, context: JobContext, teardown: JobTeardownScope, *, scope_to_teardown: JobScope | None = None
    ) -> None:
        if scope_to_teardown is None:
            scope_to_teardown = teardown

        # Do not run teardown if the scope was skipped or never run
        scope_status: JobScopeStatus = context.get_scope_status(teardown)
        if scope_status in (JobScopeStatus.UNKNOWN, JobScopeStatus.SKIPPED):
            context.status.detail(
                f"Skipping Teardown {scope_to_teardown.type} {scope_to_teardown.name} ({teardown.type} {teardown.name})"
            )
            return

        # Teardown a scope.
        if teardown.teardown:
            try:
                section: str = f"Teardown {scope_to_teardown.type} {scope_to_teardown.name}"
                if teardown is not scope_to_teardown:
                    section += f" ({teardown.type} {teardown.name})"
                context.status.start_section(section)
                teardown.teardown(context)
            except Exception as e:
                # Log but do not raise
                context.status.warning(e)
            finally:
                context.status.finish_section()

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
