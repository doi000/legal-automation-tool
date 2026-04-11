"""Claude AI連携モジュール (v1.4) - expected_conclusion_date 追加"""
import json
import os
from typing import Optional

import anthropic
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-4-20250514"


class ContractParams(BaseModel):
    company_name: str
    contract_type: str
    contract_amount: str
    start_date: str                     # YYYY-MM-DD
    end_date: str                       # YYYY-MM-DD
    payment_terms: str
    special_notes: str = ""
    expected_conclusion_date: str = ""  # 締結希望日 YYYY-MM-DD (v1.4)


class AIAgent:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY が設定されていません")
        self.client = anthropic.Anthropic(api_key=api_key)

    # ------------------------------------------------------------------
    # 機能1: 依頼文解析エージェント
    # ------------------------------------------------------------------
    def analyze_request(self, request_text: str) -> ContractParams:
        """
        依頼文から契約項目を抽出しPydanticモデルで返す。
        バリデーション失敗時は最大3回リトライする。
        """
        system_prompt = """あなたは契約書作成の専門アシスタントです。
営業担当者から送られた依頼文を分析し、以下のJSON形式で契約情報を抽出してください。
必ずJSONのみを返し、余計な説明は一切不要です。

出力スキーマ:
{
  "company_name": "顧客企業名（文字列）",
  "contract_type": "契約種別（例：業務委託契約、売買契約、NDA等）",
  "contract_amount": "契約金額（例：1,000,000）数字とカンマのみ",
  "start_date": "契約開始日 YYYY-MM-DD形式",
  "end_date": "契約終了日 YYYY-MM-DD形式",
  "payment_terms": "支払条件（例：月末締め翌月末払い）",
  "special_notes": "その他特記事項（なければ空文字）",
  "expected_conclusion_date": "締結希望日・いつまでに締結したいか YYYY-MM-DD形式（明示されていれば抽出、なければ空文字）"
}

【expected_conclusion_dateの抽出ルール】
- 「〇〇までに締結」「〇月〇日に署名」「来週中に」「月末までに」「〇〇日に契約したい」などの表現を探す
- 相対表現（「来月末」「今月中」等）は今日の日付を基準に絶対日付に変換する
- 見当たらない場合は空文字 "" を返す

日付が明示されていない場合は依頼文から推測してください。金額が不明な場合は空文字にしてください。"""

        last_error = None
        for attempt in range(3):
            try:
                message = self.client.messages.create(
                    model=MODEL,
                    max_tokens=1024,
                    messages=[{
                        "role": "user",
                        "content": f"以下の依頼文から契約情報を抽出してください:\n\n{request_text}",
                    }],
                    system=system_prompt,
                )
                raw = message.content[0].text.strip()
                if "```" in raw:
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                data = json.loads(raw)
                return ContractParams(**data)
            except (json.JSONDecodeError, ValidationError, KeyError) as e:
                last_error = e
                continue

        raise ValueError(f"AI解析に3回失敗しました: {last_error}")

    # ------------------------------------------------------------------
    # 機能2: 差異サマリー生成
    # ------------------------------------------------------------------
    def generate_diff_summary(self, old_data: dict, new_data: dict) -> str:
        old_str = json.dumps(old_data, ensure_ascii=False, indent=2)
        new_str = json.dumps(new_data, ensure_ascii=False, indent=2)

        prompt = f"""以下の2つの契約データを比較し、変更点のみを日本語の箇条書きで要約してください。
変更がない項目は省略してください。
変更点がない場合は「変更点なし」と返してください。

【既存契約データ（kintone）】
{old_str}

【新しい変更案】
{new_str}

出力形式（変更点のみ箇条書き）:
- 項目名: 旧値 → 新値（変更理由があれば補足）"""

        message = self.client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
