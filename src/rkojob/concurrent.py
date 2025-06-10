from concurrent.futures import Executor, Future, ThreadPoolExecutor
from threading import Event
from typing import Callable, Generic, ParamSpec, TypeVar

from rkojob import (
    JobContext,
    JobFuture,
    JobFutures,
    JobInterrupt,
)

R = TypeVar("R")
P = ParamSpec("P")


class JobFutureImpl(Generic[R], JobFuture[R]):
    def __init__(self, context: JobContext, future: Future[R]) -> None:
        self._context: JobContext = context
        self._future: Future[R] = future

    @property
    def context(self) -> JobContext:
        return self._context

    @property
    def done(self) -> bool:
        return self._future.done()

    @property
    def running(self) -> bool:
        return self._future.running()

    def result(self, timeout: float | None = None) -> R:
        return self._future.result(timeout=timeout)

    @property
    def future(self) -> Future[R]:
        return self._future


class JobFuturesImpl(JobFutures):
    """
    Convenience class wrapping an Executor.
    """

    def __init__(self, prefix: str = "") -> None:
        self._executor: Executor = ThreadPoolExecutor(thread_name_prefix=prefix)
        self._futures: list[JobFuture] = []

    def submit(self, context: JobContext, task: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> JobFuture[R]:
        future: Future[R] = self._executor.submit(task, *args, **kwargs)
        job_future: JobFutureImpl[R] = JobFutureImpl(context, future)
        self._futures.append(job_future)
        return job_future

    @property
    def futures(self) -> list[JobFuture[R]]:
        return self._futures

    def shutdown(self) -> None:
        self._executor.shutdown()

    def create_interrupt(self) -> JobInterrupt:
        return JobInterruptImpl()


class JobInterruptImpl:
    def __init__(self) -> None:
        self._event: Event = Event()

    def is_set(self) -> bool:
        return self._event.is_set()

    def set(self) -> None:
        self._event.set()

    def clear(self) -> None:
        self._event.clear()

    def wait(self, timeout: float | None = None) -> bool:
        return self._event.wait(timeout=timeout)
