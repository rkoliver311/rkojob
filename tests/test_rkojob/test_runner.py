from enum import Enum, auto
from unittest import TestCase

from rkojob import (
    JobCallable,
    JobContext,
    JobException,
    JobScopeType,
    ValueRef,
    job_success,
    scope_fail,
    scope_success,
)
from rkojob.factories import JobContextFactory
from rkojob.runner import JobRunnerImpl


class StubGroupScope:
    def __init__(self, name, type, scopes):
        self.name = name
        self.type = type
        self.scopes = scopes


class StubActionScope:
    def __init__(self, name, type, action=None, teardown=None, run_if=None, skip_if=None):
        self.name = name
        self.type = type
        self.action = action
        self.teardown = teardown
        self.run_if = run_if
        self.skip_if = skip_if


class StubScopeType(Enum):
    JOB = auto()
    STAGE = auto()
    STEP = auto()


class TestJobRunnerImpl(TestCase):
    def test(self):
        side_effects = []

        job = self._create_job(side_effects)

        JobRunnerImpl().run(JobContextFactory.create(), job)

        self.assertEqual(
            [
                "Action: job->stage1->step1.1",
                "Action: job->stage1->step1.2",
                "Action: job->stage2->step2.1",
                "Action: job->stage2->step2.2",
                "Teardown stage2: step2.2",
                "Teardown stage2: step2.1",
                "Action: job->stage3->step3.1",
                "Action: job->stage3->step3.2",
                "Teardown job: step3.2",
                "Teardown job: step3.1",
                "Teardown job: step1.2",
                "Teardown job: step1.1",
            ],
            side_effects,
        )

    def test_negative(self):
        side_effects = []

        job = self._create_job(side_effects)
        job.scopes[0].scopes[1].action = self._action(side_effects, fail=True)
        job.scopes[2].scopes[1].teardown = self._teardown(
            job.scopes[1].scopes[1].name, side_effects, StubScopeType.JOB, fail=True
        )

        with self.assertRaises(Exception) as e:
            JobRunnerImpl().run(JobContextFactory.create(), job)
        self.assertEqual("Action failed: job->stage1->step1.2", str(e.exception))

        self.assertEqual(
            [
                "Action: job->stage1->step1.1",
                "Teardown stage2: step2.2",
                "Teardown stage2: step2.1",
                "Teardown job: step3.1",
                "Teardown job: step1.2",
                "Teardown job: step1.1",
            ],
            side_effects,
        )

    def test_bad_scope(self):
        class StubScope:
            def __init__(self, name, type):
                self.name = name
                self.type = type

        with self.assertRaises(JobException) as e:
            JobRunnerImpl().run(JobContextFactory.create(), StubScope("name", "scope-type"))
        self.assertEqual("Unknown scope type: scope-type", str(e.exception))

    def test_mix_of_parent_and_action(self):
        side_effects = []

        root = StubGroupScope(
            name="root",
            type=StubScopeType.JOB,
            scopes=[
                StubGroupScope(
                    name="group-1",
                    type=StubScopeType.STAGE,
                    scopes=[
                        StubActionScope(
                            name="action-1-1",
                            type=StubScopeType.STEP,
                            action=lambda context: side_effects.append(f"Hello from {context.scope.name}!"),
                        ),
                        StubActionScope(
                            name="action-1-2",
                            type=StubScopeType.STEP,
                            action=lambda context: side_effects.append(f"Hello from {context.scope.name}!"),
                            teardown=lambda context: (
                                side_effects.append(f"Teardown {context.scope.name} from action-1-2!")
                                if context.scope.type == StubScopeType.STAGE
                                else None
                            ),
                        ),
                        StubGroupScope(
                            name="group-1-2",
                            type=StubScopeType.STAGE,
                            scopes=[
                                StubActionScope(
                                    name="action-1-2-1",
                                    type=StubScopeType.STEP,
                                    action=lambda context: side_effects.append(f"Hello from {context.scope.name}!"),
                                    teardown=lambda _: None,
                                ),
                                StubActionScope(
                                    name="action-1-2-2",
                                    type=StubScopeType.STEP,
                                    action=lambda context: side_effects.append(f"Hello from {context.scope.name}!"),
                                ),
                            ],
                        ),
                    ],
                ),
                StubGroupScope(
                    name="group-2",
                    type=StubScopeType.STAGE,
                    scopes=[
                        StubActionScope(
                            name="action-2-1",
                            type=StubScopeType.STEP,
                            action=lambda context: side_effects.append(f"Hello from {context.scope.name}!"),
                        ),
                        StubActionScope(
                            name="action-2-2",
                            type=StubScopeType.STEP,
                            action=None,
                            teardown=lambda context: side_effects.append(
                                f"Teardown {context.scope.name} from action-2-2!"
                            ),
                        ),
                    ],
                ),
            ],
        )

        runner = JobRunnerImpl()
        context = JobContextFactory.create()
        runner.run(context, root)

        self.assertEqual(
            [
                "Hello from action-1-1!",
                "Hello from action-1-2!",
                "Hello from action-1-2-1!",
                "Hello from action-1-2-2!",
                "Teardown group-1 from action-1-2!",
                "Hello from action-2-1!",
                "Teardown action-2-2 from action-2-2!",
                "Teardown group-2 from action-2-2!",
                "Teardown root from action-2-2!",
            ],
            side_effects,
        )

    @staticmethod
    def _action(side_effects: list[str], fail: bool = False) -> JobCallable[None]:
        def wrapped(context: JobContext) -> None:
            if fail:
                raise Exception(f"Action failed: {'->'.join([scope.name for scope in context.scopes])}")
            side_effects.append(f"Action: {'->'.join([scope.name for scope in context.scopes])}")

        return wrapped

    @staticmethod
    def _teardown(
        name: str, side_effects: list[str], *scope_types: JobScopeType, fail: bool = False
    ) -> JobCallable[None]:
        def wrapped(context: JobContext) -> None:
            if context.scope.type in scope_types:
                if fail:
                    raise Exception(f"Teardown {context.scope.name} failed: {name}")
                side_effects.append(f"Teardown {context.scope.name}: {name}")

        return wrapped

    def _create_job(self, side_effects: list[str]) -> StubGroupScope:
        job = StubGroupScope(
            name="job",
            type=StubScopeType.JOB,
            scopes=[
                StubGroupScope(
                    name="stage1",
                    type=StubScopeType.STAGE,
                    scopes=[
                        StubActionScope(
                            name="step1.1",
                            type=StubScopeType.STEP,
                            action=self._action(side_effects),
                            teardown=self._teardown("step1.1", side_effects, StubScopeType.JOB),
                        ),
                        StubActionScope(
                            name="step1.2",
                            type=StubScopeType.STEP,
                            action=self._action(side_effects),
                            teardown=self._teardown("step1.2", side_effects, StubScopeType.JOB),
                        ),
                    ],
                ),
                StubGroupScope(
                    name="stage2",
                    type=StubScopeType.STAGE,
                    scopes=[
                        StubActionScope(
                            name="step2.1",
                            type=StubScopeType.STEP,
                            action=self._action(side_effects),
                            teardown=self._teardown("step2.1", side_effects, StubScopeType.STAGE),
                        ),
                        StubActionScope(
                            name="step2.2",
                            type=StubScopeType.STEP,
                            action=self._action(side_effects),
                            teardown=self._teardown("step2.2", side_effects, StubScopeType.STAGE),
                        ),
                    ],
                ),
                StubGroupScope(
                    name="stage3",
                    type=StubScopeType.STAGE,
                    scopes=[
                        StubActionScope(
                            name="step3.1",
                            type=StubScopeType.STEP,
                            action=self._action(side_effects),
                            teardown=self._teardown("step3.1", side_effects, StubScopeType.JOB),
                        ),
                        StubActionScope(
                            name="step3.2",
                            type=StubScopeType.STEP,
                            action=self._action(side_effects),
                            teardown=self._teardown("step3.2", side_effects, StubScopeType.JOB),
                        ),
                    ],
                ),
            ],
        )

        return job

    def test_run_if_scope_fail(self) -> None:
        side_effects: list[str] = []

        job = self._create_job(side_effects)
        job.scopes[0].scopes[1].run_if = scope_fail(job.scopes[0])
        JobRunnerImpl().run(JobContextFactory.create(), job)

        self.assertEqual(
            [
                "Action: job->stage1->step1.1",
                "Action: job->stage2->step2.1",
                "Action: job->stage2->step2.2",
                "Teardown stage2: step2.2",
                "Teardown stage2: step2.1",
                "Action: job->stage3->step3.1",
                "Action: job->stage3->step3.2",
                "Teardown job: step3.2",
                "Teardown job: step3.1",
                "Teardown job: step1.2",
                "Teardown job: step1.1",
            ],
            side_effects,
        )

        side_effects.clear()
        job.scopes[0].scopes[0].action = self._action(side_effects, fail=True)

        with self.assertRaises(Exception) as e:
            JobRunnerImpl().run(JobContextFactory.create(), job)
        self.assertEqual("Action failed: job->stage1->step1.1", str(e.exception))

        self.assertEqual(
            [
                "Action: job->stage1->step1.2",
                "Teardown stage2: step2.2",
                "Teardown stage2: step2.1",
                "Teardown job: step3.2",
                "Teardown job: step3.1",
                "Teardown job: step1.2",
                "Teardown job: step1.1",
            ],
            side_effects,
        )

    def test_run_if_property(self) -> None:
        side_effects: list[str] = []

        job = self._create_job(side_effects)
        job.scopes[0].scopes[1].run_if = ValueRef((False, "Don't run me."))
        JobRunnerImpl().run(JobContextFactory.create(), job)

        self.assertEqual(
            [
                "Action: job->stage1->step1.1",
                "Action: job->stage2->step2.1",
                "Action: job->stage2->step2.2",
                "Teardown stage2: step2.2",
                "Teardown stage2: step2.1",
                "Action: job->stage3->step3.1",
                "Action: job->stage3->step3.2",
                "Teardown job: step3.2",
                "Teardown job: step3.1",
                "Teardown job: step1.2",
                "Teardown job: step1.1",
            ],
            side_effects,
        )

    def test_could_run_but_skip(self) -> None:
        side_effects: list[str] = []
        job = self._create_job(side_effects)
        job.scopes[1].scopes[1].run_if = True
        job.scopes[1].scopes[1].skip_if = True
        JobRunnerImpl().run(JobContextFactory.create(), job)

        self.assertEqual(
            [
                "Action: job->stage1->step1.1",
                "Action: job->stage1->step1.2",
                "Action: job->stage2->step2.1",
                "Teardown stage2: step2.2",
                "Teardown stage2: step2.1",
                "Action: job->stage3->step3.1",
                "Action: job->stage3->step3.2",
                "Teardown job: step3.2",
                "Teardown job: step3.1",
                "Teardown job: step1.2",
                "Teardown job: step1.1",
            ],
            side_effects,
        )

    def test_skip_if_fail(self) -> None:
        side_effects: list[str] = []
        job = self._create_job(side_effects)
        job.scopes[0].scopes[1].action = self._action(side_effects, fail=True)
        with self.assertRaises(Exception) as e:
            JobRunnerImpl().run(JobContextFactory.create(), job)
        self.assertEqual("Action failed: job->stage1->step1.2", str(e.exception))

        self.assertEqual(
            [
                "Action: job->stage1->step1.1",
                "Teardown stage2: step2.2",
                "Teardown stage2: step2.1",
                "Teardown job: step3.2",
                "Teardown job: step3.1",
                "Teardown job: step1.2",
                "Teardown job: step1.1",
            ],
            side_effects,
        )

    def test_skip_if_fail_teardown(self) -> None:
        side_effects: list[str] = []
        job = self._create_job(side_effects)
        job.scopes[1].scopes[1].teardown = self._teardown(
            job.scopes[1].scopes[1].name, side_effects, StubScopeType.STAGE, fail=True
        )

        JobRunnerImpl().run(JobContextFactory.create(), job)

        self.assertEqual(
            [
                "Action: job->stage1->step1.1",
                "Action: job->stage1->step1.2",
                "Action: job->stage2->step2.1",
                "Action: job->stage2->step2.2",
                "Teardown stage2: step2.1",
                "Action: job->stage3->step3.1",
                "Action: job->stage3->step3.2",
                "Teardown job: step3.2",
                "Teardown job: step3.1",
                "Teardown job: step1.2",
                "Teardown job: step1.1",
            ],
            side_effects,
        )

    def test_skip_if_scope_success(self) -> None:
        side_effects: list[str] = []
        job = self._create_job(side_effects)
        job.scopes[0].scopes[1].action = self._action(side_effects, fail=True)
        job.scopes[1].scopes[0].skip_if = scope_success(job.scopes[0])
        with self.assertRaises(Exception) as e:
            JobRunnerImpl().run(JobContextFactory.create(), job)
        self.assertEqual("Action failed: job->stage1->step1.2", str(e.exception))

        self.assertEqual(
            [
                "Action: job->stage1->step1.1",
                "Action: job->stage2->step2.1",
                "Teardown stage2: step2.2",
                "Teardown stage2: step2.1",
                "Teardown job: step3.2",
                "Teardown job: step3.1",
                "Teardown job: step1.2",
                "Teardown job: step1.1",
            ],
            side_effects,
        )

    def test_skip_if_success(self) -> None:
        class StubScope:
            def __init__(self, name, type, run_if=None, skip_if=None):
                self.name = name
                self.type = type
                self.run_if = run_if
                self.skip_if = skip_if

        context: JobContext = JobContextFactory.create()
        sut = JobRunnerImpl()
        step = StubScope("step", 3, skip_if=job_success)
        self.assertEqual((True, "Job is succeeding."), sut._should_skip(context, step))

    def test_skip_if_property(self) -> None:
        class StubScope:
            def __init__(self, name, type, run_if=None, skip_if=None):
                self.name = name
                self.type = type
                self.run_if = run_if
                self.skip_if = skip_if

        context: JobContext = JobContextFactory.create()
        sut = JobRunnerImpl()
        step = StubScope("step", 3, skip_if=ValueRef((True, "Skip me")))
        self.assertEqual((True, "Skip me"), sut._should_skip(context, step))

    def test_skip_if_value(self) -> None:
        class StubScope:
            def __init__(self, name, type, run_if=None, skip_if=None):
                self.name = name
                self.type = type
                self.run_if = run_if
                self.skip_if = skip_if

        context: JobContext = JobContextFactory.create()
        sut = JobRunnerImpl()
        step = StubScope("step", 3, skip_if=True)
        self.assertEqual((True, ""), sut._should_skip(context, step))
