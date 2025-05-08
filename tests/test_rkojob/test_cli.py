from unittest import TestCase

from rkojob import cli


class TestParseArgs(TestCase):
    def test(self) -> None:
        args = cli.parse_args(
            ["--job-module", "module", "--job-name", "name", "--value", "key1=value1", "--value", "key2=value2"]
        )
        self.assertEqual("module", args.job_module)
        self.assertEqual("name", args.job_name)
        self.assertEqual(["key1=value1", "key2=value2"], args.values)
