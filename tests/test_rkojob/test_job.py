# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from unittest import TestCase
from unittest.mock import MagicMock

from rkojob import (
    JobAction,
    JobContext,
    JobException,
    ValueRef,
    scope_failing,
)
from rkojob.factories import JobContextFactory
from rkojob.job import (
    Job,
    JobBuilder,
    JobScopeIDMixin,
    JobStage,
    JobStageBuilder,
    JobStep,
    JobStepBuilder,
)


class FooAction(JobAction):
    def __init__(self, side_effects: list[str] | None = None, foo: str | None = None) -> None:
        super().__init__()
        if side_effects is None:
            side_effects = []
        self.side_effects: list[str] = side_effects
        self.foo = foo

    def action(self, context: JobContext) -> None:
        self.side_effects.append("action")


class TestJobScopeIDMixin(TestCase):
    def test_eq_hash(self) -> None:
        class Foo(JobScopeIDMixin):
            def __init__(self, data, id):
                self.data = data
                self._id = id

        class Bar(JobScopeIDMixin):
            def __init__(self, num, id):
                self.num = num
                self._id = id

        class Baz:
            def __init__(self, num, id):
                self.num = num
                self._id = id

        foo = Foo({"some": "data"}, "123")
        bar = Bar(456, "123")
        self.assertEqual(foo, bar)
        self.assertEqual(hash(foo), hash(bar))

        baz = Baz(456, "123")
        self.assertNotEqual(bar, baz)
        self.assertNotEqual(hash(bar), hash(baz))


class BarAction(JobAction):
    def __init__(self, arg1: str, arg2: int, arg3: float = 1.0, arg4: bool = False) -> None:
        super().__init__()
        self.arg1 = arg1
        self.arg2 = arg2
        self.arg3 = arg3
        self.arg4 = arg4

    def action(self, context: JobContext) -> None:
        pass


class TestJobStep(TestCase):
    def test_id(self):
        self.assertEqual("scope_id", JobStep("name", id="scope_id").id)
        self.assertIsNotNone(JobStep("name", id=None).id)

    def test_name(self):
        self.assertEqual("name", JobStep("name").name)

    def test_action(self):
        mock_action = MagicMock()
        self.assertIs(mock_action, JobStep("name", action=mock_action).action)

    def test_teardown(self):
        sut = JobStep("name")
        mock_teardown = MagicMock()
        mock_context = MagicMock()
        sut.teardown += mock_teardown
        sut.teardown(mock_context)
        mock_teardown.assert_called_once_with(mock_context)

    def test_action_instance(self):
        action = FooAction()
        sut = JobStep[FooAction]("name", action=action)
        self.assertIs(action, sut.action)

    def test_action_instance_2(self):
        action = FooAction()
        sut = JobStep[FooAction]("name")
        sut.action = action
        self.assertEqual(action, sut.action)

    def test_skip_if(self) -> None:
        skip_if = ValueRef(True)
        sut: JobStep = JobStep("name", skip_if=skip_if)
        self.assertIs(skip_if, sut.skip_if)

        sut.skip_if = (False, "Don't skip.")
        self.assertEqual((False, "Don't skip."), sut.skip_if)

    def test_run_if(self) -> None:
        run_if = ValueRef((True, "Always run."))
        sut: JobStep = JobStep("name", run_if=run_if)
        self.assertIs(run_if, sut.run_if)

        sut.run_if = ValueRef((False, "Don't run."))
        self.assertEqual((False, "Don't run."), sut.run_if.get())

    def test_str(self) -> None:
        self.assertEqual("Step name", str(JobStep("name")))


class TestJobStage(TestCase):
    def test(self):
        sut = JobStage(name="stage", steps=[JobStep(name="step1"), JobStep(name="step2")])
        self.assertEqual("stage", sut.name)
        self.assertIs(sut.scopes, sut.steps)
        self.assertEqual(2, len(sut.steps))
        self.assertEqual("step1", sut.steps[0].name)
        self.assertEqual("step2", sut.steps[1].name)

    def test_id(self):
        self.assertEqual("scope_id", JobStage("name", id="scope_id").id)
        self.assertIsNotNone(JobStage("name", id=None).id)

    def test_str(self) -> None:
        self.assertEqual("Stage name", str(JobStage("name")))


class TestJob(TestCase):
    def test(self):
        sut = Job(name="job", stages=[JobStage(name="stage1"), JobStage(name="stage2")])
        self.assertEqual("job", sut.name)
        self.assertIs(sut.scopes, sut.stages)
        self.assertEqual(2, len(sut.stages))
        self.assertEqual("stage1", sut.stages[0].name)
        self.assertEqual("stage2", sut.stages[1].name)

    def test_no_stages(self):
        sut = Job(name="job")
        self.assertEqual("job", sut.name)
        self.assertEqual([], sut.stages)

    def test_id(self):
        self.assertEqual("scope_id", Job("name", id="scope_id").id)
        self.assertIsNotNone(Job("name", id=None).id)

    def test_str(self) -> None:
        self.assertEqual("Job name", str(Job("name")))


class TestJobStepBuilder(TestCase):
    def test(self):
        mock_action = MagicMock()
        mock_teardown1 = MagicMock()
        mock_teardown2 = MagicMock()
        mock_run_if = MagicMock()
        mock_skip_if = MagicMock()

        sut = JobStepBuilder("step")
        sut.action = mock_action
        sut.teardown += mock_teardown1
        sut.teardown += mock_teardown2
        sut.run_if = mock_run_if
        sut.skip_if = mock_skip_if

        step = sut.build()
        self.assertEqual("step", step.name)
        self.assertIs(sut.action, step.action)
        self.assertIn(mock_teardown1, step.teardown)
        self.assertIn(mock_teardown2, step.teardown)
        self.assertIs(sut.run_if, step.run_if)
        self.assertIs(sut.skip_if, step.skip_if)
        self.assertEqual(sut.id, step.id)

    def test_builder_as_scope_id(self) -> None:
        context: JobContext = JobContextFactory.create()
        sut = JobStepBuilder("step")
        condition = scope_failing(sut)
        scope = sut.build()
        with context.in_scope(scope), context.status.scope(scope):
            context.error("boom")
        self.assertEqual((True, "Step step has failures."), condition(context))

    def test_str(self) -> None:
        self.assertEqual(str(JobStep("name")), str(JobStepBuilder("name")))


class TestJobStageBuilder(TestCase):
    def test(self):
        mock_action1 = MagicMock()
        mock_action2 = MagicMock()
        mock_action3 = MagicMock()
        mock_teardown1 = MagicMock()
        mock_teardown2 = MagicMock()
        sut = JobStageBuilder("stage")
        with sut.step("step1") as step1:
            step1.action = mock_action1
        with sut.step("step2") as step2:
            step2.action = mock_action2
        with sut.step("step3") as step3:
            step3.action = mock_action3
        sut.teardown += mock_teardown1
        sut.teardown += mock_teardown2
        stage = sut.build()
        self.assertEqual("stage", stage.name)
        self.assertEqual(sut.id, stage.id)
        self.assertIn(mock_teardown1, stage.teardown)
        self.assertIn(mock_teardown2, stage.teardown)
        self.assertEqual("step1", stage.steps[0].name)
        self.assertIs(mock_action1, stage.steps[0].action)
        self.assertEqual("step2", stage.steps[1].name)
        self.assertIs(mock_action2, stage.steps[1].action)
        self.assertEqual("step3", stage.steps[2].name)
        self.assertIs(mock_action3, stage.steps[2].action)

    def test_str(self) -> None:
        self.assertEqual(str(JobStage("name")), str(JobStageBuilder("name")))


class TestJobBuilder(TestCase):
    def test(self):
        mock_action1_1 = MagicMock()
        mock_action2_1 = MagicMock()
        mock_action3_1 = MagicMock()
        mock_teardown1 = MagicMock()
        mock_teardown2 = MagicMock()

        with JobBuilder("job") as sut:
            with sut.stage("stage1") as stage1:
                with stage1.step("step1.1") as step1_1:
                    step1_1.action = mock_action1_1
            with sut.stage("stage2") as stage2:
                with stage2.step("step2.1") as step2_1:
                    step2_1.action = mock_action2_1
            with sut.stage("stage3") as stage3:
                with stage3.step("step3.1") as step3_1:
                    step3_1.action = mock_action3_1
        sut.teardown += mock_teardown1
        sut.teardown += mock_teardown2

        job = sut.build()
        self.assertEqual("job", job.name)
        self.assertEqual(sut.id, job.id)
        self.assertIn(mock_teardown1, job.teardown)
        self.assertIn(mock_teardown2, job.teardown)

        self.assertEqual("stage1", job.stages[0].name)
        self.assertEqual("step1.1", job.stages[0].steps[0].name)
        self.assertIs(mock_action1_1, job.stages[0].steps[0].action)

        self.assertEqual("stage2", job.stages[1].name)
        self.assertEqual("step2.1", job.stages[1].steps[0].name)
        self.assertIs(mock_action2_1, job.stages[1].steps[0].action)

        self.assertEqual("stage3", job.stages[2].name)
        self.assertEqual("step3.1", job.stages[2].steps[0].name)
        self.assertIs(mock_action3_1, job.stages[2].steps[0].action)

    def test_negative(self):
        with JobBuilder("job") as sut:
            with sut.stage("stage1") as stage1:
                try:
                    with stage1.step("step1.1"):
                        # Step will not be added to the stage
                        raise JobException()
                except JobException:
                    pass
                with stage1.step("step1.2"):
                    pass
        job = sut.build()
        self.assertEqual("step1.2", job.stages[0].steps[0].name)

    def test_str(self) -> None:
        self.assertEqual(str(Job("name")), str(JobBuilder("name")))
