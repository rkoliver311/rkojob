from unittest import TestCase
from unittest.mock import MagicMock, patch

from rkojob.coerce import as_bool, as_str
from rkojob.values import (
    ComputedValue,
    EnvironmentVariable,
    LazyValue,
    MappedValueProvider,
    NoValue,
    NoValueError,
    ValueKey,
    ValueRef,
    Values,
    as_value_ref,
    get_ref_value,
)


class TestNoValue(TestCase):
    def test_bool(self) -> None:
        self.assertFalse(bool(NoValue))

    def test_str(self) -> None:
        self.assertEqual("No Value", str(NoValue))

    def test_repr(self) -> None:
        self.assertEqual("No Value", repr(NoValue))


class TestValueRef(TestCase):
    def test_value(self) -> None:
        self.assertEqual("value", ValueRef("value").value)

    def test_no_value(self) -> None:
        with self.assertRaises(NoValueError) as e:
            _ = ValueRef().value
        self.assertEqual("ValueRef() has no value", str(e.exception))

    def test_call(self) -> None:
        self.assertEqual("value", ValueRef("value")())

    def test_get_or_else(self) -> None:
        sut: ValueRef[str] = ValueRef()
        self.assertEqual("default", sut.get_or_else(default="default"))

    def test_get_or_else_2(self) -> None:
        self.assertEqual("value", ValueRef("value").get_or_else(default="default"))

    def test_get_or_else_3(self) -> None:
        sut: ValueRef[str | None] = ValueRef()
        sut.value = None
        self.assertIsNone(sut.get_or_else(default="default"))

    def test_has_value_no_value(self) -> None:
        self.assertFalse(ValueRef().has_value)

    def test_has_value(self) -> None:
        self.assertTrue(ValueRef("foo").has_value)

    def test_name(self) -> None:
        self.assertEqual("name", ValueRef(name="name").name)

    def test_no_name(self) -> None:
        self.assertIsNone(ValueRef().name)

    def test_unset(self) -> None:
        sut = ValueRef("foo")
        sut.unset()
        self.assertFalse(sut.has_value)

    def test_str(self) -> None:
        with self.assertRaises(NoValueError) as e:
            str(ValueRef())
        self.assertEqual("ValueRef() has no value", str(e.exception))
        with self.assertRaises(NoValueError) as e:
            str(ValueRef(name="name"))
        self.assertEqual("ValueRef(name=name) has no value", str(e.exception))

        self.assertEqual("value", str(ValueRef("value", name="name")))
        self.assertEqual("value", str(ValueRef("value")))
        sut: ValueRef[str | None] = ValueRef()
        sut.value = None
        self.assertEqual(str(None), str(sut))

    def test_repr(self) -> None:
        self.assertEqual("ValueRef()", repr(ValueRef()))
        self.assertEqual("ValueRef(value=value)", repr(ValueRef("value")))
        self.assertEqual("ValueRef(name=name)", repr(ValueRef(name="name")))
        self.assertEqual("ValueRef(name=name, value=value)", repr(ValueRef("value", name="name")))


class TestMappedValueProvider(TestCase):
    def test_value(self) -> None:
        self.assertEqual("FOO", MappedValueProvider(lambda x: str(x).upper(), ValueRef("foo")).value)

    def test_value_negative(self):
        with self.assertRaises(NoValueError) as e:
            _ = MappedValueProvider(lambda x: x.upper(), ValueRef()).value
        self.assertEqual("MappedValueProvider has no value", str(e.exception))

    def test_has_value(self) -> None:
        ref: ValueRef[str] = ValueRef()
        sut = MappedValueProvider(lambda x: str(x).upper(), ref)
        self.assertFalse(sut.has_value)
        ref.value = "foo"
        self.assertTrue(sut.has_value)

    def test_map(self) -> None:
        self.assertEqual("FOO", ValueRef("foo").map(lambda x: str(x).upper()).value)


class TestComputedValue(TestCase):
    def test_value(self) -> None:
        self.assertEqual("value", ComputedValue(lambda: "value").value)

    def test_no_value(self) -> None:
        with self.assertRaises(NoValueError) as e:
            _ = ComputedValue(None).value  # type: ignore[arg-type]
        self.assertEqual("ComputedValue has no value", str(e.exception))

    def test_no_value_with_name(self) -> None:
        with self.assertRaises(NoValueError) as e:
            _ = ComputedValue(None, name="name").value  # type: ignore[arg-type]
        self.assertEqual("ComputedValue(name=name) has no value", str(e.exception))

    def test_has_value(self) -> None:
        self.assertTrue(ComputedValue(lambda: "value").has_value)

    def test_has_value_no_value(self) -> None:
        self.assertFalse(ComputedValue(None).has_value)  # type: ignore[arg-type]


class TestLazyValue(TestCase):
    def test_value(self) -> None:
        self.assertEqual("value", LazyValue(lambda: "value").value)

    def test_no_value(self) -> None:
        with self.assertRaises(NoValueError) as e:
            _ = LazyValue(None).value  # type: ignore[arg-type]
        self.assertEqual("LazyValue has no value", str(e.exception))

    def test_no_value_with_name(self) -> None:
        with self.assertRaises(NoValueError) as e:
            _ = LazyValue(None, name="name").value  # type: ignore[arg-type]
        self.assertEqual("LazyValue(name=name) has no value", str(e.exception))

    def test_has_value(self) -> None:
        self.assertTrue(LazyValue(lambda: "value").has_value)

    def test_has_value_no_value(self) -> None:
        self.assertFalse(LazyValue(None).has_value)  # type: ignore[arg-type]

    def test_compute_only_once(self) -> None:
        func = MagicMock(return_value="value")
        sut = LazyValue(func)
        self.assertEqual("value", sut.get())
        self.assertEqual("value", sut.value)
        func.assert_called_once()


class TestAsValueRef(TestCase):
    def test(self) -> None:
        ref: ValueRef[str] = ValueRef("value")
        ref2: ValueRef[str] = as_value_ref(ref)
        self.assertIs(ref, ref2)

        self.assertIsInstance(as_value_ref("value"), ValueRef)

    def test_name(self) -> None:
        self.assertEqual("name", as_value_ref("value", name="name").name)

    def test_value(self) -> None:
        self.assertEqual("value", as_value_ref("value").value)


class TestGetRefValue(TestCase):
    def test_value(self) -> None:
        self.assertEqual("value", get_ref_value("value"))

    def test_value_ref(self) -> None:
        self.assertEqual("value", get_ref_value(ValueRef("value")))

    def test_default(self) -> None:
        self.assertEqual("default", get_ref_value(ValueRef(), default="default"))


class TestValues(TestCase):
    def test_has_value(self) -> None:
        sut = Values(int_ref=123, str_ref="abc")
        self.assertTrue(sut.has_value("int_ref"))
        self.assertTrue(sut.has_value(ValueKey("str_ref")))
        self.assertFalse(sut.has_value(ValueKey("foo")))

    def test_get(self) -> None:
        sut = Values(int_ref=123, str_ref="abc")
        self.assertEqual(123, sut.get("int_ref"))
        self.assertEqual("abc", sut.get(ValueKey("str_ref")))

    def test_set(self) -> None:
        sut = Values()
        self.assertFalse(sut.has_value("str_ref"))
        sut.set("str_ref", "abc")
        self.assertTrue(sut.has_value("str_ref"))
        self.assertEqual("abc", sut.get("str_ref"))

    def test_set_ref(self) -> None:
        sut = Values()
        str_key = ValueKey[str]("str_ref")
        self.assertFalse(sut.has_value(str_key))
        sut.set(str_key, ComputedValue(lambda: "abc"))
        self.assertTrue(sut.has_value(str_key))
        self.assertEqual("abc", sut.get(str_key))

    def test_set_no_value(self) -> None:
        sut = Values(int_ref=123)
        self.assertTrue(sut.has_value("int_ref"))
        sut.set(ValueKey("int_ref"), NoValue)
        self.assertFalse(sut.has_value("int_ref"))

    def test_set_ref_no_value(self) -> None:
        sut = Values(int_ref=123)
        int_key = ValueKey[int]("int_ref")
        self.assertTrue(sut.has_value(int_key))
        sut.set(int_key, ValueRef())
        self.assertFalse(sut.has_value(int_key))

    def test_unset(self) -> None:
        sut = Values(int_ref=123)
        int_key = ValueKey[int]("int_ref")
        self.assertTrue(sut.has_value(int_key))
        sut.unset(int_key)
        self.assertFalse(sut.has_value(int_key))

    def test_get_or_else(self) -> None:
        self.assertEqual("default", Values().get_or_else("str_ref", default="default"))
        self.assertEqual("abc", Values(str_ref="abc").get_or_else("str_ref", default="default"))

    def test_get_ref(self) -> None:
        sut = Values(int_ref=123)
        int_ref: ValueRef[int] = sut.get_ref(ValueKey[int]("int_ref"))
        self.assertIsNotNone(int_ref)
        self.assertTrue(int_ref.has_value)
        self.assertEqual(123, int_ref.value)

        str_ref: ValueRef[str] = sut.get_ref("str_ref")
        self.assertIsNotNone(str_ref)
        self.assertFalse(str_ref.has_value)
        str_ref.value = "abc"
        self.assertEqual("abc", sut.get("str_ref"))
        str_ref.unset()
        self.assertFalse(sut.has_value("str_ref"))

    def test_get_no_value(self) -> None:
        with self.assertRaises(NoValueError) as e:
            _ = Values().get("int_ref")
        self.assertEqual("Values has no value associated with key 'int_ref'", str(e.exception))

    def test_get_ref_no_value(self) -> None:
        int_ref: ValueRef[int] = Values().get_ref("int_ref")
        with self.assertRaises(NoValueError) as e:
            _ = int_ref.get()
        self.assertEqual("Values has no value associated with key 'int_ref'", str(e.exception))

    def test_keys(self) -> None:
        sut = Values(int_prop=123, str_prop="abc")
        self.assertEqual({"int_prop", "str_prop"}, sut.keys())

        sut.unset("int_prop")
        self.assertEqual({"str_prop"}, sut.keys())

        sut.unset("str_prop")
        self.assertEqual(set(), sut.keys())


class TestEnvironmentVariable(TestCase):
    @patch("rkojob.values.os.getenv")
    def test_get(self, mock_getenv) -> None:
        mock_getenv.return_value = "123"
        self.assertEqual(123, EnvironmentVariable("int_ref", int).get())

    @patch("rkojob.values.os.getenv")
    def test_has_value(self, mock_getenv) -> None:
        mock_getenv.return_value = "TRUE"
        self.assertTrue(EnvironmentVariable("int_ref", bool).has_value)

    @patch("rkojob.values.os.getenv")
    def test_has_value_no_value(self, mock_getenv) -> None:
        mock_getenv.return_value = NoValue
        self.assertFalse(EnvironmentVariable("int_ref", bool).has_value)

    def test_has_value_default(self) -> None:
        self.assertTrue(EnvironmentVariable("Lets_Hope_This_Is_Not_Set_rkojob", as_str, default="default").has_value)

    @patch("rkojob.values.os.getenv")
    def test_get_no_value(self, mock_getenv) -> None:
        mock_getenv.return_value = NoValue
        with self.assertRaises(NoValueError) as e:
            _ = EnvironmentVariable("path_ref", str).get()
        self.assertEqual("Environment variable 'path_ref' is not set.", str(e.exception))

    def test_get_default(self) -> None:
        self.assertEqual(
            "default", EnvironmentVariable("Lets_Hope_This_Is_Not_Set_rkojob", as_str, default="default").get()
        )

    def test_repr(self) -> None:
        self.assertEqual("environment_variable('key')", repr(EnvironmentVariable("key", str)))
        self.assertEqual("environment_variable('key')", repr(EnvironmentVariable("key", as_str)))
        self.assertEqual("environment_variable('key', as_bool)", repr(EnvironmentVariable("key", as_bool)))
        self.assertEqual(
            "environment_variable('key', as_bool, default=True)",
            repr(EnvironmentVariable("key", as_bool, default=True)),
        )
