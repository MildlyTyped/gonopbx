"""
Core API router.

Covers the root SPA endpoint, system health check, call origination,
active-call listing, and the live-update WebSocket.  The AMI client
reference is injected by :class:`~modules.core.CoreModule` during startup.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from auth import get_current_user, JWT_SECRET, JWT_ALGORITHM
from database import User
from version import VERSION

logger = logging.getLogger(__name__)

router = APIRouter()

# AMI client reference — injected via set_ami_client() in CoreModule.on_module_startup.
_ami_client = None


def set_ami_client(client) -> None:
    global _ami_client
    _ami_client = client


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

class OriginateRequest(BaseModel):
    extension: str
    number: str


@router.get("/")
async def root():
    """Serve the SPA index page, or API version info when no frontend is built."""
    from pbxgen.module import module_registry
    if module_registry._spa_index_html is not None:
        return HTMLResponse(module_registry._spa_index_html)
    return {
        "name": "Asterisk PBX GUI API",
        "version": VERSION,
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/api/health", tags=["Core"])
async def health_check():
    """System health check."""
    asterisk_status = "disconnected"
    if _ami_client and _ami_client.connected:
        asterisk_status = "connected"
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "api": "running",
            "asterisk": asterisk_status,
            "database": "connected",
        },
    }


@router.post("/api/calls/originate", tags=["Calls"])
async def originate_call(
    req: OriginateRequest,
    current_user: User = Depends(get_current_user),
):
    """Originate a call: rings the extension first, then dials the number."""
    if not _ami_client or not _ami_client.connected:
        raise HTTPException(status_code=503, detail="Asterisk not connected")
    try:
        await _ami_client.send_action(
            "Originate",
            Channel=f"PJSIP/{req.extension}",
            Exten=req.number,
            Context="from-internal",
            Priority="1",
            CallerID=req.extension,
            Timeout="30000",
            Async="true",
        )
        return {"status": "ok", "message": f"Calling {req.number} from {req.extension}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/calls/active", tags=["Calls"])
async def get_active_calls(current_user: User = Depends(get_current_user)):
    """Get currently active calls."""
    if _ami_client and _ami_client.connected:
        calls = await _ami_client.get_active_channels()
        return {
            "calls": calls,
            "count": len(calls),
            "timestamp": datetime.utcnow().isoformat(),
        }
    return {
        "calls": [],
        "count": 0,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(None)):
    """WebSocket connection for real-time updates."""
    if token:
        from jose import JWTError, jwt as jose_jwt
        try:
            jose_jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except JWTError:
            await websocket.close(code=4001)
            return
    else:
        await websocket.close(code=4001)
        return

    await manager.connect(websocket)
    try:
        await websocket.send_json({
            "type": "connection",
            "status": "connected",
            "timestamp": datetime.utcnow().isoformat(),
        })
        if _ami_client:
            calls = await _ami_client.get_active_channels()
            await websocket.send_json({
                "type": "active_calls",
                "active_calls": calls,
                "timestamp": datetime.utcnow().isoformat(),
            })
        while True:
            data = await websocket.receive_text()
            logger.info(f"Received WebSocket message: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)
