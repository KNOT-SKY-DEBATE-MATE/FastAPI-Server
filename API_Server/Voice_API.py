from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from vosk import Model, KaldiRecognizer
import json
import os
from datetime import datetime
from pathlib import Path
import asyncio

app = FastAPI()

# CORSミドルウェア設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000"],  # フロントエンドのオリジンを設定
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

ROOT_DIR = Path(__file__).parent.absolute()
TEXT_DIR = os.path.join(ROOT_DIR, "text")
os.makedirs(TEXT_DIR, exist_ok=True)

print(f"認識結果の保存先: {TEXT_DIR}")  # 保存先ディレクトリの確認用

model = Model(os.path.join(ROOT_DIR, "model-large-ja"))

# 認識結果をJSONファイルとして保存する関数
def save_recognition_result(text: str) -> tuple[bool, str]:
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'speech_recognition_{timestamp}.json'
        filepath = os.path.join(TEXT_DIR, filename)
        
        data = {
            "timestamp": datetime.now().isoformat(),
            "text": text
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"認識結果を保存しました: {filepath}")  # 保存確認用
        return True, filename
    except Exception as e:
        print(f"保存中にエラーが発生しました: {str(e)}")  # エラー確認用
        return False, str(e)

# WebSocketエンドポイント
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()  # WebSocket接続を受け入れる
    rec = KaldiRecognizer(model, 16000)
    accumulated_text = []  # 認識結果を蓄積

    try:
        while True:
            data = await websocket.receive_bytes()  # 音声データを受信

            # 音声データを処理して認識
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                if result.get('text'):
                    text = result['text']
                    accumulated_text.append(text)  # 認識結果を蓄積
                    print(f"認識されたテキスト: {text}")  # ログに表示
                    await websocket.send_json({  # クライアントに最終認識結果を送信
                        "type": "final",
                        "text": text
                    })
            else:
                partial = json.loads(rec.PartialResult())
                if partial.get('partial'):
                    partial_text = partial['partial']
                    print(f"部分的な認識テキスト: {partial_text}")  # 部分的なテキストをログに表示
                    await websocket.send_json({  # 部分認識結果をクライアントに送信
                        "type": "partial",
                        "text": partial_text
                    })
    except Exception as e:
        print(f"WebSocketエラー: {str(e)}")
    finally:
        # 接続が終了したときに蓄積したテキストを保存
        if accumulated_text:
            full_text = " ".join(accumulated_text)
            success, filename = save_recognition_result(full_text)
            if success:
                try:
                    await websocket.send_json({  # 保存成功のメッセージをクライアントに送信
                        "type": "save",
                        "message": f"認識結果を保存しました: {filename}"
                    })
                except:
                    pass  # 接続がすでに閉じられている場合
        try:
            await websocket.close()  # WebSocket接続を閉じる
        except:
            pass

@app.get("/")
async def read_root():
    return {"status": "OK", "message": "Speech Recognition API is running"}

# FastAPIアプリをUvicornで実行
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
