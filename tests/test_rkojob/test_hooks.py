# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

from unittest import TestCase
from unittest.mock import MagicMock, NonCallableMagicMock

from rkojob import JobActionScope
from rkojob.hooks import JobHook, JobHooksImpl


class TestJobHooksImpl(TestCase):
    def test_register(self) -> None:
        mock_hook_1 = MagicMock()
        mock_hook_2 = MagicMock()
        mock_hook_3 = MagicMock()

        sut = JobHooksImpl()
        sut.register("*", mock_hook_1)
        sut.register("job.stage", mock_hook_2)
        sut.register("job.stage", mock_hook_3)

        self.assertEqual([mock_hook_1], sut._hooks["*"])
        self.assertEqual([mock_hook_2, mock_hook_3], sut._hooks["job.stage"])

    def test_get_hooks(self) -> None:
        mock_hook_0 = MagicMock(name="hook_0")
        mock_hook_1 = MagicMock(name="hook_1")
        mock_hook_2 = MagicMock(name="hook_2")
        mock_hook_3 = MagicMock(name="hook_3")
        mock_hook_4 = MagicMock(name="hook_4")
        mock_hook_5 = MagicMock(name="hook_5")
        mock_hook_6 = MagicMock(name="hook_6")
        mock_hook_7 = MagicMock(name="hook_7")

        sut = JobHooksImpl()
        sut.register("**", mock_hook_0)
        sut.register("*", mock_hook_1)
        sut.register("job/*", mock_hook_2)
        sut.register("job/stage", mock_hook_3)
        sut.register("job/stage*/*", mock_hook_4)
        sut.register("job/*/*/step", mock_hook_5)
        sut.register("job/**/step", mock_hook_6)
        sut.register("job/stage-?/step-?", mock_hook_7)

        self.assertEqual([mock_hook_0, mock_hook_1], sut.get_hooks("job"))
        self.assertEqual([mock_hook_0, mock_hook_1], sut.get_hooks("job"))
        self.assertEqual([mock_hook_0, mock_hook_1], sut.get_hooks("foo"))
        self.assertEqual([mock_hook_0, mock_hook_2], sut.get_hooks("job/foo"))
        self.assertEqual([mock_hook_0, mock_hook_6], sut.get_hooks("job/foo/step"))
        self.assertEqual([mock_hook_0, mock_hook_2, mock_hook_3], sut.get_hooks("job/stage"))
        self.assertEqual([mock_hook_0, mock_hook_4], sut.get_hooks("job/stage-1/group-1"))
        self.assertEqual([mock_hook_0, mock_hook_5, mock_hook_6], sut.get_hooks("job/foo/bar/step"))
        self.assertEqual([mock_hook_0, mock_hook_5, mock_hook_6], sut.get_hooks("job/stage-1/group-1/step"))
        self.assertEqual([mock_hook_0, mock_hook_4, mock_hook_7], sut.get_hooks("job/stage-1/step-1"))

    def test_segment_glob_to_regex(self) -> None:
        sut = JobHooksImpl()._segment_glob_to_regex

        self.assertEqual(r"(?:[^\.]*)", sut("*", "."))
        self.assertEqual(r"(?:[^\.]*[^\.]*)", sut("**", "."))
        self.assertEqual(r"(?:[^/]*)", sut("*", "/"))
        self.assertEqual(r"(?:[^/]*[^/]*)", sut("**", "/"))
        self.assertEqual(r"(?:foo[^/]*)", sut("foo*", "/"))
        self.assertEqual(r"(?:[^/]*foo)", sut("*foo", "/"))
        self.assertEqual(r"(?:f[^/]*o)", sut("f*o", "/"))
        self.assertEqual(r"(?:f[^/]o)", sut("f?o", "/"))

        self.assertEqual(r"(?:f\?[^\.]*o)", sut("f\\?*o", "."))

    def test_pattern_to_regex(self) -> None:
        sut = JobHooksImpl()._pattern_to_regex

        self.assertEqual(r"^(?:[^\.]*)$", sut("*", "."))
        self.assertEqual(r"^(?:[^/]*)$", sut("*", "/"))

        self.assertEqual(r"^(?:[^/]+(?:/[^/]+)*)?$", sut("**", "/"))
        self.assertEqual(r"^(?:[^\.]+(?:\.[^\.]+)*)?$", sut("**.**", "."))

        self.assertEqual(r"^(?:foo)(?:/[^/]+)*$", sut("foo/**", "/"))


class TestJobHook(TestCase):
    def test_scope(self) -> None:
        scope = NonCallableMagicMock(spec=JobActionScope)
        sut = JobHook(before=scope)
        self.assertIsInstance(sut, JobHook)
        self.assertIs(sut.get_before(MagicMock()), scope)
        self.assertIsNone(sut.get_after(MagicMock()))

    def test_callable(self) -> None:
        scope = NonCallableMagicMock(spec=JobActionScope)
        sut = JobHook(before=lambda x: scope)
        self.assertIsInstance(sut, JobHook)
        self.assertIs(sut.get_before(MagicMock()), scope)
        self.assertIsNone(sut.get_after(MagicMock()))
