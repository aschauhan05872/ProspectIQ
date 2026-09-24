"""Company news/funding fetch errors."""

from __future__ import annotations


class CompanyNewsError(Exception):
    permanent: bool = False


class PermanentNewsError(CompanyNewsError):
    permanent = True


class RetryableNewsError(CompanyNewsError):
    permanent = False
