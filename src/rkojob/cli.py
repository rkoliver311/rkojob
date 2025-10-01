# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

import importlib
import os
import sys
from argparse import ArgumentParser, Namespace
from types import ModuleType
from typing import Any, Final

import yaml

from rkojob import JobEventDispatcher, JobException, JobHooks, JobScope
from rkojob.events import JobDirectEventDispatcher
from rkojob.factories import JobContextFactory, JobHooksFactory, JobRunnerFactory
from rkojob.writer import JobStatusWriter


class Cli:

    RUN_COMMAND: Final[str] = "run"

    JOB_ARGS: Final[tuple[str, ...]] = ("--job", "-j")
    VALUE_ARGS: Final[tuple[str, ...]] = ("--value", "-v")
    VALUES_FROM_ARGS: Final[tuple[str, ...]] = ("--values-from",)
    HOOKS_MODULE_ARGS: Final[tuple[str, ...]] = ("--hooks-module",)

    def main(self, argv: list[str]) -> int:  # pragma: no cover
        try:
            args = self.parse_args(argv)
            if args.command == self.RUN_COMMAND:
                return self.run_job(args)
            else:
                return self.error(f"Unknown command: {args.command}")
        except Exception as e:
            return self.error(e)

    def error(self, error: str | Exception) -> int:
        print(error, file=sys.stderr)
        return 1

    def success(self) -> int:
        return 0

    def get_parser(self) -> ArgumentParser:
        parser: ArgumentParser = ArgumentParser(prog="rkojob", description="Run and manage rkoJob definitions.")
        subparsers = parser.add_subparsers(dest="command", required=True)

        # run
        run_parser = subparsers.add_parser(self.RUN_COMMAND, help="Execute a job definition.")
        run_parser.add_argument(*self.JOB_ARGS, type=str, required=True, help="The name of the job definition to run.")
        run_parser.add_argument(*self.VALUE_ARGS, action="append", dest="values", default=[])
        run_parser.add_argument(
            *self.VALUES_FROM_ARGS,
            type=str,
            help="Path to a file containing key=value pairs to add to the context's values.",
        )
        run_parser.add_argument(
            *self.HOOKS_MODULE_ARGS, type=str, help="The name of the module that will register custom hooks."
        )

        return parser

    def parse_args(self, argv: list[str]) -> Namespace:
        parser = self.get_parser()
        return parser.parse_args(argv)

    def run_job(self, args: Namespace) -> int:  # pragma: no cover
        job: JobScope = self.get_job(args.job)
        values: dict[str, Any] = self.read_values(args)
        hooks: JobHooks = self.get_hooks(args.hooks_module)

        try:
            events: JobEventDispatcher = self.get_event_dispatcher()
            status_writer: JobStatusWriter = self.get_status_writer()
            events.add_handler(status_writer)

            context = JobContextFactory.create(events=events, values=values, hooks=hooks)
            JobRunnerFactory.create().run(context, job)
            return self.success()
        except Exception as e:
            return self.error(f"Error during job run: {e}")

    def get_event_dispatcher(self) -> JobEventDispatcher:
        return JobDirectEventDispatcher()

    def get_status_writer(self) -> JobStatusWriter:
        return JobStatusWriter(stream=sys.stdout, show_detail=False, collapsible_output=self.is_github_actions)

    @property
    def is_github_actions(self) -> bool:
        return bool(os.getenv("GITHUB_ACTIONS"))

    def read_values(self, args: Namespace) -> dict[str, Any]:
        values: dict[str, Any] = {}
        if args.values_from:
            try:
                values.update(self.load_values_from_file(args.values_from))
            except Exception as e:
                raise JobException(f"Error loading values from file: {e}") from e
        # CLI values win
        values.update({k: v for k, v in (pair.split("=", 1) for pair in args.values)})
        return values

    def load_values_from_file(self, path: str) -> dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            data: Any = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Expected a dictionary at the root of {path}, got {type(data).__name__}")

        result: dict[str, Any] = {}
        for k, v in data.items():
            if not isinstance(k, str):
                raise ValueError(f"Invalid key type: {k!r}")
            result[k] = v
        return result

    def get_module(self, name: str) -> ModuleType:  # pragma: no cover
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as e:
            raise ModuleNotFoundError(f"Module not found: {name}") from e

    def get_job(self, job_name: str) -> JobScope:  # pragma: no cover
        module_name: str
        module_name, job_name = self._split_module_and_job(job_name)
        job_module: ModuleType = self.get_module(module_name)
        job: JobScope = getattr(job_module, job_name)
        return job

    def _split_module_and_job(self, job_name: str) -> tuple[str, str]:
        module_and_job: list[str] = job_name.rsplit(".", maxsplit=1)
        if len(module_and_job) != 2:
            raise ValueError(f"Invalid job name: '{job_name}' (expecting <module_name>.<job_name>)")
        return module_and_job[0], module_and_job[1]

    def get_hooks(self, module_name: str | None) -> JobHooks:  # pragma: no cover
        hooks: JobHooks = JobHooksFactory.create()
        if module_name:
            hooks_module: ModuleType = self.get_module(module_name)
            if getattr(hooks_module, "register_hooks"):
                hooks_module.register_hooks(hooks)
        return hooks


def main() -> int:  # pragma: no cover
    return Cli().main(sys.argv[1:])
