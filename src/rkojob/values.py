from __future__ import annotations

import os
from typing import (
    Any,
    Callable,
    Final,
    Generic,
    Optional,
    Protocol,
    TypeAlias,
    TypeGuard,
    TypeVar,
    cast,
    final,
    runtime_checkable,
)

T = TypeVar("T")
U = TypeVar("U")
T_co = TypeVar("T_co", covariant=True)
T_contra = TypeVar("T_contra", contravariant=True)


@final
class _NoValue:
    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "No Value"


NoValue: Final[_NoValue] = _NoValue()


def _is_value(value: T | _NoValue) -> TypeGuard[T]:
    return value is not NoValue


@runtime_checkable
class ValueProvider(Protocol[T_co]):
    def get(self) -> T_co: ...

    @property
    def has_value(self) -> bool: ...


@runtime_checkable
class ValueConsumer(Protocol[T_contra]):
    def set(self, value: T_contra) -> None: ...

    def unset(self) -> None: ...


class ValueRef(Generic[T], ValueProvider[T], ValueConsumer[T]):
    def __init__(self, value: T | _NoValue = NoValue, name: str | None = None) -> None:
        self._value: T | _NoValue = NoValue
        self._name: str | None = name

        if _is_value(value):
            self.value = value

    def get(self) -> T:
        if not self.has_value:
            raise ValueError(f"{repr(self)} has no value")
        return cast(T, self._value)

    @property
    def has_value(self) -> bool:
        return _is_value(self._value)

    def set(self, value: T) -> None:
        self._value = value

    def unset(self) -> None:
        self._value = NoValue

    @property
    def value(self) -> T:
        return self.get()

    @value.setter
    def value(self, value: T) -> None:
        self.set(value)

    def get_or_else(self, default: T | None) -> T | None:
        return self.get() if self.has_value else default

    @property
    def name(self) -> Optional[str]:
        return self._name

    def map(self, func: Callable[[T], U]) -> MappedValueProvider[U]:
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
        self._func: Callable[[T], U] = func
        self._provider: ValueProvider[T] | None = provider

    def get(self) -> U:
        if self._provider is None or not self.has_value:
            raise ValueError(f"{repr(self)} has no value")
        return self._func(self._provider.get())

    @property
    def has_value(self) -> bool:
        return self._provider is not None and self._provider.has_value

    @property
    def value(self) -> U:
        return self.get()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}"


class ComputedValue(ValueProvider[T]):
    def __init__(self, func: Callable[[], T], name: str | None = None) -> None:
        self._func: Callable[[], T] = func
        self._name = name

    @property
    def value(self) -> T:
        return self.get()

    def get(self) -> T:
        if self._func is None:
            raise ValueError(f"{repr(self)} has no value")
        return self._func()

    @property
    def has_value(self) -> bool:
        return self._func is not None

    def __repr__(self) -> str:
        if self._name:
            return f"{self.__class__.__name__}(name={self._name})"
        return f"{self.__class__.__name__}"


class EnvironmentVariable(ValueProvider[T_co]):
    def __init__(self, name: str, converter: Callable[[str], T_co]) -> None:
        self._name: str = name
        self._converter: Callable[[str], T_co] = converter

    def get(self) -> T_co:
        value: str | _NoValue = os.getenv(self._name, default=NoValue)
        if _is_value(value):
            return self._converter(value)
        raise ValueError(f"Environment variable '{self._name}' is not set.")

    @property
    def has_value(self) -> bool:
        return _is_value(os.getenv(self._name, default=NoValue))


class ValueKey(Generic[T]):
    def __init__(self, name: str) -> None:
        self.name: str = name


class ValuesRef(ValueRef[T]):
    def __init__(self, values: Values, key: ValueKey[T]) -> None:
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
        self._values: dict[str, Any] = {**kwargs}

    def get(self, key: ValueKey[T] | str) -> T:
        if isinstance(key, ValueKey):
            key = key.name
        if key not in self._values:
            raise ValueError(f"{repr(self)} has no value associated with key '{key}'")
        return self._values[key]

    def has_value(self, key: ValueKey[T] | str) -> bool:
        if isinstance(key, ValueKey):
            key = key.name
        return key in self._values

    def set(self, key: ValueKey[T] | str, value: ValueOrRef[T]) -> None:
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
        if isinstance(key, ValueKey):
            key = key.name
        self._values.pop(key)

    def get_or_else(self, key: ValueKey[T] | str, default: T | None = None) -> T | None:
        return self.get(key) if self.has_value(key) else default

    def get_ref(self, key: ValueKey[T] | str) -> ValueRef[T]:
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
