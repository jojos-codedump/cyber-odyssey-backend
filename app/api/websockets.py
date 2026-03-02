from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List, Dict
import logging
from datetime import datetime

# Initialize router
router = APIRouter(tags=["Real-Time Operations"])
logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    Manages active WebSocket connections for real-time event oversight.
    This ensures Administrators possess a complete, real-time view of the event[cite: 19].
    """
    def __init__(self):
        # Stores all active connections
        self.active_connections: List[WebSocket] = []
        # Maps specific client IDs (like Admin User UIDs) to their connections
        self.admin_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        """Accepts a new WebSocket connection and stores it."""
        await websocket.accept()
        self.admin_connections[client_id] = websocket
        self.active_connections.append(websocket)
        
        # Send an initial handshake payload
        await self.send_personal_message({
            "type": "connection_established",
            "message": "Connected to Cyber Odyssey Live Dashboard",
            "client_id": client_id,
            "timestamp": datetime.now().isoformat()
        }, websocket)
        logger.info(f"Admin client #{client_id} connected. Total active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket, client_id: str):
        """Removes a WebSocket connection upon disconnect."""
        if client_id in self.admin_connections:
            del self.admin_connections[client_id]
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"Admin client #{client_id} disconnected.")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Sends a JSON message to a specific client."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Failed to send personal message: {e}")

    async def broadcast(self, message: dict):
        """
        Broadcasts a JSON message to all connected Administrator clients.
        Used primarily for broadcasting database INSERT and UPDATE events.
        """
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # If a connection drops ungracefully, flag it for removal
                dead_connections.append(connection)
                
        # Clean up dead connections
        for dead_conn in dead_connections:
            if dead_conn in self.active_connections:
                self.active_connections.remove(dead_conn)


# Instantiate the global connection manager
manager = ConnectionManager()


@router.websocket("/admin/{client_id}")
async def websocket_admin_endpoint(websocket: WebSocket, client_id: str):
    """
    WebSocket endpoint for the Admin Master Dashboard.
    Frontend clients will connect to ws://<backend-url>/ws/admin/<their-uid>
    """
    await manager.connect(websocket, client_id)
    try:
        while True:
            # The dashboard primarily listens, but we keep the loop alive 
            # to handle incoming pings or specific manual refresh requests.
            data = await websocket.receive_text()
            
            # Simple acknowledgment of received client messages
            await manager.send_personal_message({
                "type": "ack", 
                "message": f"Server received: {data}"
            }, websocket)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, client_id)


# ---------------------------------------------------------
# UTILITY BROADCAST FUNCTIONS (Called by routes.py)
# ---------------------------------------------------------

async def broadcast_scan(scan_data: dict):
    """
    Triggered by the /attendance/scan REST endpoint.
    Pushes live attendance updates to the Admin dashboard.
    """
    payload = {
        "type": "new_scan",
        "timestamp": datetime.now().isoformat(),
        "data": scan_data
    }
    await manager.broadcast(payload)


async def broadcast_capacity_alert(event_id: str, current_capacity: int, status: str):
    """
    Triggered by the registration route if an event transitions 
    into 'Waitlisting' mode.
    """
    payload = {
        "type": "capacity_alert",
        "event_id": event_id,
        "current_capacity": current_capacity,
        "status": status,
        "timestamp": datetime.now().isoformat()
    }
    await manager.broadcast(payload)