from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Set
import json
import logging
from datetime import datetime

# ロギングの設定
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORSの設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, debate_id: str):
        await websocket.accept()
        if debate_id not in self.active_connections:
            self.active_connections[debate_id] = set()
        self.active_connections[debate_id].add(websocket)
        logger.info(f"Client connected to debate {debate_id}. Total connections: {len(self.active_connections[debate_id])}")

    async def disconnect(self, websocket: WebSocket, debate_id: str):
        try:
            if debate_id in self.active_connections:
                self.active_connections[debate_id].discard(websocket)
                if not self.active_connections[debate_id]:
                    del self.active_connections[debate_id]
                logger.info(f"Client disconnected from debate {debate_id}. Remaining connections: {len(self.active_connections.get(debate_id, set()))}")
        except Exception as e:
            logger.error(f"Error in disconnect: {e}")

    async def broadcast(self, message: dict, debate_id: str, sender_socket: WebSocket):
        if not message.get('username'):
            logger.warning(f"Received message with empty username for debate {debate_id}")
            return

        if debate_id in self.active_connections:
            dead_connections = set()
            for connection in self.active_connections[debate_id].copy():
                if connection != sender_socket:  # 送信者には送り返さない
                    try:
                        await connection.send_json(message)
                    except WebSocketDisconnect:
                        dead_connections.add(connection)
                    except Exception as e:
                        logger.error(f"Error broadcasting to client: {e}")
                        dead_connections.add(connection)

            # 切断された接続を削除
            for dead_connection in dead_connections:
                await self.disconnect(dead_connection, debate_id)

manager = ConnectionManager()

@app.websocket("/ws/debate/{debate_id}/")
async def websocket_endpoint(websocket: WebSocket, debate_id: str):
    await manager.connect(websocket, debate_id)
    
    try:
        logger.debug(f"New connection established for debate: {debate_id}")
        
        while True:
            try:
                message = await websocket.receive_json()
                if not isinstance(message, dict):
                    logger.error(f"Invalid message format received: {message}")
                    continue

                # タイムスタンプの追加
                message["timestamp"] = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                logger.debug(f"Received message in debate {debate_id}: {message}")
                
                # メッセージのブロードキャスト
                await manager.broadcast(message, debate_id, websocket)
                
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected")
                await manager.disconnect(websocket, debate_id)
                break
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {e}")
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                await manager.disconnect(websocket, debate_id)
                break
                
    except Exception as e:
        logger.error(f"Connection error: {e}")
        await manager.disconnect(websocket, debate_id)
        if websocket.client_state.CONNECTED:
            await websocket.close()

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
        "connections": {
            debate_id: len(connections) 
            for debate_id, connections in manager.active_connections.items()
        }
    }