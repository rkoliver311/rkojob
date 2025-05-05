#!/usr/bin/python3
import importlib
import sys
from argparse import ArgumentParser, Namespace
from types import ModuleType

from rkojob.factories import JobRunnerFactory, JobContextFactory
from rkojob.job import Job

if __name__ == "__main__":
    parser: ArgumentParser = ArgumentParser()
    parser.add_argument("--job-module", "-m", type=str, required=True, help="The module to import the job definition from.")
    parser.add_argument("--job-name", "-j", type=str, required=False, default="job", help="The name of the job definition to import from job_module.")
    parser.add_argument("--value", "-v", action="append", dest="values", default=[], help="A key=value pair to add to the context's values.")

    args: Namespace = parser.parse_args()

    job_module: ModuleType = importlib.import_module(args.job_module)
    job: Job = getattr(job_module, args.job_name)
    values: dict[str, str] = {key: value for key, value in [value.split("=", maxsplit=1) for value in args.values]}

    return_value: int = 0
    try:
        JobRunnerFactory.create().run(JobContextFactory.create(values=values), job)
    except Exception:
        return_value = 1
    sys.exit(return_value)
