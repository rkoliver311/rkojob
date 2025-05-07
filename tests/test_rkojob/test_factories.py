from unittest import TestCase

from rkojob.context import JobContextImpl
from rkojob.factories import JobContextFactory, JobRunnerFactory
from rkojob.runner import JobRunnerImpl


class TestJobContextFactory(TestCase):
    def test(self):
        self.assertIsInstance(JobContextFactory.create(), JobContextImpl)

    def test_values(self):
        context = JobContextFactory.create(values={"key": "value"})
        self.assertEqual("value", context.values.get("key"))


class TestJobRunnerFactory(TestCase):
    def test(self):
        self.assertIsInstance(JobRunnerFactory.create(), JobRunnerImpl)
