from unittest import TestCase

from rkojob.context import JobContextImpl
from rkojob.factories import JobContextFactory, JobRunnerFactory
from rkojob.runner import JobRunnerImpl


class TestJobContextFactory(TestCase):
    def test(self):
        self.assertIsInstance(JobContextFactory.create(), JobContextImpl)


class TestJobRunnerFactory(TestCase):
    def test(self):
        self.assertIsInstance(JobRunnerFactory.create(), JobRunnerImpl)
