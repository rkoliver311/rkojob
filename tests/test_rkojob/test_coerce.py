# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from pathlib import Path
from typing import Any, Callable
from unittest import TestCase

from rkojob.coerce import as_bool, as_float, as_int, as_path, as_str


class CoercionTest(TestCase):
    def assertCoerces(self, coercer: Callable[[Any], Any], cases: list[tuple[Any, Any]]) -> None:
        for val, expected in cases:
            with self.subTest(val=val):
                self.assertEqual(coercer(val), expected)

    def assertFails(self, func: Callable[[Any], Any], cases: list[Any]) -> None:
        for val in cases:
            with self.subTest(val=val):
                with self.assertRaises(ValueError):
                    func(val)


class TestAsBool(CoercionTest):
    def test_true_values(self) -> None:
        self.assertCoerces(
            as_bool, [("true", True), ("True", True), ("1", True), ("yes", True), ("on", True), (True, True)]
        )

    def test_false_values(self) -> None:
        self.assertCoerces(
            as_bool,
            [
                ("false", False),
                ("False", False),
                ("FALSE", False),
                ("0", False),
                ("no", False),
                ("off", False),
                (False, False),
            ],
        )

    def test_invalid_values(self) -> None:
        self.assertFails(as_bool, ["maybe", "", None, 42, 1.0, 0.0, object()])

    def test_integer_values(self) -> None:
        self.assertCoerces(as_bool, [(1, True), (0, False)])
        self.assertFails(as_bool, [2])


class TestAsInt(CoercionTest):
    def test_valid_ints(self) -> None:
        self.assertCoerces(
            as_int,
            [
                (42, 42),
                ("42", 42),
                (" 42 ", 42),
                (42.0, 42),
            ],
        )

    def test_invalid_ints(self) -> None:
        self.assertFails(as_int, ["3.14", "foo", None, object()])


class TestAsFloat(CoercionTest):
    def test_valid_floats(self) -> None:
        self.assertCoerces(
            as_float,
            [
                (3.14, 3.14),
                ("3.14", 3.14),
                (" 2.0 ", 2.0),
                (2, 2.0),
            ],
        )

    def test_invalid_floats(self) -> None:
        self.assertFails(as_float, ["NaNish", None, object()])


class TestAsStr(CoercionTest):
    def test_valid_strs(self) -> None:
        self.assertCoerces(
            as_str,
            [
                ("foo", "foo"),
                (42, "42"),
                (3.14, "3.14"),
                (True, "True"),
            ],
        )

    def test_none_value(self) -> None:
        self.assertFails(as_str, [None])


class TestAsPath(TestCase):
    def test_none(self) -> None:
        self.assertIsNone(as_path(None))

    def test_str(self) -> None:
        self.assertEqual(Path("/foo/bar"), as_path("/foo/bar"))

    def test_path(self) -> None:
        value = Path("/foo/bar")
        self.assertIs(value, as_path(value))
