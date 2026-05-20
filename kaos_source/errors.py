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


class SourceAntiBotChallengeError(SourceError):
    """Raised when an HTTP response looks like an anti-bot challenge page.

    Signals to the caller that the URL is protected by a bot-detection
    or interstitial system (Cloudflare, hCaptcha/reCAPTCHA, etc.) and
    that a browser-driven retry (Playwright) is the canonical next step.

    The ``details`` dict carries:

    - ``locator``: the URL that triggered the challenge
    - ``http_status``: response status code (may be 200 for HTML
      challenges, or 403/451 for explicit refusals)
    - ``fingerprint``: short label of the matched pattern (e.g.
      ``"cloudflare"``, ``"captcha"``, ``"http_403"``)
    """

    retryable = False
