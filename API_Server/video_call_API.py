# API_Server/video_call_API.py

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import json
from typing import Dict, Set

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

class ConnectionManager:
    def __init__(self):
        # 部屋ごとの接続を管理
        self.rooms: Dict[str, Dict[str, Dict]] = {}

    async def connect(self, websocket: WebSocket, room_id: str, user: str):
        await websocket.accept()
        
        if room_id not in self.rooms:
            self.rooms[room_id] = {}
        
        self.rooms[room_id][user] = {
            "websocket": websocket,
            "camera_on": False
        }
        
        # カメラステータスの変更をブロードキャスト
        await self.broadcast({
            "type": "user_status_change", 
            "user": user,
            "camera_on": False
        }, room_id, exclude_user=user)
        
        print(f"ユーザー {user} が部屋 {room_id} に接続しました")

    def disconnect(self, room_id: str, user: str):
        if room_id in self.rooms and user in self.rooms[room_id]:
            del self.rooms[room_id][user]
            print(f"ユーザー {user} が部屋 {room_id} から切断されました")

    async def broadcast(self, message: dict, room_id: str, exclude_user: str = None):
        if room_id not in self.rooms:
            return

        for user, connection in self.rooms[room_id].items():
            if exclude_user is None or user != exclude_user:
                try:
                    await connection["websocket"].send_json(message)
                except Exception as e:
                    print(f"ブロードキャスト中にエラー: {e}")

    async def update_camera_status(self, room_id: str, user: str, camera_on: bool):
        if room_id in self.rooms and user in self.rooms[room_id]:
            self.rooms[room_id][user]["camera_on"] = camera_on
            await self.broadcast({
                "type": "user_status_change", 
                "user": user,
                "camera_on": camera_on
            }, room_id, exclude_user=user)

manager = ConnectionManager()

@app.websocket("/ws/debate/{debate_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
    debate_id: str, 
    user: str
):
    try:
        await manager.connect(websocket, debate_id, user)
        
        while True:
            try:
                data = await websocket.receive_json()
                
                # 送信者情報を追加
                data['sender'] = user
                
                # 特定のメッセージタイプのみブロードキャスト
                broadcast_types = ['offer', 'answer', 'ice_candidate', 'camera_status']
                if data.get('type') in broadcast_types:
                    await manager.broadcast(data, debate_id, exclude_user=user)
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"メッセージ処理中にエラー: {e}")
                break
    
    except WebSocketDisconnect:
        manager.disconnect(debate_id, user)
    
    finally:
        try:
            await websocket.close()
        except:
            pass
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)