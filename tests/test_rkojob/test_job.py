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
    JobGroup,
    JobGroupBuilder,
    JobScopeIDMixin,
    JobStage,
    JobStageBuilder,
    JobStageGroupBuilder,
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

    def test_concurrent(self):
        self.assertTrue(JobStep("name", concurrent=True).concurrent)

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


class TestJobGroup(TestCase):
    def test(self):
        sut = JobGroup(name="group", scopes=[JobGroup(name="group1"), JobStep(name="step1"), JobStage(name="stage1")])
        self.assertEqual("group", sut.name)
        self.assertEqual(3, len(sut.scopes))
        self.assertEqual("group1", sut.scopes[0].name)
        self.assertEqual("step1", sut.scopes[1].name)
        self.assertEqual("stage1", sut.scopes[2].name)

    def test_id(self):
        self.assertEqual("scope_id", JobGroup("name", id="scope_id").id)
        self.assertIsNotNone(JobGroup("name", id=None).id)

    def test_concurrent(self):
        self.assertTrue(JobGroup("name", concurrent=True).concurrent)

    def test_str(self) -> None:
        self.assertEqual("Group name", str(JobGroup("name")))


class TestJobStage(TestCase):
    def test(self):
        sut = JobStage(name="stage", scopes=[JobGroup(name="group1"), JobStep(name="step1"), JobStep(name="step2")])
        self.assertEqual("stage", sut.name)
        self.assertEqual(3, len(sut.scopes))
        self.assertEqual("group1", sut.scopes[0].name)
        self.assertEqual("step1", sut.scopes[1].name)
        self.assertEqual("step2", sut.scopes[2].name)

    def test_id(self):
        self.assertEqual("scope_id", JobStage("name", id="scope_id").id)
        self.assertIsNotNone(JobStage("name", id=None).id)

    def test_concurrent(self):
        self.assertTrue(JobStage("name", concurrent=True).concurrent)

    def test_str(self) -> None:
        self.assertEqual("Stage name", str(JobStage("name")))


class TestJob(TestCase):
    def test(self):
        sut = Job(
            name="job",
            scopes=[
                JobGroup(name="group1"),
                JobStep(name="job_step"),
                JobStage(name="stage1"),
                JobStage(name="stage2"),
            ],
        )
        self.assertEqual("job", sut.name)
        self.assertEqual(4, len(sut.scopes))
        self.assertEqual("group1", sut.scopes[0].name)
        self.assertEqual("job_step", sut.scopes[1].name)
        self.assertEqual("stage1", sut.scopes[2].name)
        self.assertEqual("stage2", sut.scopes[3].name)
        self.assertFalse(sut.concurrent)

    def test_no_scopes(self):
        sut = Job(name="job")
        self.assertEqual("job", sut.name)
        self.assertEqual([], sut.scopes)

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

        sut = JobStepBuilder("step", concurrent=True)
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
        self.assertEqual(sut.concurrent, step.concurrent)
        self.assertEqual(sut.id, step.id)

    def test_builder_as_scope_id(self) -> None:
        context: JobContext = JobContextFactory.create()
        sut = JobStepBuilder("step")
        condition = scope_failing(sut)
        scope = sut.build()
        with context.events.scope(scope):
            context.error("boom")
        self.assertEqual((True, "Step step has failures."), condition(context))

    def test_str(self) -> None:
        self.assertEqual(str(JobStep("name")), str(JobStepBuilder("name")))


class TestJobGroupBuilder(TestCase):
    def test_concurrent(self) -> None:
        sut = JobGroupBuilder("group", concurrent=True)
        self.assertTrue(sut.concurrent)

    def test_group(self) -> None:
        with JobGroupBuilder("group").group("sub-group") as sub_group:
            self.assertIsInstance(sub_group, JobGroupBuilder)

    def test_step(self) -> None:
        with JobGroupBuilder("group").step("step") as step:
            self.assertIsInstance(step, JobStepBuilder)

    def test_stage(self) -> None:
        with JobGroupBuilder("group").stage("stage") as stage:
            self.assertIsInstance(stage, JobStageBuilder)

    def test_str(self) -> None:
        self.assertEqual(str(JobGroupBuilder("name")), str(JobGroup("name")))

    def test_add_scope(self) -> None:
        with JobStepBuilder("step1.1") as step_builder:
            step_builder.action = MagicMock()
        step = step_builder.build()

        with JobGroupBuilder("stage1") as sut:
            sut.add_scope(step)
        stage = sut.build()
        self.assertIs(step, stage.scopes[0])


class TestJobStageGroupBuilder(TestCase):
    def test_concurrent(self) -> None:
        sut = JobStageGroupBuilder("group", concurrent=True)
        self.assertTrue(sut.concurrent)

    def test_group(self) -> None:
        with JobStageGroupBuilder("group").group("sub-group") as sub_group:
            self.assertIsInstance(sub_group, JobStageGroupBuilder)

    def test_step(self) -> None:
        with JobStageGroupBuilder("group").step("step") as step:
            self.assertIsInstance(step, JobStepBuilder)

    def test_str(self) -> None:
        self.assertEqual(str(JobStageGroupBuilder("name")), str(JobGroup("name")))

    def test_add_scope(self) -> None:
        with JobStepBuilder("step1.1") as step_builder:
            step_builder.action = MagicMock()
        step = step_builder.build()

        with JobStageGroupBuilder("stage1") as sut:
            sut.add_scope(step)
        stage = sut.build()
        self.assertIs(step, stage.scopes[0])


class TestJobStageBuilder(TestCase):
    def test(self):
        mock_action1 = MagicMock()
        mock_action2 = MagicMock()
        mock_action3 = MagicMock()
        mock_teardown1 = MagicMock()
        mock_teardown2 = MagicMock()
        sut = JobStageBuilder("stage", concurrent=True)
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
        self.assertEqual(sut.concurrent, stage.concurrent)
        self.assertIn(mock_teardown1, stage.teardown)
        self.assertIn(mock_teardown2, stage.teardown)
        self.assertEqual("step1", stage.scopes[0].name)
        self.assertIs(mock_action1, stage.scopes[0].action)
        self.assertEqual("step2", stage.scopes[1].name)
        self.assertIs(mock_action2, stage.scopes[1].action)
        self.assertEqual("step3", stage.scopes[2].name)
        self.assertIs(mock_action3, stage.scopes[2].action)

    def test_str(self) -> None:
        self.assertEqual(str(JobStage("name")), str(JobStageBuilder("name")))

    def test_add_scope(self) -> None:
        with JobStepBuilder("step1.1") as step_builder:
            step_builder.action = MagicMock()
        step = step_builder.build()

        with JobStageBuilder("stage1") as sut:
            sut.add_scope(step)
        stage = sut.build()
        self.assertIs(step, stage.scopes[0])


class TestJobBuilder(TestCase):
    def test(self):
        mock_job_action = MagicMock()
        mock_action1_1 = MagicMock()
        mock_action2_1 = MagicMock()
        mock_action3_1 = MagicMock()
        mock_action3_2 = MagicMock()
        mock_action3_3 = MagicMock()
        mock_teardown1 = MagicMock()
        mock_teardown2 = MagicMock()

        with JobBuilder("job") as sut:
            with sut.step("job_step") as job_step:
                job_step.action = mock_job_action
            with sut.group("group1") as group1:
                with group1.stage("stage1") as stage1:
                    with stage1.step("step1.1") as step1_1:
                        step1_1.action = mock_action1_1
                with group1.stage("stage2") as stage2:
                    with stage2.step("step2.1") as step2_1:
                        step2_1.action = mock_action2_1
            with sut.stage("stage3") as stage3:
                with stage3.step("step3.1") as step3_1:
                    step3_1.action = mock_action3_1
                with stage3.group("group3") as group3:
                    with group3.step("step3.2") as step3_2:
                        step3_2.action = mock_action3_2
                    with group3.group("group3.1") as group3_1:
                        with group3_1.step("step3.3") as step3_3:
                            step3_3.action = mock_action3_3

        sut.teardown += mock_teardown1
        sut.teardown += mock_teardown2

        job = sut.build()
        self.assertEqual("job", job.name)
        self.assertEqual(sut.id, job.id)
        self.assertIn(mock_teardown1, job.teardown)
        self.assertIn(mock_teardown2, job.teardown)

        self.assertEqual("job_step", job.scopes[0].name)

        self.assertEqual("group1", job.scopes[1].name)
        self.assertEqual("stage1", job.scopes[1].scopes[0].name)
        self.assertIs(mock_action1_1, job.scopes[1].scopes[0].scopes[0].action)

        self.assertEqual("stage2", job.scopes[1].scopes[1].name)
        self.assertIs(mock_action2_1, job.scopes[1].scopes[1].scopes[0].action)

        self.assertEqual("stage3", job.scopes[2].name)
        self.assertEqual("step3.1", job.scopes[2].scopes[0].name)
        self.assertIs(mock_action3_1, job.scopes[2].scopes[0].action)
        self.assertEqual("group3", job.scopes[2].scopes[1].name)
        self.assertEqual("step3.2", job.scopes[2].scopes[1].scopes[0].name)
        self.assertIs(mock_action3_2, job.scopes[2].scopes[1].scopes[0].action)
        self.assertEqual("group3.1", job.scopes[2].scopes[1].scopes[1].name)
        self.assertEqual("step3.3", job.scopes[2].scopes[1].scopes[1].scopes[0].name)
        self.assertIs(mock_action3_3, job.scopes[2].scopes[1].scopes[1].scopes[0].action)

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
        self.assertEqual("step1.2", job.scopes[0].scopes[0].name)

    def test_str(self) -> None:
        self.assertEqual(str(Job("name")), str(JobBuilder("name")))

    def test_add_scope(self) -> None:
        with JobStageBuilder("stage1") as stage_builder:
            with stage_builder.step("step1.1") as step:
                step.action = MagicMock()
            with stage_builder.step("step1.2") as step:
                step.action = MagicMock()
        stage = stage_builder.build()

        with JobBuilder("job") as sut:
            sut.add_scope(stage)
        job = sut.build()
        self.assertIs(stage, job.scopes[0])
