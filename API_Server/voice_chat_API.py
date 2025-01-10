from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
import json
from typing import Dict, Set, Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本番環境では具体的なオリジンを指定
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.rooms: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: str, user: Optional[str] = None):
        await websocket.accept()
        if room_id not in self.rooms:
            self.rooms[room_id] = set()
        self.rooms[room_id].add(websocket)
        print(f"User {user} connected to room {room_id}")

    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.rooms:
            self.rooms[room_id].discard(websocket)
            if not self.rooms[room_id]:
                del self.rooms[room_id]

    async def broadcast_to_room(self, message: dict, room_id: str, sender: WebSocket):
        if room_id in self.rooms:
            for connection in self.rooms[room_id]:
                if connection != sender:
                    await connection.send_json(message)

manager = ConnectionManager()

@app.websocket("/ws/debate/{debate_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
    debate_id: str, 
    user: Optional[str] = Query(None)
):
    try:
        await manager.connect(websocket, debate_id, user)
        
        while True:
            data = await websocket.receive_json()
            # ユーザー情報を含めてブロードキャスト
            broadcast_data = {**data, "sender": user}
            await manager.broadcast_to_room(broadcast_data, debate_id, websocket)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, debate_id)
        # 切断通知を送信
        await manager.broadcast_to_room(
            {
                "type": "user_leave", 
                "user": user,
                "debate_id": debate_id
            },
            debate_id,
            websocket
        )
    except Exception as e:
        print(f"WebSocket error: {e}")
        await websocket.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)