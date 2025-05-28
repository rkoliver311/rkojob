# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.
from enum import Enum, auto
from unittest import TestCase
from unittest.mock import MagicMock

from rkojob import (
    JobAction,
    JobCallable,
    JobContext,
    JobException,
    JobResolvableValue,
    JobScopeID,
    JobScopeStack,
    ValueKey,
    assign_value,
    context_value,
    create_scope_id,
    job_action,
    job_always,
    job_context,
    job_failing,
    job_never,
    job_scope,
    job_succeeding,
    lazy_action,
    lazy_format,
    resolve_map,
    resolve_value,
    resolve_values,
    scope_failing,
    scope_succeeding,
    unassign_value,
)
from rkojob.coerce import as_bool
from rkojob.factories import JobContextFactory
from rkojob.values import ComputedValue, NoValueError, ValueRef, Values


class TestJobException(TestCase):
    def test_can_raise(self) -> None:
        try:
            raise JobException("error")
        except JobException as e:
            self.assertEqual("error", str(e))


class TestCreateScopeId(TestCase):
    def test(self) -> None:
        self.assertEqual(36, len(create_scope_id()))
        self.assertNotEqual(create_scope_id(), create_scope_id())


class StubEventType(Enum):
    START_SCOPE = auto()
    FINISH_SCOPE = auto()


class StubEvent:
    def __init__(self, scope, type, data):
        self.scope = scope
        self.type = type
        self.data = data


class StubScope:
    def __init__(self, name, type, id=None):
        self.name = name
        self.type = type
        self.id = id or create_scope_id()


class TestJobScopeStack(TestCase):
    def test_get(self) -> None:
        scope1 = StubScope("scope1", "type")

        sut: JobScopeStack[JobScopeID, str] = JobScopeStack()
        self.assertIsNone(sut.get(scope1))

        sut.push(scope1, "scope1")
        self.assertEqual("scope1", sut[scope1])

    def test_get_scope(self) -> None:
        scope1 = StubScope("scope1", "type")

        sut: JobScopeStack[JobScopeID, str] = JobScopeStack()
        self.assertIsNone(sut.get_scope())

        sut.push(scope1, "scope1")
        self.assertEqual(scope1, sut.get_scope())

    def test_scope(self) -> None:
        sut: JobScopeStack[JobScopeID, str] = JobScopeStack()
        with self.assertRaises(JobException) as e:
            _ = sut.scope
        self.assertEqual("Scope stack underflow.", str(e.exception))

        with self.assertRaises(JobException) as e:
            _ = sut.value
        self.assertEqual("Scope stack underflow.", str(e.exception))

        scope1 = StubScope("scope1", "type")
        sut.push(scope1, "scope1")
        self.assertEqual(scope1, sut.scope)
        self.assertEqual("scope1", sut.value)

    def test_path_to(self) -> None:
        sut: JobScopeStack[JobScopeID, str] = JobScopeStack()
        scope1 = StubScope("scope1", "type")
        scope2 = StubScope("scope2", "type")
        scope3 = StubScope("scope3", "type")
        sut.push(scope1, "scope1")
        sut.push(scope2, "scope2")
        sut.push(scope3, "scope3")

        self.assertEqual((scope1,), sut.path_to(scope1))
        self.assertEqual((scope1, scope2), sut.path_to(scope2))
        self.assertEqual((scope1, scope2, scope3), sut.path_to(scope3))

    def test_push_pop_peek(self) -> None:
        sut: JobScopeStack[JobScopeID, str] = JobScopeStack()

        scope1 = StubScope("scope1", "type")
        scope2 = StubScope("scope2", "type")
        scope3 = StubScope("scope3", "type")
        sut.push(scope1, "scope1")
        sut.push(scope2, "scope2")
        sut.push(scope3, "scope3")

        self.assertEqual((scope3, "scope3"), sut.peek())
        self.assertEqual((scope3, "scope3"), sut.pop())

        self.assertEqual((scope2, "scope2"), sut.peek())
        self.assertEqual((scope2, "scope2"), sut.pop())

        self.assertEqual((scope1, "scope1"), sut.peek())
        self.assertEqual((scope1, "scope1"), sut.pop())

        with self.assertRaises(JobException) as e:
            _, _ = sut.peek()
        self.assertEqual("Scope stack underflow.", str(e.exception))

        with self.assertRaises(JobException) as e:
            _, _ = sut.pop()
        self.assertEqual("Scope stack underflow.", str(e.exception))

    def test_len(self) -> None:
        sut: JobScopeStack[JobScopeID, None] = JobScopeStack()
        scope1 = StubScope("scope1", "type")
        scope2 = StubScope("scope2", "type")
        scope3 = StubScope("scope3", "type")
        sut.push(scope1, None)
        sut.push(scope2, None)
        sut.push(scope3, None)
        self.assertEqual(3, len(sut))

    def test_items(self) -> None:
        sut: JobScopeStack[JobScopeID, None] = JobScopeStack()
        scope1 = StubScope("scope1", "type")
        scope2 = StubScope("scope2", "type")
        scope3 = StubScope("scope3", "type")
        sut.push(scope1, None)
        sut.push(scope2, None)
        sut.push(scope3, None)
        self.assertEqual(list({scope3: None, scope2: None, scope1: None}.items()), list(sut.items()))

    def test_iter(self) -> None:
        sut: JobScopeStack[JobScopeID, None] = JobScopeStack()
        self.assertEqual(list({}), list(sut))

        scope1 = StubScope("scope1", "type")
        scope2 = StubScope("scope2", "type")
        scope3 = StubScope("scope3", "type")
        sut.push(scope1, None)
        sut.push(scope2, None)
        sut.push(scope3, None)
        self.assertEqual(list({scope3: None, scope2: None, scope1: None}), list(sut))

    def test_bool(self) -> None:
        sut: JobScopeStack[JobScopeID, None] = JobScopeStack()
        self.assertFalse(bool(sut))

        sut.push(StubScope("name", "type"), None)
        self.assertTrue(bool(sut))

    def test_fork(self) -> None:
        sut: JobScopeStack[JobScopeID, None] = JobScopeStack()
        mock_scope_1 = MagicMock()
        mock_scope_2 = MagicMock()
        mock_scope_3 = MagicMock()

        sut.push(mock_scope_1)
        sut.push(mock_scope_2)

        fork = sut.fork()
        self.assertIs(sut._default_factory, fork._default_factory)
        self.assertTrue(fork.at_fork)

        fork.push(mock_scope_3)
        self.assertFalse(fork.at_fork)

        self.assertEqual([mock_scope_2, mock_scope_1], list(sut))
        self.assertEqual([mock_scope_3, mock_scope_2, mock_scope_1], list(fork))

        fork.pop()
        self.assertTrue(fork.at_fork)
        self.assertEqual(list(sut), list(fork))


class TestContextValue(TestCase):
    def test(self) -> None:
        mock_context = MagicMock(values=Values(key="value"))
        sut: JobResolvableValue[str] = context_value("key")
        self.assertEqual("value", resolve_value(sut, context=mock_context))

    def test_default(self) -> None:
        mock_context = MagicMock(values=Values())
        sut: JobResolvableValue[str] = context_value("key", default="default")
        self.assertEqual("default", resolve_value(sut, context=mock_context))
        self.assertEqual("default", mock_context.values.get("key"))

    def test_raise(self) -> None:
        mock_context = MagicMock(values=Values())
        sut: JobResolvableValue[str] = context_value("key")
        with self.assertRaises(NoValueError) as e:
            resolve_value(sut, context=mock_context, raise_no_value=True)
        self.assertEqual("No context value found for key 'key'", str(e.exception))

    def test_coerce(self) -> None:
        mock_context = MagicMock(values=Values(key="True"))
        sut: JobResolvableValue[bool] = context_value("key", coercer=as_bool)
        self.assertTrue(resolve_value(sut, context=mock_context))

    def test_callable(self) -> None:
        mock_context = MagicMock(values=Values(key="True"))
        sut: JobCallable[bool] = context_value("key", coercer=as_bool)
        self.assertTrue(sut(mock_context))

    def test_repr(self) -> None:
        self.assertEqual("context_value('key')", repr(context_value("key")))
        self.assertEqual("context_value('key', as_bool)", repr(context_value("key", as_bool)))

    def test_scopes(self) -> None:
        sut: JobResolvableValue[str] = context_value("key")

        mock_context = MagicMock()

        mock_context.scopes = (StubScope("job", 0),)
        mock_context.values = Values(**{"job.key": "job_value", "key": "value"})
        self.assertEqual("job_value", resolve_value(sut, context=mock_context))

        mock_context.scopes = (StubScope("job", 0), StubScope("stage", 1))
        self.assertEqual("job_value", resolve_value(sut, context=mock_context))

        mock_context.scopes = (StubScope("job", 0), StubScope("stage", 1), StubScope("step", 2))
        mock_context.values = Values(
            **{
                "job.key": "job_value",
                "job.stage.key": "stage_value",
                "job.stage.step.key": "step_value",
                "key": "value",
            }
        )
        self.assertEqual("step_value", resolve_value(sut, context=mock_context))

        sut = context_value("job.stage.key")
        self.assertEqual("stage_value", resolve_value(sut, context=mock_context))

    def test_scopes_raise(self) -> None:
        sut: JobResolvableValue[str] = context_value("key")

        mock_context = MagicMock()
        mock_context.scopes = (StubScope("job", 0), StubScope("stage", 1), StubScope("step", 2))
        mock_context.values = Values()
        with self.assertRaises(NoValueError) as e:
            resolve_value(sut, context=mock_context, raise_no_value=True)
        self.assertEqual(
            "No context value found for key 'key' "
            "(first tried: ['job.stage.step.key', 'job.stage.key', 'job.key']).",
            str(e.exception),
        )


class TestJobScope(TestCase):
    def test(self) -> None:
        mock_context = MagicMock()
        mock_scope = MagicMock()
        mock_context.get_scope.return_value = mock_scope
        sut = job_scope(mock_scope)
        self.assertIs(mock_scope, sut(mock_context))
        mock_context.get_scope.assert_called_once_with(mock_scope, generation=0)

        mock_context.get_scope.reset_mock()

        sut = job_scope(mock_scope, generation=1)
        self.assertIs(mock_scope, sut(mock_context))
        mock_context.get_scope.assert_called_once_with(mock_scope, generation=1)

    def test_repr(self) -> None:
        mock_scope = MagicMock()
        self.assertEqual(f"job_scope({mock_scope!r})", repr(job_scope(mock_scope)))


class TestResolveValue(TestCase):
    def test_callable(self) -> None:
        context: JobContext = JobContextFactory.create(values=dict(key="value"))
        self.assertEqual("value", resolve_value(lambda ctx: ctx.values.get_ref("key").value, context=context))

    def test_callable_no_context(self) -> None:
        self.assertEqual("default", resolve_value(lambda ctx: ctx.values.get_ref("foo").value, default="default"))

    def test_callable_no_context_raise(self) -> None:
        with self.assertRaises(NoValueError) as e:
            resolve_value(lambda ctx: ctx.values.get_ref("foo").value, default="default", raise_no_value=True)
        self.assertEqual("Unable to resolve value without context.", str(e.exception))

    def test_property(self) -> None:
        self.assertEqual("value", resolve_value(ValueRef("value")))

    def test_property_no_value(self) -> None:
        self.assertEqual("default", resolve_value(ValueRef(), default="default"))

    def test_property_key(self) -> None:
        context: JobContext = JobContextFactory.create(values=dict(key="value"))
        self.assertEqual("value", resolve_value(ValueKey("key"), context=context))

    def test_property_key_no_value(self) -> None:
        context: JobContext = JobContextFactory.create()
        self.assertEqual("default", resolve_value(ValueKey("key"), context=context, default="default"))

    def test_property_key_no_context(self) -> None:
        self.assertEqual("default", resolve_value(ValueKey("key"), default="default"))

    def test_property_key_no_context_raise(self) -> None:
        with self.assertRaises(NoValueError) as e:
            resolve_value(ValueKey("key"), default="default", raise_no_value=True)
        self.assertEqual("Unable to resolve value without context.", str(e.exception))

    def test_value(self) -> None:
        self.assertEqual("value", resolve_value("value"))


class TestAssignValue(TestCase):
    def test_property(self) -> None:
        assignable: ValueRef[str] = ValueRef()
        assign_value(assignable, "value")
        self.assertEqual("value", assignable.value)

    def test_key(self) -> None:
        context = MagicMock()
        assignable: ValueKey[str] = ValueKey("key")
        assign_value(assignable, "value", context=context)
        context.values.set.assert_called_with(assignable, "value")

    def test_key_no_context(self) -> None:
        with self.assertRaises(JobException) as e:
            assign_value(ValueKey("key"), "value")
        self.assertEqual("Unable to assign value to context value without a context!", str(e.exception))

    def test_non_assignable(self) -> None:
        with self.assertRaises(JobException) as e:
            assign_value("foo", "value")  # type: ignore[arg-type]
        self.assertEqual("Unable to assign value to foo", str(e.exception))


class TestResolveValues(TestCase):
    def test_no_context(self) -> None:
        self.assertEqual(["value1", 123], resolve_values([ValueRef("value1"), ValueRef(123)]))

    def test_with_context(self) -> None:
        self.assertEqual(
            ["value1", 123],
            resolve_values([ValueRef("value1"), ValueKey("int_key")], context=MagicMock(values=Values(int_key=123))),
        )


class TestResolveMap(TestCase):
    def test_no_context(self) -> None:
        self.assertEqual({"ref1": "value1", "int_prop": 123}, resolve_map(ref1=ValueRef("value1"), int_prop=123))

    def test_with_context(self) -> None:
        self.assertEqual(
            {"ref1": "value1", "ref2": 123},
            resolve_map(
                ref1=ValueRef("value1"), ref2=ValueKey("int_key"), context=MagicMock(values=Values(int_key=123))
            ),
        )


class TestLazyFormat(TestCase):
    def test(self) -> None:
        ref1 = ValueRef("value1")
        ref2 = ValueRef("value2")
        sut = lazy_format("{ref1}, {ref2}", ref1=ref1, ref2=ref2)
        self.assertEqual("value1, value2", resolve_value(sut, context=MagicMock()))

    def test_with_context(self) -> None:
        ref2 = ValueRef("value2")
        sut = lazy_format("{ref.1}, {ref2}", ref2=ref2)
        values: Values = Values()
        values.set("ref.1", "value1")
        self.assertEqual("value1, value2", resolve_value(sut, context=MagicMock(values=values)))

    def test_missing_key(self) -> None:
        ref2 = ValueRef("value2")
        sut = lazy_format("{ref1}, {ref2}", ref2=ref2)
        with self.assertRaises(NoValueError) as e:
            _ = resolve_value(sut, context=MagicMock(values=Values()), raise_no_value=True)
        self.assertEqual("No context value found for key 'ref1'", str(e.exception))

    def test_repr(self) -> None:
        self.assertEqual("lazy_format('{ref1}, {ref2}')", repr(lazy_format("{ref1}, {ref2}")))
        self.assertEqual(
            "lazy_format('{ref1}, {ref2}', ref1='value1', ref2=ValueRef(value=value2))",
            repr(lazy_format("{ref1}, {ref2}", ref1="value1", ref2=ValueRef("value2"))),
        )


class TestUnassignValue(TestCase):
    def test_property(self) -> None:
        assignable: ValueRef[str] = ValueRef("value")
        unassign_value(assignable)
        self.assertFalse(assignable.has_value)

    def test_key(self) -> None:
        context = MagicMock()
        assignable: ValueKey[str] = ValueKey("key")
        unassign_value(assignable, context=context)
        context.values.unset.assert_called_with(assignable)

    def test_key_no_context(self) -> None:
        with self.assertRaises(JobException) as e:
            unassign_value(ValueKey("key"))
        self.assertEqual("Unable to unassign context value without a context!", str(e.exception))

    def test_non_assignable(self) -> None:
        with self.assertRaises(JobException) as e:
            unassign_value("foo")  # type: ignore[arg-type]
        self.assertEqual("Unable to unassign foo", str(e.exception))


class TestJobScopeCondition(TestCase):
    def test_job_always(self) -> None:
        sut = job_always
        self.assertEqual("Always", repr(sut))
        self.assertEqual((True, "Always"), sut(MagicMock()))

    def test_job_never(self) -> None:
        sut = job_never
        self.assertEqual("Never", repr(sut))
        self.assertEqual((False, "Never"), sut(MagicMock()))

    def test_job_failing(self) -> None:
        sut = job_failing
        self.assertEqual("Job has failures.", repr(sut))
        self.assertEqual((True, "Job has failures."), sut(MagicMock(get_errors=MagicMock(return_value=[Exception()]))))
        self.assertEqual((False, "Job has failures."), sut(MagicMock(get_errors=MagicMock(return_value=[]))))

    def test_job_succeeding(self) -> None:
        sut = job_succeeding
        self.assertEqual("Job is succeeding.", repr(sut))
        self.assertEqual(
            (False, "Job is succeeding."), sut(MagicMock(get_errors=MagicMock(return_value=[Exception()])))
        )
        self.assertEqual((True, "Job is succeeding."), sut(MagicMock(get_errors=MagicMock(return_value=[]))))

    def test_scope_failing(self) -> None:
        mock_context = MagicMock()
        mock_scope = MagicMock()
        mock_scope.__str__.return_value = "Scope"  # type: ignore[attr-defined]

        sut = scope_failing(mock_scope)
        self.assertEqual("Scope has failures.", repr(sut))

        mock_context.get_errors.return_value = [Exception()]
        self.assertEqual((True, "Scope has failures."), sut(mock_context))
        mock_context.get_errors.assert_called_with(mock_scope)

        mock_context.reset_mock()
        mock_context.get_errors.return_value = []

        self.assertEqual((False, "Scope has failures."), sut(mock_context))
        mock_context.get_errors.assert_called_with(mock_scope)

    def test_scope_succeeding(self) -> None:
        mock_context = MagicMock()
        mock_scope = MagicMock()
        mock_scope.__str__.return_value = "Scope"  # type: ignore[attr-defined]

        sut = scope_succeeding(mock_scope)
        self.assertEqual("Scope is succeeding.", repr(sut))

        mock_context.get_errors.return_value = [Exception()]
        self.assertEqual((False, "Scope is succeeding."), sut(mock_context))
        mock_context.get_errors.assert_called_with(mock_scope)

        mock_context.reset_mock()
        mock_context.get_errors.return_value = []

        self.assertEqual((True, "Scope is succeeding."), sut(mock_context))
        mock_context.get_errors.assert_called_with(mock_scope)


class TestJobContext(TestCase):
    def test(self) -> None:
        mock_context = MagicMock()
        self.assertIs(mock_context, job_context(mock_context))

    def test_repr(self) -> None:
        self.assertEqual("job_context()", repr(job_context))


class TestJobAction(TestCase):
    def test(self) -> None:
        mock_action = MagicMock()
        sut = job_action(mock_action)
        self.assertIsInstance(sut, JobAction)
        sut(MagicMock())
        mock_action.assert_called_once()

    def test_with_args(self) -> None:
        mock_action = MagicMock()
        sut = job_action(mock_action, ValueRef("foo"), bar=ComputedValue(lambda: "bar"))
        self.assertIsInstance(sut, JobAction)
        sut(MagicMock())
        mock_action.assert_called_once_with("foo", bar="bar")

    def test_repr(self) -> None:
        mock_action = MagicMock()
        self.assertEqual(f"job_action({mock_action!r})", repr(job_action(mock_action)))


class FooAction(JobAction):
    def __init__(self, side_effects: list[str] | None = None, foo: str | None = None) -> None:
        super().__init__()
        if side_effects is None:
            side_effects = []
        self.side_effects: list[str] = side_effects
        self.foo = foo

    def action(self, context: JobContext) -> None:
        self.side_effects.append("action")


class TestLazyAction(TestCase):
    def test(self) -> None:
        sut = lazy_action(FooAction, ["foo"], foo="foo")
        action_instance = sut._get_action_instance(MagicMock())  # type: ignore[attr-defined]
        self.assertEqual(["foo"], action_instance.side_effects)
        self.assertEqual("foo", action_instance.foo)
        sut.action(MagicMock())  # type: ignore[attr-defined]
        self.assertEqual(["foo", "action"], action_instance.side_effects)

    def test_values_key(self) -> None:
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

    def test_repr(self) -> None:
        self.assertEqual(
            "lazy_action(FooAction)",
            repr(lazy_action(FooAction, ValueKey[str]("foo_key"), foo=ValueKey[str]("bar_key"))),
        )
