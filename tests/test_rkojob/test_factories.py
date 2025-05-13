# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

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
