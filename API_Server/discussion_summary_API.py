from openai import OpenAI
from flask import Flask, request, render_template
from flask.views import MethodView

CONFIGS = {}

# ツールの定義を修正
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

class IndexView(MethodView):
    def get(self):
        return render_template("index.html")

    def post(self):
        text = request.form['text']

        try:
            # モデル呼び出し
            response = client.chat.completions.create(
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
                        )
                    },
                    {
                        "role": "user",
                        "content": f"次の文章を要約してください：「{text}」"
                    }
                ],
                tools=TOOLS,
                temperature=0.7,
            )
            
            # ツールの呼び出し結果を取得
            if response.choices[0].message.tool_calls:
                summary_text = response.choices[0].message.tool_calls[0].function.arguments
            else:
                summary_text = response.choices[0].message.content

            return render_template("index.html", summary_text=summary_text, text=text)
            
        except Exception as e:
            error_message = f"エラーが発生しました: {str(e)}"
            return render_template("index.html", summary_text=error_message, text=text)

if __name__ == "__main__":
    import json

    # 設定ファイルの読み込み
    with open("app-configs.json", "r") as f:
        CONFIGS.update(json.load(f))

    # OpenAIクライアントの初期化
    client = OpenAI(api_key=CONFIGS['OPENAI.API_KEY'], timeout=30)
    
    # Flaskアプリケーションの設定
    app = Flask(__name__)
    app.add_url_rule("/", view_func=IndexView.as_view("index"))
    app.run(debug=True, load_dotenv=True)