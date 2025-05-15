# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from unittest import TestCase

from rkojob.delegates import Delegate, DelegateException, delegate


class TestDelegate(TestCase):
    def test_add_callback(self):
        sut = Delegate[[str], str]()

        def callback(value: str) -> str:
            return value

        sut.add_callback(callback)

        self.assertEqual(["value"], sut("value"))

    def test_remove_callback(self):
        sut = Delegate[[str], str]()

        def callback(value: str) -> str:
            return value

        sut.add_callback(callback)
        sut.remove_callback(callback)

        self.assertEqual([], sut("value"))

    def test_add_callback_op(self):
        sut = Delegate[[str], str]()

        def callback1(value: str) -> str:
            return value

        def callback2(value: str) -> str:
            return value

        sut += callback1

        self.assertEqual(["value"], sut("value"))

        sut2 = Delegate[[str], str]()
        sut2 += callback2
        sut += sut2
        self.assertEqual([callback1, callback2], sut._callbacks)

    def test_remove_callback_op(self):
        sut = Delegate[[str], str]()

        def callback1(value: str) -> str:
            return value

        def callback2(value: str) -> str:
            return value

        sut.add_callback(callback1)
        sut -= callback1

        self.assertEqual([], sut("value"))

        sut += callback1
        sut += callback2

        sut2 = Delegate[[str], str]()
        sut2 += callback2

        sut -= sut2
        self.assertEqual([callback1], sut._callbacks)

    def test_bool(self) -> None:
        sut: Delegate[[str], str] = Delegate()

        def callback(value: str) -> str:
            return value

        self.assertFalse(bool(sut))
        sut += callback
        self.assertTrue(bool(sut))
        sut -= callback
        self.assertFalse(bool(sut))

    def test_add_op(self) -> None:
        def callback1(value: str) -> str:
            return value

        def callback2(value: str) -> str:
            return value

        def callback3(value: str) -> str:
            return value

        sut = Delegate[[str], str]()
        sut += callback1
        sut += callback2

        sut2 = Delegate[[str], str]()
        sut2 += callback3

        self.assertEqual([callback1, callback2, callback3], (sut + sut2)._callbacks)
        self.assertEqual([callback1, callback2, callback3], (sut + callback3)._callbacks)

    def test_add_op_options(self) -> None:
        sut: Delegate[[str], str] = Delegate(reverse=True) + Delegate(continue_on_error=True)
        self.assertTrue(sut._reverse)
        self.assertFalse(sut._continue_on_error)

    def test_sub_op(self) -> None:
        def callback1(value: str) -> str:
            return value

        def callback2(value: str) -> str:
            return value

        sut = Delegate[[str], str]()
        sut += callback1
        sut += callback2

        sut2 = Delegate[[str], str]()
        sut2 += callback1

        self.assertEqual([callback2], (sut - sut2)._callbacks)
        self.assertEqual([callback2], (sut - callback1)._callbacks)

    def test_sub_op_options(self) -> None:
        sut: Delegate[[str], str] = Delegate(reverse=False) - Delegate(continue_on_error=True)
        self.assertFalse(sut._reverse)
        self.assertFalse(sut._continue_on_error)

    def test_radd_op(self) -> None:
        def callback(value: str) -> str:
            return value

        sut = callback + Delegate[[str], str]()
        self.assertEqual([callback], sut._callbacks)

    def test_in_op(self) -> None:
        def callback(value: str) -> str:
            return value

        sut = Delegate[[str], str]()

        self.assertFalse(callback in sut)
        sut += callback
        self.assertTrue(callback in sut)

    def test_remove_callback_when_not_present(self):
        sut = Delegate[str, str]()

        def callback(value: str) -> str:
            return value

        sut.remove_callback(callback)

        self.assertEqual([], sut("value"))

    def test_callback_raises_exception(self):
        sut = Delegate[str, str](continue_on_error=True)

        error = Exception("error")

        def failing_callback(value: str) -> str:
            raise error

        sut.add_callback(failing_callback)

        def callback(value: str) -> str:
            return value

        sut.add_callback(callback)

        self.assertEqual([error, "value"], sut("value"))

    def test_callback_raises_exception_continue(self):
        sut = Delegate[str, str]()

        error = Exception("error")

        def failing_callback(_: str) -> str:
            raise error

        sut.add_callback(failing_callback)

        def callback(value: str) -> str:
            return value

        sut.add_callback(callback)

        with self.assertRaises(DelegateException) as e:
            _ = sut("value")
        self.assertEqual("error", str(e.exception))
        self.assertIs(error, e.exception.error)
        self.assertIs(error, e.exception.__cause__)
        self.assertEqual([error, None], e.exception.results)

    def test_reverse_callback(self):
        sut = Delegate[[str], str](reverse=True)
        side_effects = []

        def callback1(x):
            value = x * 1
            side_effects.append(value)
            return value

        sut.add_callback(callback1)

        def callback2(x):
            value = x * 2
            side_effects.append(value)
            return value

        sut.add_callback(callback2)

        def callback3(x):
            value = x * 3
            side_effects.append(value)
            return value

        sut.add_callback(callback3)

        self.assertEqual(["xxx", "xx", "x"], sut("x"))
        self.assertEqual(["xxx", "xx", "x"], side_effects)

    def test_non_callable_callback(self):
        with self.assertRaises(ValueError) as e:
            Delegate().add_callback("non-callable")
        self.assertEqual("callback must be callable", str(e.exception))

    def test_decorator(self):
        class Foo:
            @delegate
            def foo(self, foo: int, bar: str) -> str:
                _ = foo, bar  # not used
                return ""

            @delegate(continue_on_error=False, reverse=True)
            def bar(self, foo: int, bar: str) -> str:
                _ = foo, bar  # not used
                return ""

        foo = Foo()
        self.assertEqual([], foo.foo(1, "foo"))

        def callback(count: int, noun: str) -> str:
            return f"{count} {noun}{'s' if count != 1 else ''}"

        foo.foo += callback
        self.assertEqual(["1 dog"], foo.foo(1, "dog"))

        foo.foo += lambda count, noun: f"{count} {noun}(s)"
        self.assertEqual(["1 dog", "1 dog(s)"], foo.foo(1, "dog"))

        foo.bar += lambda count, noun: f"{count} {noun}(s)"
        foo.bar += lambda count, noun: f"{noun}: {count}"
        foo.bar += lambda count, noun: [][1]
        foo.bar += lambda count, noun: "Should see this"
        with self.assertRaises(DelegateException):
            foo.bar(1, "dog")

        with self.assertRaises(AttributeError) as e:
            foo.bar = Delegate()
        self.assertEqual("Cannot reassign delegate 'bar'. Use '+=' to add handlers.", str(e.exception))
