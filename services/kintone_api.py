"""kintone API連携モジュール"""
import os
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

MOCK_DATA = {
    "company_name": "株式会社サンプル",
    "contract_type": "業務委託契約",
    "contract_amount": "1,000,000",
    "start_date": "2025-01-01",
    "end_date": "2025-12-31",
    "payment_terms": "月末締め翌月末払い",
}


class KintoneClient:
    def __init__(self):
        self.use_mock = os.getenv("USE_MOCK_KINTONE", "false").lower() == "true"
        self.subdomain = os.getenv("KINTONE_SUBDOMAIN", "")
        self.app_id = os.getenv("KINTONE_APP_ID", "")
        self.api_token = os.getenv("KINTONE_API_TOKEN", "")

    def get_latest_contract(self, company_name: str) -> Optional[dict]:
        """顧客名で最新の契約レコードを1件取得する"""
        if self.use_mock:
            return dict(MOCK_DATA, company_name=company_name)

        url = f"https://{self.subdomain}.cybozu.com/k/v1/records.json"
        headers = {"X-Cybozu-API-Token": self.api_token}
        params = {
            "app": self.app_id,
            "query": f'company_name = "{company_name}" order by 更新日時 desc limit 1',
        }

        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()

        records = resp.json().get("records", [])
        if not records:
            return None

        raw = records[0]
        return {
            "company_name": raw.get("company_name", {}).get("value", ""),
            "contract_type": raw.get("contract_type", {}).get("value", ""),
            "contract_amount": raw.get("contract_amount", {}).get("value", ""),
            "start_date": raw.get("start_date", {}).get("value", ""),
            "end_date": raw.get("end_date", {}).get("value", ""),
            "payment_terms": raw.get("payment_terms", {}).get("value", ""),
        }
