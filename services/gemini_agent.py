"""Google Gemini 1.5 Flash エージェント (v1.5) - 比較分析・リスク検知専用"""
import os
from dotenv import load_dotenv

load_dotenv()


class GeminiAgent:
    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY", "")
        self._mock = not api_key or api_key.startswith("your_") or not api_key.strip()
        if not self._mock:
            try:
                from google import genai
                self._client = genai.Client(api_key=api_key)
            except Exception:
                self._mock = True

    def analyze_comparison(self, request_data: dict, kintone_data: dict | None) -> str:
        """営業の依頼データ（新規）vs kintone の過去データを比較・リスク分析する"""
        if self._mock:
            return self._mock_analysis(request_data, kintone_data)
        prompt = self._build_prompt(request_data, kintone_data)
        try:
            response = self._client.models.generate_content(
                model="gemini-2.0-flash", contents=prompt
            )
            return response.text
        except Exception as e:
            return f"Gemini API エラー: {e}\n\n---\n{self._mock_analysis(request_data, kintone_data)}"

    def _build_prompt(self, request_data: dict, kintone_data: dict | None) -> str:
        req_str = "\n".join(f"- {k}: {v}" for k, v in request_data.items() if v)

        if kintone_data:
            kt_str  = "\n".join(f"- {k}: {v}" for k, v in kintone_data.items() if v)
            compare = f"【kintone 過去契約データ】\n{kt_str}"
        else:
            compare = "【kintone 過去契約データ】\nデータなし（新規顧客）"

        return f"""あなたは日本企業の契約書レビュー担当者です。
営業からの「新規依頼内容」と「過去契約データ」を照合し、変更点・リスクを日本語で分析してください。

【新規依頼内容（営業入力）】
{req_str}

{compare}

以下の観点で300字以内の箇条書きで出力してください（前置き不要）：
1. 前回との主な変更点（金額・期間・条件の数値変化）
2. 法務リスクや要確認事項（曖昧表現・不利な条件等）
3. 法務担当者へのアクション推奨（優先度: 高/中/低）"""

    def _mock_analysis(self, request_data: dict, kintone_data: dict | None) -> str:
        company  = request_data.get("customer_name", "（顧客名未設定）")
        ctype    = request_data.get("contract_type", "")
        amount   = request_data.get("amount", "未記載")
        p_start  = request_data.get("period_start", "未記載")
        p_end    = request_data.get("period_end", "未記載")
        terms    = request_data.get("special_terms", "") or "なし"
        comment  = request_data.get("sales_comment", "")

        if kintone_data:
            prev_amount = kintone_data.get("contract_amount", "不明")
            prev_end    = kintone_data.get("end_date", "不明")
            return f"""【Gemini 比較分析 (Mock)】

**変更点の概要**
- 顧客: {company}（既存顧客）
- 契約種別: {ctype}
- 金額: 今回 {amount} ／ 前回 {prev_amount}
- 有効期間: {p_start}〜{p_end}（前回終了: {prev_end}）

**リスク検知** [優先度: 中]
- ⚠️ 金額が前回から変更されています。増減の根拠を営業に確認してください
- ⚠️ 特約事項「{terms[:40]}」に法務確認が必要な可能性があります

**推奨アクション**
- 金額変更の根拠確認（優先度: 高）
- 特約事項のリーガルチェック（優先度: 中）
- Word生成後、送付前に最終確認（優先度: 低）"""
        else:
            return f"""【Gemini 比較分析 (Mock)】

**変更点の概要**
- 顧客: {company}（新規顧客 — kintoneデータなし）
- 契約種別: {ctype}
- 金額: {amount}
- 有効期間: {p_start}〜{p_end}

**リスク検知** [優先度: 低〜中]
- ℹ️ 新規顧客のため過去契約との比較はできません
- 特約事項: {terms[:40]}
{"- 補足コメント: " + comment[:40] if comment else ""}

**推奨アクション**
- 標準テンプレートを使用（優先度: 低）
- 新規顧客につきリーガルチェック推奨（優先度: 中）
- 締結希望日まで余裕があるか確認（優先度: 高）"""
