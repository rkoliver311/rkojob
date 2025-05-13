# Copyright (c) 2025 R.K. Oliver. All rights reserved.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

import os
from os import PathLike
from pathlib import Path
from typing import Any


def as_bool(value: Any) -> bool:
    """
    Coerces a value to ``bool``.
    Unreasonable values raise a ``ValueError``.

    :param value: The value to coerce.
    :returns: The `value` as a ``bool``.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value in (0, 1):
            return bool(value)
        raise ValueError(f"Integer {value} is not a valid boolean value (expected 0 or 1)")
    if isinstance(value, str):
        val = value.strip().lower()
        if val in {"true", "1", "yes", "on"}:
            return True
        if val in {"false", "0", "no", "off"}:
            return False
    raise ValueError(f"Cannot interpret {value!r} as a boolean")


def as_int(value: Any) -> int:
    """
    Coerces a value to ``int``.
    Unreasonable values raise a ``ValueError``.

    :param value: The value to coerce.
    :returns: The `value` as a ``int``.
    """
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    try:
        return int(str(value).strip())
    except (ValueError, TypeError) as e:
        raise ValueError(f"Cannot interpret {value!r} as an integer") from e


def as_float(value: Any) -> float:
    """
    Coerces a value to ``float``.
    Unreasonable values raise a ``ValueError``.

    :param value: The value to coerce.
    :returns: The `value` as a ``float``.
    """
    if isinstance(value, float):
        return value
    if isinstance(value, int):  # ints are valid floats
        return float(value)
    try:
        return float(str(value).strip())
    except (ValueError, TypeError) as e:
        raise ValueError(f"Cannot interpret {value!r} as a float") from e


def as_str(value: Any) -> str:
    """
    Coerces a value to ``str``. That is, call ``str(value)``.
    If value is ``None`` a ``ValueError`` is raised.

    :param value: The value to coerce.
    :returns: The `value` as a ``str``.
    """
    if value is None:
        raise ValueError("Cannot interpret None as a string")
    return str(value)


def as_path(value: str | PathLike | None) -> Path | None:
    """
    Returns a `Path` instance for the provided value.
    :param value: The value to return as a `Path` instance. If `value` is a `Path`, return it unchanged.
    :return: A `Path` instance or `None` if `value` is `None`.
    """
    if value is None or isinstance(value, Path):
        return value
    return Path(os.fspath(value))
