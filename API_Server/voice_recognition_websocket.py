from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from vosk import Model, KaldiRecognizer
import json
import os
from datetime import datetime
from pathlib import Path
import asyncio
import numpy as np

app = FastAPI()

# CORSミドルウェア設定
app.add_middleware(
   CORSMiddleware,
   allow_origins=["http://localhost:3000", "http://localhost:8000"],
   allow_credentials=True,
   allow_methods=["*"],
   allow_headers=["*"],
   expose_headers=["*"]
)

ROOT_DIR = Path(__file__).parent.absolute()
TEXT_DIR = os.path.join(ROOT_DIR, "text")
os.makedirs(TEXT_DIR, exist_ok=True)

print(f"認識結果の保存先: {TEXT_DIR}")

model = Model(os.path.join(ROOT_DIR, "model-large-ja"))

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
       
       print(f"認識結果を保存しました: {filepath}")
       return True, filename
   except Exception as e:
       print(f"保存中にエラーが発生しました: {str(e)}")
       return False, str(e)



def process_audio_data(data: bytes) -> bytes:
    try:
        # バッファサイズチェック
        if len(data) < 32768:
            return data
           
        # バイトデータをfloat32配列に変換
        float_data = np.frombuffer(data, dtype=np.float32).copy()
        
        # RMS値を計算して音量レベルを評価
        rms = np.sqrt(np.mean(float_data**2))
        print(f"元の音声データ特性 - RMS: {rms:.4f}")

        # 極端な音量不足時の処理
        if rms < 0.01:
            # 最大20倍まで増幅可能
            # 音量が非常に小さいほど、より大きく増幅
            gain = min(20.0, 1.0 / (rms + 0.0001))
            float_data *= gain
            print(f"音量を {gain:.2f}倍 に大幅増幅しました")
        elif rms < 0.05:
            # 中程度に小さい場合は10倍まで増幅
            gain = min(10.0, 0.5 / (rms + 0.001))
            float_data *= gain
            print(f"音量を {gain:.2f}倍 に増幅しました")
        
        # 増幅後の音量を再評価
        post_gain_rms = np.sqrt(np.mean(float_data**2))
        print(f"増幅後の音声データ特性 - RMS: {post_gain_rms:.4f}")

        # クリッピング防止と正規化
        max_amplitude = np.max(np.abs(float_data))
        if max_amplitude > 0:
            # より緩やかな正規化
            float_data = np.clip(float_data / max_amplitude * 0.99, -0.99, 0.99)

        # float32からint16に変換
        int_data = (float_data * 32767).astype(np.int16)
        
        return int_data.tobytes()
    
    except Exception as e:
        print(f"音声データ処理中にエラー: {str(e)}")
        return data

@app.websocket("/ws/debate/{debate_id}/")
async def websocket_endpoint(websocket: WebSocket, debate_id: str):
   await websocket.accept()
   rec = KaldiRecognizer(model, 16000)
   accumulated_text = []
   buffer = bytearray()
   CHUNK_SIZE = 32768
   silence_duration = 0
   MIN_SILENCE_DURATION = 8192  # 無音判定の閾値

   print(f"WebSocket接続開始 [{debate_id}]")

   try:
       while True:
           try:
               data = await websocket.receive_bytes()
               buffer.extend(data)

               if len(buffer) >= CHUNK_SIZE:
                   chunk = buffer[:CHUNK_SIZE]
                   buffer = buffer[CHUNK_SIZE:]
                   
                   # 無音検出
                   float_data = np.frombuffer(chunk, dtype=np.float32)
                   rms = np.sqrt(np.mean(float_data**2))
                   
                   if rms < 0.01:  # 無音判定
                       silence_duration += len(chunk)
                       if silence_duration >= MIN_SILENCE_DURATION:
                           # 長い無音があった場合、新しい認識セグメントを開始
                           rec = KaldiRecognizer(model, 16000)
                           silence_duration = 0
                   else:
                       silence_duration = 0

                   processed_data = process_audio_data(bytes(chunk))

                   if rec.AcceptWaveform(processed_data):
                       result = json.loads(rec.Result())
                       if result.get('text'):
                           text = result['text'].strip()
                           if text:
                               accumulated_text.append(text)
                               print(f"認識されたテキスト [{debate_id}]: {text}")
                               await websocket.send_json({
                                   "type": "final",
                                   "text": text,
                                   "debate_id": debate_id
                               })
                   else:
                       partial = json.loads(rec.PartialResult())
                       if partial.get('partial'):
                           partial_text = partial['partial'].strip()
                           if partial_text:
                               print(f"部分的な認識テキスト [{debate_id}]: {partial_text}")
                               await websocket.send_json({
                                   "type": "partial",
                                   "text": partial_text,
                                   "debate_id": debate_id
                               })

           except json.JSONDecodeError as e:
               print(f"JSON解析エラー [{debate_id}]: {str(e)}")
               continue
           except ConnectionResetError:
               print(f"接続リセット [{debate_id}]")
               break
           except Exception as e:
               print(f"データ処理エラー [{debate_id}]: {str(e)}")
               break

   except WebSocketDisconnect as e:
       print(f"WebSocket切断 [{debate_id}]: コード {e.code}")
   except Exception as e:
       print(f"予期せぬエラー [{debate_id}]: {str(e)}")
   finally:
       # 残りのバッファを処理
       if buffer and len(buffer) >= CHUNK_SIZE:
           try:
               processed_data = process_audio_data(bytes(buffer))
               if rec.AcceptWaveform(processed_data):
                   result = json.loads(rec.Result())
                   if result.get('text'):
                       text = result['text'].strip()
                       if text:
                           accumulated_text.append(text)
           except Exception as e:
               print(f"最終バッファ処理エラー [{debate_id}]: {str(e)}")

       if accumulated_text:
           full_text = " ".join(accumulated_text)
           success, filename = save_recognition_result(full_text)
           if success:
               try:
                   await websocket.send_json({
                       "type": "save",
                       "message": f"認識結果を保存しました: {filename}",
                       "debate_id": debate_id
                   })
               except:
                   print(f"保存通知の送信に失敗 [{debate_id}]")
       try:
           await websocket.close()
           print(f"WebSocket接続を終了 [{debate_id}]")
       except:
           pass
@app.websocket("/ws/debate/{debate_id}/")
async def websocket_endpoint(websocket: WebSocket, debate_id: str):
   await websocket.accept()
   rec = KaldiRecognizer(model, 16000)
   accumulated_text = []
   buffer = bytearray()
   CHUNK_SIZE = 32768  # バッファサイズを32KBに増加

   print(f"WebSocket接続開始 [{debate_id}]")

   try:
       while True:
           try:
               data = await websocket.receive_bytes()
               buffer.extend(data)

               # バッファが十分なサイズになったら処理
               if len(buffer) >= CHUNK_SIZE:
                   chunk = buffer[:CHUNK_SIZE]
                   buffer = buffer[CHUNK_SIZE:]
                   
                   processed_data = process_audio_data(bytes(chunk))

                   if rec.AcceptWaveform(processed_data):
                       result = json.loads(rec.Result())
                       if result.get('text'):
                           text = result['text'].strip()
                           if text:  # 空文字列でない場合のみ処理
                               accumulated_text.append(text)
                               print(f"認識されたテキスト [{debate_id}]: {text}")
                               await websocket.send_json({
                                   "type": "final",
                                   "text": text,
                                   "debate_id": debate_id
                               })
                   else:
                       partial = json.loads(rec.PartialResult())
                       if partial.get('partial'):
                           partial_text = partial['partial'].strip()
                           if partial_text:  # 空文字列でない場合のみ処理
                               print(f"部分的な認識テキスト [{debate_id}]: {partial_text}")
                               await websocket.send_json({
                                   "type": "partial",
                                   "text": partial_text,
                                   "debate_id": debate_id
                               })

           except json.JSONDecodeError as e:
               print(f"JSON解析エラー [{debate_id}]: {str(e)}")
               continue
           except ConnectionResetError:
               print(f"接続リセット [{debate_id}]")
               break
           except Exception as e:
               print(f"データ処理エラー [{debate_id}]: {str(e)}")
               break

   except WebSocketDisconnect as e:
       print(f"WebSocket切断 [{debate_id}]: コード {e.code}")
   except Exception as e:
       print(f"予期せぬエラー [{debate_id}]: {str(e)}")
   finally:
       # 残りのバッファを処理
       if buffer:
           try:
               processed_data = process_audio_data(bytes(buffer))
               if rec.AcceptWaveform(processed_data):
                   result = json.loads(rec.Result())
                   if result.get('text'):
                       text = result['text'].strip()
                       if text:
                           accumulated_text.append(text)
           except Exception as e:
               print(f"最終バッファ処理エラー [{debate_id}]: {str(e)}")

       if accumulated_text:
           full_text = " ".join(accumulated_text)
           success, filename = save_recognition_result(full_text)
           if success:
               try:
                   await websocket.send_json({
                       "type": "save",
                       "message": f"認識結果を保存しました: {filename}",
                       "debate_id": debate_id
                   })
               except:
                   print(f"保存通知の送信に失敗 [{debate_id}]")
       try:
           await websocket.close()
           print(f"WebSocket接続を終了 [{debate_id}]")
       except:
           pass

@app.get("/")
async def read_root():
   return {"status": "OK", "message": "Speech Recognition API is running"}

if __name__ == "__main__":
   import uvicorn
   uvicorn.run(app, host="0.0.0.0", port=8002)