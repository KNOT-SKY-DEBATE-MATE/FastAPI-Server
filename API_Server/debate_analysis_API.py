# debate_analysis_API.py
import traceback
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.websockets import WebSocketDisconnect
from openai import OpenAI

import json
import asyncio
from datetime import datetime
import os
from pathlib import Path

app = FastAPI()

# CORSミドルウェア設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 設定の読み込み
ROOT_DIR = Path(__file__).parent.absolute()
with open(os.path.join(ROOT_DIR, "analysis_conf.json")) as f:
    CONFIGS = json.load(f)

# OpenAIクライアントの初期化
client = OpenAI(api_key=CONFIGS['OPENAI.API_KEY'])

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "analyze_discussion",
            "description": "議論内容を分析し、要約、提案、批判、評価、ポリシー違反の警告を提供します。",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "議論全体の簡潔な要約。"
                    },
                    "suggestions": {
                        "type": "string",
                        "description": "議論の方向性や内容に関する提案。"
                    },
                    "criticisms": {
                        "type": "string",
                        "description": "論理的な洞察や発話内容の間違いに関する批判。"
                    },
                    "evaluations": {
                        "type": "string",
                        "description": "発話内容に対する批判を踏まえた評価。"
                    },
                    "warnings": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "ポリシー違反やメンバーの行動に関する警告。"
                    }
                },
                "required": ["summary", "suggestions", "evaluations"]
            }
        }
    }
]

async def analyze_debate_content(messages):
    try:
        formatted_messages = "\n".join([
            f"{msg['author']}: {msg['content']}" 
            for msg in messages
        ])

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=CONFIGS['OPENAI.CHAT_MODEL'],
            messages=[
                {
                    "role": "system",
                    "content": (
                        "あなたは議長です。"
                        "以下のポリシーに従って、議論を分析し、要約してください。"
                        "議長ポリシー："
                        "- 感情的にならず、中立的であること"
                        "- 論理的で批判的な視点を持つこと"
                        "- 議論メンバーの意見を適切に要約、批判、評価すること"
                        "- 議題から外れた発言があれば指摘すること"
                    )
                },
                {
                    "role": "user",
                    "content": f"次の議論を分析してください：\n{formatted_messages}"
                }
            ],
            tools=TOOLS,
            temperature=0.7,
        )

        if response.choices[0].message.tool_calls:
            return json.loads(response.choices[0].message.tool_calls[0].function.arguments)
        return {"summary": response.choices[0].message.content}

    except Exception as e:
        print(f"分析エラー: {str(e)}")
        return {"error": str(e)}
        



@app.websocket("/ws/debate/analysis/{debate_id}/")
async def websocket_endpoint(websocket: WebSocket, debate_id: str):
    await websocket.accept()
    print(f"Analysis WebSocket connected: {debate_id}")
    
    # 既に分析したメッセージを追跡するセットを追加
    analyzed_messages = set()
    
    try:
        while True:
            data = await websocket.receive_json()
            print(f"受信データ: {data}") 
            messages = data.get("messages", [])
            
            # メッセージの一意性を確認するためのハッシュを生成
            message_hashes = [hash((msg['content'], msg['author'], msg['timestamp'])) for msg in messages]
            
            # 未分析のメッセージのみを処理
            unique_messages = [
                msg for msg, msg_hash in zip(messages, message_hashes) 
                if msg_hash not in analyzed_messages
            ]
            
            if unique_messages:
                print(f"ディベート {debate_id} のメッセージを分析中")
                print(f"メッセージ: {unique_messages}")
                analysis_result = await analyze_debate_content(unique_messages)

                print(f"分析結果: {analysis_result}") 
                
                # 分析済みメッセージのハッシュを追加
                analyzed_messages.update(message_hashes)
                
                # 分析結果を送信
                await websocket.send_json({
                    "type": "analysis",
                    "result": analysis_result,
                    "timestamp": datetime.now().isoformat()
                })
                print(f"ディベート {debate_id} の分析を送信")
            else:
                print("新しいメッセージがないため分析をスキップ")
    
    except WebSocketDisconnect:
        print(f"Client disconnected normally from debate {debate_id}")
    except Exception as e:
        print(f"ディベート {debate_id} の詳細な分析エラー: {traceback.format_exc()}")
    finally:
        if not websocket.client_state.DISCONNECTED:
            await websocket.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)