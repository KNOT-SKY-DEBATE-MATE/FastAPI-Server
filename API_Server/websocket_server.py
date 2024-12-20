# FastAPI WebSocket Server (websocket_server.py)
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List
import json
from datetime import datetime
from pydantic import BaseModel

app = FastAPI()

# CORSの設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000"],  # フロントエンドのオリジンを設定
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)


# dabareroomごとの接続管理を行うクラス
class DebateRoom:
    def __init__(self):
        self.connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.connections:
            self.connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.connections:
            await connection.send_json(message)


# DebateRoom管理
debate_rooms: Dict[int, DebateRoom] = {}

@app.websocket("ws/debate/{debate_id}")
async def websocket_endpoint(websocket: WebSocket, debate_id: int):
    # debate_room が存在しない場合は作成
    if debate_id not in debate_rooms:
        debate_rooms[debate_id] = DebateRoom()

    room = debate_rooms[debate_id]
    await room.connect(websocket)

    try:
        while True:
            date = await websocket.receive_text()
            message_date = json.loads(date)

            # masseageにtimestampを追加
            message_date["timestamp"] = datetime.now().strftime('%Y-%m-%d_%H:%M %S')


            # roommemberにブロードキャスト
            await   room.broadcast(message_date)

    except WebSocketDisconnect:
        room.disconnect(websocket)
    except Exception as e:
        print(f"Error: {str(e)}")
        room.disconnect(websocket)

