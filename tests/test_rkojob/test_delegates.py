from unittest import TestCase

from rkojob.delegates import Delegate, DelegateException, delegate


class TestDelegate(TestCase):
    def test_add_callback(self):
        sut = Delegate[str, str]()

        def callback(value: str) -> str:
            return value

        sut.add_callback(callback)

        self.assertEqual(["value"], sut("value"))

    def test_remove_callback(self):
        sut = Delegate[str, str]()

        def callback(value: str) -> str:
            return value

        sut.add_callback(callback)
        sut.remove_callback(callback)

        self.assertEqual([], sut("value"))

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
        sut = Delegate[str, str](reverse=True)
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

        self.assertEqual(["x", "xx", "xxx"], sut("x"))
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

        foo.foo.add_callback(callback)
        self.assertEqual(["1 dog"], foo.foo(1, "dog"))

        foo.foo.add_callback(lambda count, noun: f"{count} {noun}(s)")
        self.assertEqual(["1 dog", "1 dog(s)"], foo.foo(1, "dog"))

        foo.bar.add_callback(lambda count, noun: f"{count} {noun}(s)")
        foo.bar.add_callback(lambda count, noun: f"{noun}: {count}")
        foo.bar.add_callback(lambda count, noun: [][1])
        foo.bar.add_callback(lambda count, noun: "Should see this")
        with self.assertRaises(DelegateException):
            foo.bar(1, "dog")
