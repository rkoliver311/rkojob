from unittest import TestCase

from rkojob.context import JobContextImpl
from rkojob.factories import JobContextFactory


class TestJobContextFactory(TestCase):
    def test(self):
        self.assertIsInstance(JobContextFactory.create(), JobContextImpl)
