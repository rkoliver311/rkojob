# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.
import time
from enum import Enum, auto
from threading import Event
from types import SimpleNamespace
from unittest import TestCase

from rkojob import (
    JobAction,
    JobCallable,
    JobContext,
    JobException,
    JobIdType,
    JobInterrupt,
    ValueKey,
    ValueRef,
    create_scope_id,
    job_succeeding,
    scope_failing,
    scope_succeeding,
)
from rkojob.delegates import Delegate
from rkojob.factories import JobContextFactory
from rkojob.job import JobScopeIDMixin
from rkojob.runner import JobRunnerImpl
from rkojob.util import not_none


class StubScopeID(JobScopeIDMixin):
    def __init__(self, id: JobIdType | None = None) -> None:
        self._id = id or create_scope_id()


class StubScope:
    def __init__(self, name, type, teardown=None, id=None, concurrent=False):
        self.name = name
        self.type = type
        self.teardown = Delegate[[JobContext], None](continue_on_error=True)
        if teardown:
            self.teardown += teardown
        self.id = id or create_scope_id()
        self.concurrent = concurrent

    def __str__(self):
        return f"{self.type} {self.name}"


class StubGroupScope(StubScope):
    def __init__(self, name, type, scopes, teardown=None, id=None, concurrent=False):
        super().__init__(name, type, teardown, id, concurrent)
        self.scopes = scopes


class StubActionScope(StubScope):
    def __init__(self, name, type, action=None, teardown=None, run_if=None, skip_if=None, id=None, concurrent=False):
        super().__init__(name, type, teardown, id, concurrent)
        self.action = action
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
        job.scopes[0].teardown += lambda context: side_effects.append(f"Teardown {job.scopes[0].name} 1")
        job.scopes[0].teardown += lambda context: side_effects.append(f"Teardown {job.scopes[0].name} 2")
        job.teardown += lambda context: side_effects.append("Teardown job 1")
        job.teardown += lambda context: side_effects.append("Teardown job 2")

        JobRunnerImpl().run(JobContextFactory.create(), job)

        self.assertEqual(
            [
                "Action: job->stage1->step1.1",
                "Action: job->stage1->step1.2",
                "Teardown stage1 1",
                "Teardown stage1 2",
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
                "Teardown job 1",
                "Teardown job 2",
            ],
            side_effects,
        )

    def test_negative(self):
        side_effects = []

        job = self._create_job(side_effects)
        job.scopes[0].scopes[1].action = self._action(side_effects, fail=True)
        # This teardown should not run because the action never runs
        job.scopes[1].scopes[1].action = self._action(
            side_effects,
            root_teardown=self._teardown(job.scopes[1].scopes[1].name, side_effects, fail=True),
        )
        # This teardown should run
        job.teardown += self._teardown("job", side_effects)

        with self.assertRaises(Exception):
            JobRunnerImpl().run(JobContextFactory.create(), job)

        self.assertEqual(
            ["Action: job->stage1->step1.1", "Teardown job: step1.1", "Teardown job: job"],
            side_effects,
        )

    def test_bad_scope(self):
        with self.assertRaises(JobException) as e:
            JobRunnerImpl().run(JobContextFactory.create(), SimpleNamespace(type="scope-type", concurrent=False))
        self.assertEqual("Unknown scope type: scope-type", str(e.exception))

    def test_action_method_as_teardown(self) -> None:
        class SomeAction(JobAction):
            def __init__(self, side_effects: list[str]) -> None:
                self._side_effects: list[str] = side_effects

            def action(self, context: JobContext) -> None:
                self._side_effects.append("Action!")
                context.add_teardown(not_none(context.get_scope(generation=1)), self._clean_up)

            def _clean_up(self, context: JobContext) -> None:
                self._side_effects.append(f"Teardown {context.scope}!")

        side_effects: list[str] = []
        scope = StubActionScope("scope", StubScopeType.STEP, action=SomeAction(side_effects))
        parent = StubGroupScope("parent", StubScopeType.STAGE, scopes=[scope])

        context: JobContext = JobContextFactory.create()
        sut = JobRunnerImpl()
        sut.run(context, parent)
        self.assertEqual(["Action!", f"Teardown {parent}!"], side_effects)

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
                            action=self._action(side_effects),
                        ),
                        StubActionScope(
                            name="action-1-2",
                            type=StubScopeType.STEP,
                            action=self._action(
                                side_effects, parent_teardown=self._teardown("action-1-2", side_effects)
                            ),
                        ),
                        StubGroupScope(
                            name="group-1-2",
                            type=StubScopeType.STAGE,
                            scopes=[
                                StubActionScope(
                                    name="action-1-2-1",
                                    type=StubScopeType.STEP,
                                    action=self._action(side_effects),
                                ),
                                StubActionScope(
                                    name="action-1-2-2",
                                    type=StubScopeType.STEP,
                                    action=self._action(side_effects),
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
                            action=self._action(side_effects),
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
                "Action: root->group-1->action-1-1",
                "Action: root->group-1->action-1-2",
                "Action: root->group-1->group-1-2->action-1-2-1",
                "Action: root->group-1->group-1-2->action-1-2-2",
                "Teardown group-1: action-1-2",
                "Action: root->group-2->action-2-1",
                "Teardown action-2-2 from action-2-2!",
            ],
            side_effects,
        )

    @staticmethod
    def _action(
        side_effects: list[str],
        fail: bool = False,
        teardown: JobCallable[None] | None = None,
        root_teardown: JobCallable[None] | None = None,
        parent_teardown: JobCallable[None] | None = None,
    ) -> JobCallable[None]:
        def wrapped(context: JobContext) -> None:
            if teardown:
                context.add_teardown(context.scope, teardown)
            if parent_teardown:
                context.add_teardown(not_none(context.get_scope(generation=1), name="Parent scope"), parent_teardown)
            if root_teardown:
                context.add_teardown(not_none(context.get_scope(generation=-1), name="Root scope"), root_teardown)

            if fail:
                raise Exception(f"Action failed: {'->'.join([scope.name for scope in context.scopes])}")
            side_effects.append(f"Action: {'->'.join([scope.name for scope in context.scopes])}")

        return wrapped

    @staticmethod
    def _teardown(name: str, side_effects: list[str], fail: bool = False) -> JobCallable[None]:
        def wrapped(context: JobContext) -> None:
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
                            action=self._action(side_effects, root_teardown=self._teardown("step1.1", side_effects)),
                        ),
                        StubActionScope(
                            name="step1.2",
                            type=StubScopeType.STEP,
                            action=self._action(side_effects, root_teardown=self._teardown("step1.2", side_effects)),
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
                            action=self._action(side_effects, parent_teardown=self._teardown("step2.1", side_effects)),
                        ),
                        StubActionScope(
                            name="step2.2",
                            type=StubScopeType.STEP,
                            action=self._action(
                                side_effects,
                                parent_teardown=self._teardown("step2.2", side_effects),
                            ),
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
                            action=self._action(side_effects, root_teardown=self._teardown("step3.1", side_effects)),
                        ),
                        StubActionScope(
                            name="step3.2",
                            type=StubScopeType.STEP,
                            action=self._action(side_effects, root_teardown=self._teardown("step3.2", side_effects)),
                        ),
                    ],
                ),
            ],
        )

        return job

    def test_run_if_scope_failing(self) -> None:
        side_effects: list[str] = []

        job = self._create_job(side_effects)
        job.scopes[0].scopes[1].run_if = scope_failing(job.scopes[0])
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
                "Teardown job: step1.1",
            ],
            side_effects,
        )

        side_effects.clear()
        job.scopes[0].scopes[0].action = self._action(side_effects, fail=True)

        with self.assertRaises(Exception):
            JobRunnerImpl().run(JobContextFactory.create(), job)

        self.assertEqual(
            [
                "Action: job->stage1->step1.2",
                "Teardown job: step1.2",
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
        with self.assertRaises(Exception):
            JobRunnerImpl().run(JobContextFactory.create(), job)

        self.assertEqual(
            [
                "Action: job->stage1->step1.1",
                "Teardown job: step1.1",
            ],
            side_effects,
        )

    def test_skip_if_fail_teardown(self) -> None:
        side_effects: list[str] = []
        job = self._create_job(side_effects)
        job.scopes[1].scopes[1].action = self._action(
            side_effects, parent_teardown=self._teardown(job.scopes[1].scopes[1].name, side_effects, fail=True)
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
        job.scopes[1].scopes[0].skip_if = scope_succeeding(job.scopes[0])
        with self.assertRaises(Exception):
            JobRunnerImpl().run(JobContextFactory.create(), job)

        self.assertEqual(
            [
                "Action: job->stage1->step1.1",
                "Action: job->stage2->step2.1",
                "Teardown stage2: step2.1",
                "Teardown job: step1.1",
            ],
            side_effects,
        )

    def test_skip_if_success(self) -> None:
        context: JobContext = JobContextFactory.create()
        sut = JobRunnerImpl()
        step = StubActionScope("step", 3, skip_if=job_succeeding)
        self.assertEqual((True, "Job is succeeding."), sut._should_skip(context, step))

    def test_skip_if_property(self) -> None:
        context: JobContext = JobContextFactory.create()
        sut = JobRunnerImpl()
        step = StubActionScope("step", 3, skip_if=ValueRef((True, "Skip me")))
        self.assertEqual((True, "Skip me"), sut._should_skip(context, step))

    def test_skip_if_value(self) -> None:
        context: JobContext = JobContextFactory.create()
        sut = JobRunnerImpl()
        step = StubActionScope("step", 3, skip_if=True)
        self.assertEqual((True, ""), sut._should_skip(context, step))

    def test_concurrent(self) -> None:
        side_effects_key = ValueKey[list[str]]("side_effects")
        side_effects_event_key = ValueKey[Event]("side_effects_event")

        def foreground_action(context: JobContext):
            context.values.get(side_effects_key).append("Hello from the foreground!")
            context.values.get(side_effects_event_key).set()

        def background_action(context: JobContext):
            context.values.get(side_effects_event_key).wait()
            context.values.get(side_effects_key).append("Hello from the background!")

        def failing_background_action(context: JobContext):
            context.values.get(side_effects_event_key).wait()
            raise JobException("Boom!")

        job = StubGroupScope(
            "job",
            StubScopeType.JOB,
            scopes=[
                StubActionScope("background_step", StubScopeType.STEP, action=background_action, concurrent=True),
                StubGroupScope(
                    "stage",
                    StubScopeType.STAGE,
                    scopes=[
                        StubActionScope(
                            "failing_background_step",
                            StubScopeType.STEP,
                            action=failing_background_action,
                            concurrent=True,
                        ),
                        StubActionScope("step", StubScopeType.STEP, action=foreground_action),
                    ],
                ),
            ],
        )

        side_effects: list[str] = []
        side_effects_event: Event = Event()
        context = JobContextFactory.create(
            values=dict(side_effects=side_effects, side_effects_event=side_effects_event)
        )

        sut = JobRunnerImpl()
        with self.assertRaises(JobException):
            sut.run(context, job)

        self.assertEqual(["Hello from the foreground!", "Hello from the background!"], side_effects)

    def test_concurrent_with_error(self) -> None:
        side_effects_key = ValueKey[list[str]]("side_effects")
        side_effects_event_key = ValueKey[Event]("side_effects_event")

        def background_action(context: JobContext):
            # Demonstrate avoid deadlock when event never set
            if context.values.get(side_effects_event_key).wait(timeout=0.1):
                context.values.get(side_effects_key).append("Hello from the background!")

        def failing_action(_context: JobContext):
            raise JobException("Boom!")

        def foreground_action(context: JobContext):
            context.values.get(side_effects_key).append("Hello from the foreground!")
            context.values.get(side_effects_event_key).set()

        job = StubGroupScope(
            "job",
            StubScopeType.JOB,
            scopes=[
                StubGroupScope(
                    "stage",
                    StubScopeType.STAGE,
                    scopes=[
                        StubActionScope(
                            "background_step", StubScopeType.STEP, action=background_action, concurrent=True
                        ),
                        StubActionScope(
                            "failing_action",
                            StubScopeType.STEP,
                            action=failing_action,
                        ),
                        StubActionScope("step", StubScopeType.STEP, action=foreground_action),
                    ],
                ),
            ],
        )

        side_effects: list[str] = []
        side_effects_event: Event = Event()
        context = JobContextFactory.create(
            values=dict(side_effects=side_effects, side_effects_event=side_effects_event)
        )

        sut = JobRunnerImpl()
        with self.assertRaises(JobException):
            sut.run(context, job)

        self.assertEqual([], side_effects)

    def test_concurrent_interrupt(self) -> None:
        side_effects_key = ValueKey[list[str]]("side_effects")

        def background_action(context: JobContext):
            interrupt: JobInterrupt = not_none(context.get_interrupt())

            for _ in range(10):
                if interrupt.is_set():
                    break
                context.values.get(side_effects_key).append("Hello from the background!")
                time.sleep(0.1)

        def foreground_action(context: JobContext):
            context.values.get(side_effects_key).append("Hello from the foreground!")

        job = StubGroupScope(
            "job",
            StubScopeType.JOB,
            scopes=[
                StubActionScope(
                    "background_step",
                    StubScopeType.STEP,
                    action=background_action,
                    concurrent=True,
                    id="background_step",
                ),
                StubGroupScope(
                    "stage",
                    StubScopeType.STAGE,
                    scopes=[
                        StubActionScope("step", StubScopeType.STEP, action=foreground_action),
                    ],
                ),
            ],
        )

        side_effects: list[str] = []

        context = JobContextFactory.create(values=dict(side_effects=side_effects))

        sut = JobRunnerImpl()
        sut.run(context, job)

        self.assertEqual(["Hello from the background!", "Hello from the foreground!"], side_effects)
