import importlib
import sys
from argparse import ArgumentParser, Namespace
from types import ModuleType

from rkojob.factories import JobContextFactory, JobRunnerFactory
from rkojob.job import Job


def parse_args(argv: list[str]) -> Namespace:
    parser: ArgumentParser = ArgumentParser()
    parser.add_argument(
        "--job-module", "-m", type=str, required=True, help="The module to import the job definition from."
    )
    parser.add_argument(
        "--job-name",
        "-j",
        type=str,
        required=False,
        default="job",
        help="The name of the job definition to import from job_module.",
    )
    parser.add_argument(
        "--value",
        "-v",
        action="append",
        dest="values",
        default=[],
        help="A key=value pair to add to the context's values.",
    )

    return parser.parse_args(argv)


def main() -> int:  # pragma: no cover
    args = parse_args(sys.argv[1:])
    job_module: ModuleType = importlib.import_module(args.job_module)
    job: Job = getattr(job_module, args.job_name)
    values: dict[str, str] = {key: value for key, value in [value.split("=", maxsplit=1) for value in args.values]}

    try:
        JobRunnerFactory.create().run(JobContextFactory.create(values=values), job)
        return 0
    except Exception:
        return 1
