# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from rkojob import JobContext, JobFutures, JobRunner


class JobContextFactory:
    @classmethod
    def create(cls, *args, **kwargs) -> JobContext:
        from rkojob.context import JobContextImpl

        return JobContextImpl(events=kwargs.get("events"), values=kwargs.get("values"))


class JobRunnerFactory:
    @classmethod
    def create(cls, *args, **kwargs) -> JobRunner:
        from rkojob.runner import JobRunnerImpl

        return JobRunnerImpl()


class JobFuturesFactory:
    @classmethod
    def create(cls, *args, **kwargs) -> JobFutures:
        from rkojob.concurrent import JobFuturesImpl

        return JobFuturesImpl()
