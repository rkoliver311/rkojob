from unittest import TestCase
from unittest.mock import MagicMock

from rkojob import (
    JobBaseStatus,
    JobCallable,
    JobContext,
    JobException,
    JobResolvableValue,
    JobStatusCollector,
    ValueKey,
    assign_value,
    context_value,
    lazy_format,
    resolve_map,
    resolve_value,
    resolve_values,
    unassign_value,
)
from rkojob.coerce import as_bool
from rkojob.factories import JobContextFactory
from rkojob.values import NoValueError, ValueRef, Values


class TestJobException(TestCase):
    def test_can_raise(self) -> None:
        try:
            raise JobException("error")
        except JobException as e:
            self.assertEqual("error", str(e))


class TestJobBaseStatus(TestCase):
    def test_scope(self) -> None:
        sut = JobBaseStatus()
        sut.start_scope = MagicMock()  # type: ignore[method-assign]
        sut.finish_scope = MagicMock()  # type: ignore[method-assign]
        sut.error = MagicMock()  # type: ignore[method-assign]
        mock_scope = MagicMock()
        with sut.scope(mock_scope):
            sut.start_scope.assert_called_with(mock_scope)
        sut.finish_scope.assert_called_with(mock_scope)
        sut.error.assert_not_called()

    def test_scope_error(self) -> None:
        sut = JobBaseStatus()
        sut.start_scope = MagicMock()  # type: ignore[method-assign]
        sut.finish_scope = MagicMock()  # type: ignore[method-assign]
        sut.error = MagicMock()  # type: ignore[method-assign]
        mock_scope = MagicMock()
        exception = Exception("error")
        with self.assertRaises(Exception):
            with sut.scope(mock_scope):
                sut.start_scope.assert_called_with(mock_scope)
                raise exception
        sut.error.assert_called_with(exception)
        sut.finish_scope.assert_called_with(mock_scope)

    def test_section(self) -> None:
        sut = JobBaseStatus()
        sut.start_section = MagicMock()  # type: ignore[method-assign]
        sut.finish_section = MagicMock()  # type: ignore[method-assign]
        sut.error = MagicMock()  # type: ignore[method-assign]
        with sut.section("name"):
            sut.start_section.assert_called_with("name")
        sut.finish_section.assert_called_with("name")
        sut.error.assert_not_called()

    def test_section_error(self) -> None:
        sut = JobBaseStatus()
        sut.start_section = MagicMock()  # type: ignore[method-assign]
        sut.finish_section = MagicMock()  # type: ignore[method-assign]
        sut.error = MagicMock()  # type: ignore[method-assign]
        exception = Exception("error")
        with self.assertRaises(Exception):
            with sut.section("name"):
                sut.start_section.assert_called_with("name")
                raise exception
        sut.error.assert_called_with(exception)
        sut.finish_section.assert_called_with("name")

    def test_item(self) -> None:
        sut = JobBaseStatus()
        sut.start_item = MagicMock()  # type: ignore[method-assign]
        sut.finish_item = MagicMock()  # type: ignore[method-assign]
        sut.error = MagicMock()  # type: ignore[method-assign]
        with sut.item("item"):
            sut.start_item.assert_called_with("item")
        sut.finish_item.assert_called_with()
        sut.error.assert_not_called()

    def test_item_error(self) -> None:
        sut = JobBaseStatus()
        sut.start_item = MagicMock()  # type: ignore[method-assign]
        sut.finish_item = MagicMock()  # type: ignore[method-assign]
        sut.error = MagicMock()  # type: ignore[method-assign]
        exception = Exception("error")
        with self.assertRaises(Exception):
            with sut.item("item"):
                sut.start_item.assert_called_with("item")
                raise exception
        sut.error.assert_called_with(exception)
        sut.finish_item.assert_called_with()


class TestJobStatusCollector(TestCase):
    def setUp(self) -> None:
        self.mock_arg = MagicMock()
        self.mock_1 = MagicMock()
        self.mock_2 = MagicMock()
        self.sut = JobStatusCollector()
        self.sut.add_listener(self.mock_1)
        self.sut.add_listener(self.mock_2)

    def tearDown(self) -> None:
        self.mock_1.reset_mock()
        self.mock_2.reset_mock()

    def test_start_scope(self):
        self.sut.start_scope(self.mock_arg)
        self.mock_1.start_scope.assert_called_with(self.mock_arg)
        self.mock_2.start_scope.assert_called_with(self.mock_arg)

    def test_finish_scope(self):
        self.sut.finish_scope(self.mock_arg)
        self.mock_1.finish_scope.assert_called_with(self.mock_arg)
        self.mock_2.finish_scope.assert_called_with(self.mock_arg)

    def test_skip_scope(self):
        self.sut.skip_scope(self.mock_arg)
        self.mock_1.skip_scope.assert_called_with(self.mock_arg)
        self.mock_2.skip_scope.assert_called_with(self.mock_arg)

    def test_start_section(self):
        self.sut.start_section(self.mock_arg)
        self.mock_1.start_section.assert_called_with(self.mock_arg)
        self.mock_2.start_section.assert_called_with(self.mock_arg)

    def test_finish_section(self):
        self.sut.finish_section(self.mock_arg)
        self.mock_1.finish_section.assert_called_with(self.mock_arg)
        self.mock_2.finish_section.assert_called_with(self.mock_arg)

    def test_start_item(self):
        self.sut.start_item(self.mock_arg)
        self.mock_1.start_item.assert_called_with(self.mock_arg)
        self.mock_2.start_item.assert_called_with(self.mock_arg)

    def test_finish_item(self):
        self.sut.finish_item(self.mock_arg)
        self.mock_1.finish_item.assert_called_with(self.mock_arg)
        self.mock_2.finish_item.assert_called_with(self.mock_arg)

    def test_info(self):
        self.sut.info(self.mock_arg)
        self.mock_1.info.assert_called_with(self.mock_arg)
        self.mock_2.info.assert_called_with(self.mock_arg)

    def test_detail(self):
        self.sut.detail(self.mock_arg)
        self.mock_1.detail.assert_called_with(self.mock_arg)
        self.mock_2.detail.assert_called_with(self.mock_arg)

    def test_error(self):
        self.sut.error(self.mock_arg)
        self.mock_1.error.assert_called_with(self.mock_arg)
        self.mock_2.error.assert_called_with(self.mock_arg)

    def test_warning(self):
        self.sut.warning(self.mock_arg)
        self.mock_1.warning.assert_called_with(self.mock_arg)
        self.mock_2.warning.assert_called_with(self.mock_arg)

    def test_scope_context_manager(self):
        with self.sut.scope(self.mock_arg):
            self.mock_1.start_scope.assert_called_with(self.mock_arg)
            self.mock_2.start_scope.assert_called_with(self.mock_arg)
        self.mock_1.finish_scope.assert_called_with(self.mock_arg)
        self.mock_2.finish_scope.assert_called_with(self.mock_arg)

    def test_scope_context_manager_negative(self):
        exception = Exception()
        with self.assertRaises(Exception) as e:
            with self.sut.scope(self.mock_arg):
                self.mock_1.start_scope.assert_called_with(self.mock_arg)
                self.mock_2.start_scope.assert_called_with(self.mock_arg)
                raise exception
        self.assertIs(exception, e.exception)
        self.mock_1.error.assert_called_with(exception)
        self.mock_1.finish_scope.assert_called_with(self.mock_arg)
        self.mock_2.error.assert_called_with(exception)
        self.mock_2.finish_scope.assert_called_with(self.mock_arg)

    def test_section_context_manager(self):
        with self.sut.section(self.mock_arg):
            self.mock_1.start_section.assert_called_with(self.mock_arg)
            self.mock_2.start_section.assert_called_with(self.mock_arg)
        self.mock_1.finish_section.assert_called_with(self.mock_arg)
        self.mock_2.finish_section.assert_called_with(self.mock_arg)

    def test_section_context_manager_negative(self):
        exception = Exception()
        with self.assertRaises(Exception) as e:
            with self.sut.section(self.mock_arg):
                self.mock_1.start_section.assert_called_with(self.mock_arg)
                self.mock_2.start_section.assert_called_with(self.mock_arg)
                raise exception
        self.assertIs(exception, e.exception)
        self.mock_1.error.assert_called_with(exception)
        self.mock_1.finish_section.assert_called_with(self.mock_arg)
        self.mock_2.error.assert_called_with(exception)
        self.mock_2.finish_section.assert_called_with(self.mock_arg)

    def test_item_context_manager(self):
        with self.sut.item(self.mock_arg):
            self.mock_1.start_item.assert_called_with(self.mock_arg)
            self.mock_2.start_item.assert_called_with(self.mock_arg)
        self.mock_1.finish_item.assert_called_with()
        self.mock_2.finish_item.assert_called_with()

    def test_item_context_manager_negative(self):
        exception = Exception()
        with self.assertRaises(Exception) as e:
            with self.sut.item(self.mock_arg):
                self.mock_1.start_item.assert_called_with(self.mock_arg)
                self.mock_2.start_item.assert_called_with(self.mock_arg)
                raise exception
        self.assertIs(exception, e.exception)
        self.mock_1.error.assert_called_with(exception)
        self.mock_1.finish_item.assert_called_with()
        self.mock_2.error.assert_called_with(exception)
        self.mock_2.finish_item.assert_called_with()


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
        sut = lazy_format("{ref1}, {ref2}", ref2=ref2)
        self.assertEqual("value1, value2", resolve_value(sut, context=MagicMock(values=Values(ref1="value1"))))

    def test_missing_key(self) -> None:
        ref2 = ValueRef("value2")
        sut = lazy_format("{ref1}, {ref2}", ref2=ref2)
        with self.assertRaises(NoValueError) as e:
            _ = resolve_value(sut, context=MagicMock(values=Values()), raise_no_value=True)
        self.assertEqual("Values has no value associated with key 'ref1'", str(e.exception))

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
