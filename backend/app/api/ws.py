"""WebSocket endpoint streaming the full network state every tick."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.engine import get_engine
from app.logging_config import get_logger

log = get_logger("netmedic.ws")

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @property
    def count(self) -> int:
        return len(self._connections)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        log.info("[WS] Client connected (%d active)", self.count)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)
        log.info("[WS] Client disconnected (%d active)", self.count)

    async def broadcast(self, message: dict[str, Any]) -> None:
        if not self._connections:
            return
        stale: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 - client went away mid-send
                stale.append(ws)
        for ws in stale:
            await self.disconnect(ws)


manager = ConnectionManager()


@router.websocket("/ws/network")
async def network_stream(websocket: WebSocket) -> None:
    engine = get_engine()
    await manager.connect(websocket)
    try:
        # Send the current state immediately so the dashboard renders without waiting a tick.
        await websocket.send_json(engine.state_message())
        while True:
            # Clients may send pings; we only need to detect disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        log.exception("[WS] Connection error")
    finally:
        await manager.disconnect(websocket)
