import sys

from rkojob import JobContext, JobRunner


class JobContextFactory:
    @classmethod
    def create(cls, *args, **kwargs) -> JobContext:
        from rkojob.context import JobContextImpl
        from rkojob.writer import JobStatusWriter

        status_writer: JobStatusWriter = kwargs.get("status_writer") or JobStatusWriter(
            stream=sys.stdout,
            show_detail=False,
        )
        return JobContextImpl(values=kwargs.get("values"), status_writer=status_writer)


class JobRunnerFactory:
    @classmethod
    def create(cls, *args, **kwargs) -> JobRunner:
        from rkojob.runner import JobRunnerImpl

        return JobRunnerImpl()
