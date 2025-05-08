from unittest import TestCase
from unittest.mock import MagicMock

from rkojob import (
    JobContext,
    JobException,
    ValueKey,
    ValueRef,
    Values,
)
from rkojob.factories import JobContextFactory
from rkojob.job import (
    Job,
    JobBaseAction,
    JobBuilder,
    JobScopes,
    JobStage,
    JobStageBuilder,
    JobStep,
    lazy_action,
)


class FooAction(JobBaseAction):
    def __init__(self, side_effects: list[str] | None = None, foo: str | None = None) -> None:
        super().__init__()
        if side_effects is None:
            side_effects = []
        self.side_effects: list[str] = side_effects
        self.foo = foo

    def action(self, context: JobContext) -> None:
        self.side_effects.append("action")

    def teardown_step(self, context: JobContext) -> None:
        self.side_effects.append("teardown_step")

    def teardown_stage(self, context: JobContext) -> None:
        self.side_effects.append("teardown_stage")

    def teardown_job(self, context: JobContext) -> None:
        self.side_effects.append("teardown_job")


class TestJobBaseAction(TestCase):
    def test_call(self):
        sut = FooAction()
        # Use __call__
        sut(MagicMock())
        self.assertEqual(["action"], sut.side_effects)

    def test_action(self):
        sut = FooAction()
        sut.action(MagicMock())
        self.assertEqual(["action"], sut.side_effects)

    def test_teardown(self):
        sut = FooAction()
        sut.teardown(MagicMock(scope=MagicMock(type=JobScopes.STEP)))
        sut.teardown(MagicMock(scope=MagicMock(type=JobScopes.STAGE)))
        sut.teardown(MagicMock(scope=MagicMock(type=JobScopes.JOB)))
        self.assertEqual(["teardown_step", "teardown_stage", "teardown_job"], sut.side_effects)

    def test_teardown_negative(self):
        sut = FooAction()
        unknown_scope = MagicMock()
        context = JobContextFactory.create()
        with context.in_scope(unknown_scope):
            with self.assertRaises(JobException) as e:
                sut.teardown(context)
        self.assertEqual(f"Unknown scope type: {unknown_scope.type}", str(e.exception))

    def test_teardown_step(self):
        sut = FooAction()
        sut.teardown_step(MagicMock())
        self.assertEqual(["teardown_step"], sut.side_effects)

    def test_teardown_stage(self):
        sut = FooAction()
        sut.teardown_stage(MagicMock())
        self.assertEqual(["teardown_stage"], sut.side_effects)

    def test_teardown_job(self):
        sut = FooAction()
        sut.teardown_job(MagicMock())
        self.assertEqual(["teardown_job"], sut.side_effects)


class BarAction(JobBaseAction):
    def __init__(self, arg1: str, arg2: int, arg3: float = 1.0, arg4: bool = False) -> None:
        super().__init__()
        self.arg1 = arg1
        self.arg2 = arg2
        self.arg3 = arg3
        self.arg4 = arg4


class TestJobStep(TestCase):
    def test_name(self):
        self.assertEqual("name", JobStep("name").name)

    def test_action(self):
        mock_action = MagicMock()
        self.assertIs(mock_action, JobStep("name", action=mock_action).action)

    def test_teardown(self):
        mock_teardown = MagicMock()
        self.assertIs(mock_teardown, JobStep("name", teardown=mock_teardown).teardown)

    def test_action_instance(self):
        action = FooAction()
        sut = JobStep[FooAction]("name", action=action)
        self.assertIs(action, sut.action)
        self.assertEqual(action.teardown, sut.teardown)

    def test_action_instance_2(self):
        action = FooAction()
        sut = JobStep[FooAction]("name")
        sut.action = action
        self.assertEqual(action, sut.action)
        self.assertEqual(action.teardown, sut.teardown)

    def test_action_instance_negative(self):
        with self.assertRaises(ValueError) as e:
            _ = JobStep("step", action=FooAction(), teardown=MagicMock())
        self.assertEqual("Cannot specify teardown when action is JobAction", str(e.exception))

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

    def test_str(self) -> None:
        self.assertEqual("Job name", str(Job("name")))


class TestJobStageBuilder(TestCase):
    def test(self):
        mock_action1 = MagicMock()
        mock_action2 = MagicMock()
        mock_action3 = MagicMock()

        sut = JobStageBuilder("stage")
        with sut.step("step1") as step1:
            step1.action = mock_action1
        with sut.step("step2") as step2:
            step2.action = mock_action2
        with sut.step("step3") as step3:
            step3.action = mock_action3
        stage = sut.build()
        self.assertEqual("stage", stage.name)
        self.assertEqual("step1", stage.steps[0].name)
        self.assertIs(mock_action1, stage.steps[0].action)
        self.assertEqual("step2", stage.steps[1].name)
        self.assertIs(mock_action2, stage.steps[1].action)
        self.assertEqual("step3", stage.steps[2].name)
        self.assertIs(mock_action3, stage.steps[2].action)


class TestJobBuilder(TestCase):
    def test(self):
        mock_action1_1 = MagicMock()
        mock_action2_1 = MagicMock()
        mock_action3_1 = MagicMock()

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
        job = sut.build()
        self.assertEqual("job", job.name)

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


class TestDeferredInit(TestCase):
    def test(self) -> None:
        class StubScope:
            def __init__(self, name, type):
                self.name = name
                self.type = type

        sut = lazy_action(FooAction, ["foo"], foo="foo")
        action_instance = sut._get_action_instance(MagicMock())  # type: ignore[attr-defined]
        self.assertEqual(["foo"], action_instance.side_effects)
        self.assertEqual("foo", action_instance.foo)
        sut.action(MagicMock())  # type: ignore[attr-defined]
        self.assertEqual(["foo", "action"], action_instance.side_effects)
        sut.teardown(MagicMock(scope=StubScope("scope", JobScopes.JOB)))  # type: ignore[attr-defined]
        self.assertEqual(["foo", "action", "teardown_job"], action_instance.side_effects)

    def test_values_key(self) -> None:
        class StubScope:
            def __init__(self, name, type):
                self.name = name
                self.type = type

        values: Values = Values()
        values.set("foo_key", ["foo"])
        values.set("bar_key", "bar")
        mock_context = MagicMock(values=values)

        sut = lazy_action(FooAction, ValueKey[str]("foo_key"), foo=ValueKey[str]("bar_key"))
        action_instance = sut._get_action_instance(mock_context)  # type: ignore[attr-defined]
        self.assertEqual(["foo"], action_instance.side_effects)
        self.assertEqual("bar", action_instance.foo)
        sut.action(MagicMock())  # type: ignore[attr-defined]
        self.assertEqual(["foo", "action"], action_instance.side_effects)
        sut.teardown(MagicMock(scope=StubScope("scope", JobScopes.JOB)))  # type: ignore[attr-defined]
        self.assertEqual(["foo", "action", "teardown_job"], action_instance.side_effects)
