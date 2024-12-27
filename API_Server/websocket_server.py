from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Set
import json
import logging
from datetime import datetime

# ロギングの設定
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORSの設定を更新
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# デバートルームごとの接続管理
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, debate_id: str):
        await websocket.accept()
        if debate_id not in self.active_connections:
            self.active_connections[debate_id] = set()
        self.active_connections[debate_id].add(websocket)
        logger.info(f"Client connected to debate {debate_id}. Total connections: {len(self.active_connections[debate_id])}")

    def disconnect(self, websocket: WebSocket, debate_id: str):
        if debate_id in self.active_connections:
            self.active_connections[debate_id].discard(websocket)
            if not self.active_connections[debate_id]:
                del self.active_connections[debate_id]
            logger.info(f"Client disconnected from debate {debate_id}. Remaining connections: {len(self.active_connections.get(debate_id, set()))}")

    async def broadcast(self, message: dict, debate_id: str):
        if debate_id in self.active_connections:
            for connection in self.active_connections[debate_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to client: {e}")
                    await self.disconnect(connection, debate_id)

manager = ConnectionManager()

@app.websocket("/ws/debate/{debate_id}/")
async def websocket_endpoint(websocket: WebSocket, debate_id: str):
    try:
        await manager.connect(websocket, debate_id)
        logger.debug(f"New connection established for debate: {debate_id}")
        
        while True:
            try:
                data = await websocket.receive_text()
                message_data = json.loads(data)
                message_data["timestamp"] = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                logger.debug(f"Received message in debate {debate_id}: {message_data}")
                
                await manager.broadcast(message_data, debate_id)
                
            except WebSocketDisconnect:
                manager.disconnect(websocket, debate_id)
                break
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON received: {e}")
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                break
                
    except Exception as e:
        logger.error(f"Connection error: {e}")
        manager.disconnect(websocket, debate_id)

# ヘルスチェックエンドポイント
@app.get("/health")
async def health_check():
    return {"status": "healthy", "connections": {
        debate_id: len(connections) 
        for debate_id, connections in manager.active_connections.items()
    }}