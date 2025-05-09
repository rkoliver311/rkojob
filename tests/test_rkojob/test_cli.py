from __future__ import annotations

import tempfile
from argparse import Namespace
from pathlib import Path
from typing import Any
from unittest import TestCase

import yaml

from rkojob import JobException
from rkojob.cli import Cli


class TestCli(TestCase):
    def setUp(self) -> None:  # runs before each test
        self.sut = Cli()

    # --------------------------------------------------------------------- #
    # parse_args                                                             #
    # --------------------------------------------------------------------- #
    def test_parse_args_defaults(self) -> None:
        args = self.sut.parse_args(["run", "-m", "pkg.mod"])
        self.assertEqual(args.command, "run")
        self.assertEqual(args.job_module, "pkg.mod")
        self.assertEqual(args.job_name, "job")  # default
        self.assertEqual(args.values, [])  # default
        self.assertIsNone(args.values_from)

    def test_parse_args_all_options(self) -> None:
        argv = [
            "run",
            "--job-module",
            "some.module",
            "--job-name",
            "my_job",
            "-v",
            "a=1",
            "-v",
            "b=two",
            "--values-from",
            "vals.yml",
        ]
        args = self.sut.parse_args(argv)
        self.assertEqual(
            (args.command, args.job_module, args.job_name, args.values, args.values_from),
            ("run", "some.module", "my_job", ["a=1", "b=two"], "vals.yml"),
        )

    def test_error_and_success(self) -> None:
        self.assertEqual(self.sut.error("boom"), 1)
        self.assertEqual(self.sut.success(), 0)

    def _write_yaml(self, content: Any) -> Path:
        path = Path(tempfile.mkstemp(suffix=".yml")[1])
        path.write_text(yaml.safe_dump(content), encoding="utf-8")
        return path

    def test_load_values_from_file_success(self) -> None:
        path = self._write_yaml({"x": 1, "y": "two"})
        self.assertEqual(self.sut.load_values_from_file(str(path)), {"x": 1, "y": "two"})

    def test_load_values_from_file_root_not_mapping(self) -> None:
        path = self._write_yaml(["not", "a", "dict"])
        with self.assertRaises(ValueError):
            self.sut.load_values_from_file(str(path))

    def test_load_values_from_file_non_string_key(self) -> None:
        path = self._write_yaml({1: "bad"})
        with self.assertRaises(ValueError):
            self.sut.load_values_from_file(str(path))

    def test_read_values_precedence_and_merge(self) -> None:
        file_path = self._write_yaml({"a": 1, "b": 2})
        args = Namespace(values_from=str(file_path), values=["a=override", "c=3"])
        merged = self.sut.read_values(args)
        self.assertEqual(merged, {"a": "override", "b": 2, "c": "3"})

    def test_read_values_missing_file(self) -> None:
        args = Namespace(values_from="no_such_file.yml", values=[])
        with self.assertRaises(JobException):
            self.sut.read_values(args)
