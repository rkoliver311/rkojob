from unittest import TestCase

from rkojob import JobException


class TestJobException(TestCase):
    def test_can_raise(self) -> None:
        try:
            raise JobException("error")
        except JobException as e:
            self.assertEqual("error", str(e))
