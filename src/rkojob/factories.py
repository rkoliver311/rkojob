from rkojob import JobContext, JobRunner


class JobContextFactory:
    @classmethod
    def create(cls, *args, **kwargs) -> JobContext:
        from rkojob.context import JobContextImpl

        return JobContextImpl()


class JobRunnerFactory:
    @classmethod
    def create(cls, *args, **kwargs) -> JobRunner:
        from rkojob.runner import JobRunnerImpl

        return JobRunnerImpl()
