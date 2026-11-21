"""Typed access to the BACKDATE settings dict."""

from __future__ import annotations

from typing import cast

from django.conf import settings


def get_int(name: str) -> int:
    return int(settings.BACKDATE[name])


def get_list(name: str) -> list[str]:
    return list(cast("list[str]", settings.BACKDATE[name]))


def get_bool(name: str) -> bool:
    return bool(settings.BACKDATE[name])
