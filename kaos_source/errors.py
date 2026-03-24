from __future__ import annotations

from typing import Any

from kaos_core.exceptions import KaosCoreError
from kaos_core.types.content import KaosModel


class SourceErrorInfo(KaosModel):
    error_type: str
    message: str
    retryable: bool = False
    details: dict[str, Any]


class SourceError(KaosCoreError):
    retryable = False

    def to_info(self) -> SourceErrorInfo:
        return SourceErrorInfo(
            error_type=self.__class__.__name__,
            message=self.message,
            retryable=self.retryable,
            details=self.details,
        )


class SourceNotFoundError(SourceError):
    pass


class SourceAccessError(SourceError):
    pass


class SourcePolicyError(SourceError):
    pass


class SourceMaterializationError(SourceError):
    pass


class SourceValidationError(SourceError):
    pass


class SourceTransientError(SourceError):
    retryable = True
