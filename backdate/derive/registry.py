"""Registry of derivations: named functions computed from facts.

A derivation is a plain function ``fn(ctx, key) -> JSON``. It must read facts
only through ``ctx`` so backdate can see what it depends on. Anything else it
reads (the clock, a random number, another table) makes recomputation give
different answers for the same inputs, and the restatement feed will show
noise.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from backdate import conf

if TYPE_CHECKING:
    from backdate.derive.context import Context

JSON = Any
DerivationFn = Callable[["Context", str], JSON]


class UnknownDerivation(LookupError):
    pass


class DuplicateDerivation(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Derivation:
    name: str
    fn: DerivationFn
    version: str
    description: str


_registry: dict[str, Derivation] = {}


def derivation(name: str, *, version: str = "1") -> Callable[[DerivationFn], DerivationFn]:
    """Register ``fn`` under ``name``.

    Bump ``version`` when the logic changes in a way that should restate old
    results. ``manage.py backdate_rebase`` marks results from older versions
    stale.
    """

    def register(fn: DerivationFn) -> DerivationFn:
        existing = _registry.get(name)
        if existing is not None and existing.fn is not fn:
            raise DuplicateDerivation(name)
        doc = (fn.__doc__ or "").strip().splitlines()
        _registry[name] = Derivation(name, fn, version, doc[0] if doc else "")
        return fn

    return register


def get(name: str) -> Derivation:
    try:
        return _registry[name]
    except KeyError:
        raise UnknownDerivation(name) from None


def all_derivations() -> list[Derivation]:
    return sorted(_registry.values(), key=lambda d: d.name)


def load_configured_modules() -> None:
    for module in conf.get_list("DERIVATION_MODULES"):
        importlib.import_module(module)
