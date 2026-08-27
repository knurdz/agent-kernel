"""JWT-authenticated chat + thread history for the AgriPilot mobile app."""

from __future__ import annotations

from typing import List, Optional

from agentkernel.auth.authoriser import Authoriser
from agentkernel.integration.thread import AgentThreadRequestHandler
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from marketplace.auth import decode_token
from marketplace.database import get_db
from marketplace.jwt_authoriser import MarketplaceJwtAuthoriser
from marketplace.models import User
from marketplace.session_identity import canonical_session_id

_bearer = HTTPBearer(auto_error=False)


class AuthenticatedMobileChatHandler(AgentThreadRequestHandler):
    """Thread-aware chat requiring JWT; session_id is derived from the authenticated user."""

    def __init__(self, authoriser: Optional[Authoriser] = None):
        super().__init__(authoriser=authoriser or MarketplaceJwtAuthoriser())

    def _require_user(
        self,
        credentials: Optional[HTTPAuthorizationCredentials],
        db: Session,
    ) -> User:
        if not credentials or not credentials.credentials:
            raise HTTPException(status_code=401, detail="Missing authorization header")
        data = decode_token(credentials.credentials)
        sub = data.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="invalid token")
        try:
            uid = int(sub)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="invalid token") from exc
        user = db.get(User, uid)
        if not user:
            raise HTTPException(status_code=401, detail="invalid token")
        return user

    @staticmethod
    def _bind_request_to_user(req, user: User) -> None:
        req.session_id = canonical_session_id(user.id)
        req.user_id = str(user.id)

    def get_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route(self.AGENTS_PATH, self.list_agents, methods=["GET"])
        router.add_api_route(
            self.CHAT_PATH,
            self._run_authenticated,
            methods=["POST"],
        )
        router.add_api_route(
            self.CHAT_MULTIPART_PATH,
            self._run_multipart_authenticated,
            methods=["POST"],
        )
        router.include_router(self._read_handler.get_router())
        return router

    async def _run_authenticated(
        self,
        body,
        credentials: HTTPAuthorizationCredentials = Depends(_bearer),
        db: Session = Depends(get_db),
    ):
        user = self._require_user(credentials, db)
        self._bind_request_to_user(body, user)
        return await super().run(body)

    async def _run_multipart_authenticated(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(_bearer),
        db: Session = Depends(get_db),
        prompt: str = Form(...),
        agent: Optional[str] = Form(None),
        session_id: Optional[str] = Form(None),
        user_id: Optional[str] = Form(None),
        group_id: Optional[str] = Form(None),
        thread_name: Optional[str] = Form(None),
        files: Optional[List[UploadFile]] = File(None),
        images: Optional[List[UploadFile]] = File(None),
    ):
        user = self._require_user(credentials, db)
        req = AgentThreadRequestHandler.BaseMultimodalRunRequest(
            prompt=prompt,
            agent=agent,
            session_id=session_id,
            user_id=user_id,
            group_id=group_id,
            thread_name=thread_name,
            files=files,
            images=images,
        )
        self._bind_request_to_user(req, user)
        return await super().run_multipart(
            prompt=req.prompt,
            agent=req.agent,
            session_id=req.session_id,
            user_id=req.user_id,
            group_id=req.group_id,
            thread_name=req.thread_name,
            files=req.files,
            images=req.images,
        )
