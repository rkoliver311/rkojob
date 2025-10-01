# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

import re

from rkojob import JobHook, JobHooks


class JobHooksImpl(JobHooks):
    def __init__(self) -> None:
        self._patterns: dict[str, re.Pattern] = {}
        self._hooks: dict[str, list[JobHook]] = {}

    def register(self, pattern: str, hook: JobHook) -> None:
        if pattern not in self._hooks:
            self._hooks[pattern] = []
        self._hooks[pattern].append(hook)

    def get_hooks(self, path: str) -> list[JobHook]:
        hooks: list[JobHook] = []
        for pattern in self._hooks:
            if pattern not in self._patterns:
                self._patterns[pattern] = re.compile(self._pattern_to_regex(pattern, "/"))
            if self._patterns[pattern].match(path):
                hooks.extend(self._hooks[pattern])
        return hooks

    def _pattern_to_regex(self, pattern: str, sep: str) -> str:
        segs: list[str] = pattern.split(sep)
        sep_esc: str = re.escape(sep)
        seg_nonsep: str = rf"[^{sep_esc}]+"

        out: list[str] = ["^"]
        i = 0
        first = True

        while i < len(segs):
            seg = segs[i]
            if seg == "**":
                # Collapse consecutive **
                while i + 1 < len(segs) and segs[i + 1] == "**":
                    i += 1

                if not first:
                    # Zero or more additional segments
                    out.append(rf"(?:{sep_esc}{seg_nonsep})*")
                else:
                    # Zero or more segments
                    out.append(rf"(?:{seg_nonsep}(?:{sep_esc}{seg_nonsep})*)?")

            else:
                if not first:
                    out.append(sep_esc)
                out.append(self._segment_glob_to_regex(seg, sep))

            first = False
            i += 1

        out.append("$")
        return "".join(out)

    def _segment_glob_to_regex(self, seg: str, sep: str) -> str:
        """
        Translate a single *segment* glob to a regex that never matches the separator.
        Supports: *, ?, and character classes [] (with '!'/'^' negation).
        """
        sep_esc: str = re.escape(sep)
        out: list[str] = []
        i = 0
        n = len(seg)

        while i < n:
            ch = seg[i]

            if ch == "\\" and i + 1 < n:
                # Escaped char
                out.append(re.escape(seg[i + 1]))
                i += 2
                continue

            if ch == "*":
                # Match zero or more chars but not sep
                out.append(f"[^{sep_esc}]*")
                i += 1
                continue

            if ch == "?":
                # Match any char but not sep
                out.append(f"[^{sep_esc}]")
                i += 1
                continue

            # Suggested by AI but not sure I want it yet.
            # if ch == "[":
            #     # Copy a character class verbatim until closing ']'
            #     j = i + 1
            #     if j < n and seg[j] in ("!", "^"):
            #         j += 1  # keep negation marker inside the class
            #     if j < n and seg[j] == "]":
            #         j += 1  # literal ']' as first member
            #
            #     while j < n and seg[j] != "]":
            #         j += 1
            #     if j >= n:
            #         # Unclosed class: treat '[' literally
            #         out.append(r"\[")
            #         i += 1
            #     else:
            #         # Keep the class as-is, but escape regex meta outside class context
            #         cls = seg[i : j + 1]
            #         out.append(cls)
            #         i = j + 1
            #     continue

            # Literal char
            out.append(re.escape(ch))
            i += 1

        # Anchor this segment
        return "(?:" + "".join(out) + ")"
