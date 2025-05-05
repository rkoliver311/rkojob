from rkojob import (
    JobActionScope,
    JobContext,
    JobException,
    JobGroupScope,
    JobScope,
    JobTeardownScope,
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

    def _run_scope(self, context: JobContext, scope: JobScope) -> None:
        # Run and then teardown a scope.
        # If the scope is a group, recursively run and teardown child scopes.

        group: JobGroupScope | None = scope if isinstance(scope, JobGroupScope) else None
        action: JobActionScope | None = scope if isinstance(scope, JobActionScope) else None
        teardown: JobTeardownScope | None = scope if isinstance(scope, JobTeardownScope) else None
        if not (group or action or teardown):
            raise self._unknown_scope(context, scope)

        with context.in_scope(scope):
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
                raise context.exception(e)

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
                self._run_teardown(context, child_as_teardown)

    def _run_teardown(self, context: JobContext, teardown: JobTeardownScope) -> None:
        # Teardown a scope.
        if teardown.teardown:
            try:
                teardown.teardown(context)
            except Exception:
                # do not raise
                pass

    def _unknown_scope(self, context: JobContext, scope: JobScope) -> Exception:
        return JobException(f"Unknown scope type: {scope.type}")
