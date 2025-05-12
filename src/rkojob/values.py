from __future__ import annotations

import os
from typing import (
    Any,
    Callable,
    Final,
    Generic,
    Optional,
    Protocol,
    Set,
    TypeAlias,
    TypeGuard,
    TypeVar,
    cast,
    final,
    runtime_checkable,
)

from rkojob.coerce import as_str

T = TypeVar("T")
U = TypeVar("U")
T_co = TypeVar("T_co", covariant=True)
T_contra = TypeVar("T_contra", contravariant=True)


class NoValueError(Exception):
    def __init__(self, message: str | None = None):
        super().__init__("No value" if message is None else message)


@final
class NoValueType:
    """Sentinel type to distinguish from ``None``."""

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "No Value"


NoValue: Final[NoValueType] = NoValueType()
"""Sentinel value to distinguish from ``None``."""


def _is_value(value: T | NoValueType) -> TypeGuard[T]:
    """
    ``TypeGuard`` to insist that `value` is not ``NoValue``.
    :param value: The value check.
    """
    return value is not NoValue


@runtime_checkable
class ValueProvider(Protocol[T_co]):
    """
    A protocol for a type that provides a value.  A ``NoValueError`` should be raised if ``get()`` is called when no
    value is available.  The ``has_value`` property can be used to check whether a value is available.
    """

    def get(self) -> T_co: ...

    @property
    def has_value(self) -> bool: ...


@runtime_checkable
class ValueConsumer(Protocol[T_contra]):
    """
    A protocol for a type that consumes a value.  A ``NoValueError`` should be raised if value cannot be set or unset
    via the ``set()`` and ``unset()`` methods.
    """

    def set(self, value: T_contra) -> None: ...

    def unset(self) -> None: ...


class ValueRef(Generic[T], ValueProvider[T], ValueConsumer[T]):
    def __init__(self, value: T | NoValueType = NoValue, name: str | None = None) -> None:
        """
        A read/write value container that implements the ``ValueProvider[T]`` and ``ValueConsumer[T]`` protocols.

        :param value: The initial value of the ``ValueRef``.
        :param name: An optional name for the ``ValueRef``.
        """
        self._value: T | NoValueType = NoValue
        self._name: str | None = name

        if _is_value(value):
            self.value = value

    def get(self) -> T:
        """
        Get the value currently held by this instance. A ``NoValueError`` is raised if no value is present.
        :returns: The value held by this instance.
        """
        if not self.has_value:
            raise NoValueError(f"{repr(self)} has no value")
        return cast(T, self._value)

    @property
    def has_value(self) -> bool:
        """
        :returns: Whether this instance holds a value.
        """
        return _is_value(self._value)

    def set(self, value: T) -> None:
        """
        Set the value held by this instance.
        :param value: The value to set on this instance.
        """
        self._value = value

    def unset(self) -> None:
        """Removes the value, if any, held by this instance."""
        self._value = NoValue

    @property
    def value(self) -> T:
        """:returns: The value held by this instance. A ``NoValueError`` is raised if no value is present."""
        return self.get()

    @value.setter
    def value(self, value: T) -> None:
        """:param value: Sets the value to be held by this instance."""
        self.set(value)

    def get_or_else(self, default: T | None) -> T | None:
        """
        Gets the value held by this instance or returns `default` if no value is present.
        :param default: The value to return if no value is present.
        """
        return self.get() if self.has_value else default

    @property
    def name(self) -> Optional[str]:
        """:returns: The optional name of this ``ValueRef``."""
        return self._name

    def map(self, func: Callable[[T], U]) -> MappedValueProvider[U]:
        """
        Creates a ``ValueProvider`` instance that transforms (maps) the value held by this instance. The value is a live
        view of this ``ValueRef``'s value.

        :param func: The transformation function.
        :returns: A ``ValueProvider`` that transforms the value held by this ``ValueRef``.
        """
        return MappedValueProvider(func, provider=self)

    def __str__(self) -> str:
        return str(self.value)

    def __repr__(self) -> str:
        if self._name and self.has_value:
            return f"{self.__class__.__name__}(name={self._name}, value={self._value})"
        if self._name:
            return f"{self.__class__.__name__}(name={self._name})"
        if self.has_value:
            return f"{self.__class__.__name__}(value={self._value})"
        return f"{self.__class__.__name__}()"

    def __call__(self, *args, **kwargs) -> T:
        return self.value


class MappedValueProvider(ValueProvider[U]):
    def __init__(self, func: Callable[[T], U], provider: ValueProvider[T] | None = None) -> None:
        """
        A ``ValueProvider`` that transforms the value returned by another ``ValueProvider``.
        :param func: The transformation function.
        :provider: The provider that provides the value to transform.
        """
        self._func: Callable[[T], U] = func
        self._provider: ValueProvider[T] | None = provider

    def get(self) -> U:
        """:returns: The transformed value."""
        if self._provider is None or not self.has_value:
            raise NoValueError(f"{repr(self)} has no value")
        return self._func(self._provider.get())

    @property
    def has_value(self) -> bool:
        """:returns: Whether the underlying provider has a value."""
        return self._provider is not None and self._provider.has_value

    @property
    def value(self) -> U:
        """:returns: The transformed value."""
        return self.get()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}"


class ComputedValue(ValueProvider[T]):
    """
    A `ValueProvider` that computes the value everytime `get()` is called.
    """

    def __init__(self, func: Callable[[], T], name: str | None = None) -> None:
        self._func: Callable[[], T] = func
        self._name = name

    @property
    def value(self) -> T:
        return self.get()

    def get(self) -> T:
        if self._func is None:
            raise NoValueError(f"{repr(self)} has no value")
        return self._func()

    @property
    def has_value(self) -> bool:
        return self._func is not None

    def __repr__(self) -> str:
        if self._name:
            return f"{self.__class__.__name__}(name={self._name})"
        return f"{self.__class__.__name__}"


class LazyValue(ValueProvider[T]):
    """
    A `ValueProvider` that computes the value only the first time `get()` is called.
    """

    def __init__(self, func: Callable[[], T], name: str | None = None) -> None:
        self._func: Callable[[], T] = func
        self._name = name
        self._value: T | NoValueType = NoValue

    @property
    def value(self) -> T:
        return self.get()

    def get(self) -> T:
        if self._func is None:
            raise NoValueError(f"{repr(self)} has no value")
        if not _is_value(self._value):
            self._value = self._func()
        return self._value

    @property
    def has_value(self) -> bool:
        return self._func is not None

    def __repr__(self) -> str:
        if self._name:
            return f"{self.__class__.__name__}(name={self._name})"
        return f"{self.__class__.__name__}"


class EnvironmentVariable(ValueProvider[T_co]):
    def __init__(self, name: str, coercer: Callable[[str], T_co], default: T_co | NoValueType = NoValue) -> None:
        """
        A type-safe ``ValueProvider`` that provides access to an environment variable.

        :param name: The name of the environment variable.
        :param coercer: The function used to coerce the environment variable value (a ``str``) to the desired type.
        :param default: The default value to return if the environment variable is not set.
        """
        self._name: str = name
        self._coercer: Callable[[str], T_co] = coercer
        self._default: T_co | NoValueType = default

    def get(self) -> T_co:
        value: Any = os.getenv(self._name, default=self._default)
        if _is_value(value):
            return self._coercer(value)
        raise NoValueError(f"Environment variable '{self._name}' is not set.")

    @property
    def has_value(self) -> bool:
        return _is_value(os.getenv(self._name, default=self._default))

    def __repr__(self) -> str:
        value: str = f"environment_variable('{self._name}'"
        if self._coercer not in (as_str, str):
            value += f", {self._coercer.__name__}"
        if _is_value(self._default):
            value += f", default={repr(self._default)}"
        value += ")"
        return value


class ValueKey(Generic[T]):
    def __init__(self, name: str) -> None:
        """
        A typed key used to access values from a ``Values`` instance.

        :param name: The key name.
        """
        self.name: str = name


class ValuesRef(ValueRef[T]):
    def __init__(self, values: Values, key: ValueKey[T]) -> None:
        """
        A ``ValueRef`` class that is backed by a ``Values`` instance.

        :param values: The backing ``Values`` instance.
        :param key: The ``ValueKey`` that identifies the value.
        """
        super().__init__(name=key.name)
        self._values: Values = values
        self._key: ValueKey[T] = key

    def get(self) -> T:
        return self._values.get(self._key)

    @property
    def has_value(self) -> bool:
        return self._values.has_value(self._key)

    def set(self, value: T) -> None:
        self._values.set(self._key, value)

    def unset(self) -> None:
        self._values.unset(self._key)


class Values:
    def __init__(self, **kwargs) -> None:
        """
        A wrapper around a ``dict[str, Any]`` that allows statically type-checked access
        and convenience methods for returning a value as a ``ValueRef``.

        :param kwargs: key/value pairs to add to the ``Values`` instance.
        """
        self._values: dict[str, Any] = {**kwargs}

    def keys(self) -> Set[str]:
        """
        :returns: A snapshot of the current keys.
        """
        return set(self._values.keys())

    def get(self, key: ValueKey[T] | str) -> T:
        """
        Get the value associated with the provided `key`. If no value is present a ``NoValueError`` is raised
        (not a ``KeyError``).

        :param key: A `ValueKey` or `str` key.
        :returns: A value of type `T`.
        """
        if isinstance(key, ValueKey):
            key = key.name
        if key not in self._values:
            raise NoValueError(f"{repr(self)} has no value associated with key '{key}'")
        return self._values[key]

    def has_value(self, key: ValueKey[T] | str) -> bool:
        """
        Check whether the provided *key*
        """
        if isinstance(key, ValueKey):
            key = key.name
        return key in self._values

    def set(self, key: ValueKey[T] | str, value: ValueOrRef[T]) -> None:
        """
        Sets or adds a `value` associated with the provided `key`.

        :param key: The key to associate the value with.
        :param value: The value to add to this ``Values`` instance.
        """
        if isinstance(key, ValueKey):
            key = key.name
        if isinstance(value, ValueProvider):
            if value.has_value:
                self._values[key] = value.get()
            else:
                self.unset(key)
        elif not _is_value(value):
            # Not typical but not impossible
            self.unset(key)
        else:
            self._values[key] = value

    def unset(self, key: ValueKey[T] | str) -> None:
        """
        Removes a value from this instance.

        :param key: The key associated with the value to remove.
        """
        if isinstance(key, ValueKey):
            key = key.name
        self._values.pop(key)

    def get_or_else(self, key: ValueKey[T] | str, default: T | None = None) -> T | None:
        """
        Gets the value associated with `key` or else `default` if no value is present.
        :param key: The key for the value.
        :param default: The default value to return if no value is present.
        :returns: The value of `default`.
        """
        return self.get(key) if self.has_value(key) else default

    def get_ref(self, key: ValueKey[T] | str) -> ValueRef[T]:
        """
        Creates a ``ValueRef`` instance that wraps the value associated with the provided `key`.

        :param key: The key of the value to wrap in a ``ValueRef``.
        :returns: A ``ValueRef`` instance.
        """
        if isinstance(key, str):
            key = ValueKey[T](key)
        return ValuesRef(self, key)

    def __repr__(self) -> str:
        return self.__class__.__name__


ValueOrRef: TypeAlias = ValueProvider[T] | T


def as_value_ref(value_or_ref: ValueOrRef[T] | None, name: str | None = None) -> ValueRef[T]:
    if isinstance(value_or_ref, ValueRef):
        return value_or_ref
    value: T | None = cast(T | None, value_or_ref)
    return ValueRef(NoValue if value is None else value, name=name)


def get_ref_value(value_or_ref: ValueOrRef[T], default: Optional[T] = None) -> Optional[T]:
    if isinstance(value_or_ref, ValueRef):
        return value_or_ref.get_or_else(default)
    return cast(T | None, value_or_ref)
