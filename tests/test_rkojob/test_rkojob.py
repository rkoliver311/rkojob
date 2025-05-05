from unittest import TestCase
from unittest.mock import MagicMock

from rkojob import (
    JobContext,
    JobException,
    ValueKey,
    assign_value,
    resolve_value,
    unassign_value,
)
from rkojob.factories import JobContextFactory
from rkojob.values import ValueRef


class TestJobException(TestCase):
    def test_can_raise(self) -> None:
        try:
            raise JobException("error")
        except JobException as e:
            self.assertEqual("error", str(e))


class TestResolveValue(TestCase):
    def test_callable(self) -> None:
        context: JobContext = JobContextFactory.create(values=dict(key="value"))
        self.assertEqual("value", resolve_value(lambda ctx: ctx.values.get_ref("key").value, context=context))

    def test_callable_no_context(self) -> None:
        self.assertEqual("default", resolve_value(lambda ctx: ctx.values.get_ref("foo").value, default="default"))

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
