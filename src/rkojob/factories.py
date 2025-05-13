import os
import sys

from rkojob import JobContext, JobRunner


class JobContextFactory:
    @classmethod
    def create(cls, *args, **kwargs) -> JobContext:
        from rkojob.context import JobContextImpl, JobStatusWriter

        status_writer: JobStatusWriter = kwargs.get("status_writer") or JobStatusWriter(
            stream=sys.stdout, show_detail=False, collapsible_output=bool(os.getenv("GITHUB_ACTIONS"))
        )
        return JobContextImpl(values=kwargs.get("values"), status_writer=status_writer)


class JobRunnerFactory:
    @classmethod
    def create(cls, *args, **kwargs) -> JobRunner:
        from rkojob.runner import JobRunnerImpl

        return JobRunnerImpl()
