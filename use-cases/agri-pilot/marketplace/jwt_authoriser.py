"""JWT Authoriser for Agent Kernel thread and mobile chat routes."""

from __future__ import annotations

from typing import Optional

from agentkernel.auth.authoriser import Authoriser

from marketplace.auth import decode_token


class MarketplaceJwtAuthoriser(Authoriser):
    """Resolve Bearer JWT to marketplace user id (string sub claim)."""

    def authorise(self, token: str) -> Optional[str]:
        try:
            data = decode_token(token)
        except Exception:
            return None
        sub = data.get("sub")
        if sub is None:
            return None
        return str(sub)
