"""Exceptions for the Data Collection Engine."""

from __future__ import annotations


class ProviderError(RuntimeError):
    """A single provider failed to fetch data.

    Raised for both transient failures (network, timeout, rate limit) and
    permanent ones (missing credentials, malformed response); the fallback
    chain treats every `ProviderError` as "try the next provider".
    """


class ProviderNotConfiguredError(ProviderError):
    """A provider is missing required credentials (e.g. an API key)."""


class AllProvidersFailedError(RuntimeError):
    """Every provider in a fallback chain failed, and no cached value existed."""
