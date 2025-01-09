import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor

def run_server(command):
    try:
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running server: {e}")
    except KeyboardInterrupt:
        print("Server stopped by user")

def main():
    # サーバーコマンドのリスト
    commands = [
        "uvicorn chat_websocket:app --host localhost --port 8001 --reload",
        "uvicorn voice_recognition_websocket:app --host 0.0.0.0 --port 8002 --reload",
        "uvicorn voice_call_API:app --host 0.0.0.0 --port 8003 --reload",
        "uvicorn video_call_API:app --host 0.0.0.0 --port 8004 --reload",

    ]

    # ProcessPoolExecutorを使用して複数のサーバーを並行して実行
    with ProcessPoolExecutor(max_workers=len(commands)) as executor:
        try:
            # 各サーバーを別々のプロセスで実行
            futures = [executor.submit(run_server, cmd) for cmd in commands]
            
            # すべてのプロセスが完了するまで待機
            for future in futures:
                future.result()
        except KeyboardInterrupt:
            print("\nStopping all servers...")
            sys.exit(0)

if __name__ == "__main__":
    main()