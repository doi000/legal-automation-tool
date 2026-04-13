"""Google Sheets をDBとして使用するモジュール"""
import os
import uuid
from datetime import datetime
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_HEADERS = {
    "user_master": ["email", "name", "role"],
    "transaction_log": [
        "request_id", "title", "requester_email", "status",
        "current_version", "created_at", "last_updated_at",
        "scheduled_date", "sales_person", "editor_person",
        # v1.5: Sales フォーム入力フィールド
        "customer_name", "contract_type", "amount",
        "period_start", "period_end", "special_terms", "sales_comment",
    ],
    "status_history": [
        "history_id", "request_id", "version", "status",
        "changed_at", "changed_by", "comment",
    ],
    "workflow_definition": [
        "step_order", "step_name", "approver_email", "action_type",
    ],
    "review_rules": [
        "rule_id", "rule_name", "condition_field", "condition_operator",
        "condition_value", "action", "action_target", "description",
        "is_active", "created_at", "created_by",
    ],
    "workflow_rules": [
        "rule_id", "rule_name", "trigger_status", "condition",
        "next_step_override", "notification_emails", "description",
        "is_active", "created_at", "created_by",
    ],
    "template_registry": [
        "template_id", "template_name", "contract_type", "drive_url",
        "version", "is_active", "uploaded_at", "uploaded_by", "description",
    ],
    "validation_rules": [
        "rule_id", "target_template", "condition_field", "operator", "threshold",
        "action_type", "action_value", "message", "is_active", "created_at", "created_by",
    ],
}


class SheetsDB:
    def __init__(self):
        self._client: Optional[gspread.Client] = None
        self._spreadsheet: Optional[gspread.Spreadsheet] = None
        self._dev_mode = os.getenv("DEV_MODE", "false").lower() == "true"
        self._mock_store: dict = {name: [] for name in SHEET_HEADERS}

        if not self._dev_mode:
            self._connect()
            self.initialize_sheets()

    # ------------------------------------------------------------------
    # 接続・初期化
    # ------------------------------------------------------------------
    def _connect(self):
        creds_path = os.path.join(os.path.dirname(__file__), "..", "google_credentials.json")
        creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
        self._client = gspread.authorize(creds)
        sheet_id = os.getenv("GOOGLE_SHEET_ID")
        self._spreadsheet = self._client.open_by_key(sheet_id)

    def initialize_sheets(self):
        """未作成のシートを作成しヘッダーを設定（冪等）"""
        existing = {ws.title for ws in self._spreadsheet.worksheets()}
        for name, headers in SHEET_HEADERS.items():
            if name not in existing:
                ws = self._spreadsheet.add_worksheet(title=name, rows=1000, cols=len(headers))
                ws.append_row(headers)

    # ------------------------------------------------------------------
    # 汎用 CRUD ヘルパー
    # ------------------------------------------------------------------
    def _get_ws(self, sheet_name: str) -> gspread.Worksheet:
        return self._spreadsheet.worksheet(sheet_name)

    def _all_records(self, sheet_name: str) -> list[dict]:
        if self._dev_mode:
            return list(self._mock_store[sheet_name])
        return self._get_ws(sheet_name).get_all_records()

    def _append_row(self, sheet_name: str, row: dict):
        headers = SHEET_HEADERS[sheet_name]
        values = [str(row.get(h, "")) for h in headers]
        if self._dev_mode:
            self._mock_store[sheet_name].append(row)
        else:
            self._get_ws(sheet_name).append_row(values)

    def _update_row(self, sheet_name: str, key_col: str, key_val: str, updates: dict):
        if self._dev_mode:
            for record in self._mock_store[sheet_name]:
                if str(record.get(key_col)) == str(key_val):
                    record.update(updates)
            return
        ws = self._get_ws(sheet_name)
        records = ws.get_all_records()
        headers = SHEET_HEADERS[sheet_name]
        for i, record in enumerate(records, start=2):
            if str(record.get(key_col)) == str(key_val):
                for col_name, new_val in updates.items():
                    if col_name in headers:
                        col_idx = headers.index(col_name) + 1
                        ws.update_cell(i, col_idx, str(new_val))
                break

    def _delete_row(self, sheet_name: str, key_col: str, key_val: str):
        if self._dev_mode:
            self._mock_store[sheet_name] = [
                r for r in self._mock_store[sheet_name]
                if str(r.get(key_col)) != str(key_val)
            ]
            return
        ws = self._get_ws(sheet_name)
        records = ws.get_all_records()
        for i, record in enumerate(records, start=2):
            if str(record.get(key_col)) == str(key_val):
                ws.delete_rows(i)
                break

    # ------------------------------------------------------------------
    # user_master
    # ------------------------------------------------------------------
    def get_user(self, email: str) -> Optional[dict]:
        for r in self._all_records("user_master"):
            if r.get("email") == email:
                return r
        return None

    def get_all_users(self) -> list[dict]:
        return self._all_records("user_master")

    def add_user(self, email: str, name: str, role: str):
        self._append_row("user_master", {"email": email, "name": name, "role": role})

    def update_user(self, email: str, updates: dict):
        self._update_row("user_master", "email", email, updates)

    def delete_user(self, email: str):
        self._delete_row("user_master", "email", email)

    # ------------------------------------------------------------------
    # transaction_log
    # ------------------------------------------------------------------
    def get_all_transactions(self) -> list[dict]:
        return self._all_records("transaction_log")

    def get_transaction(self, request_id: str) -> Optional[dict]:
        for r in self._all_records("transaction_log"):
            if r.get("request_id") == request_id:
                return r
        return None

    def create_transaction(
        self,
        title: str,
        requester_email: str,
        scheduled_date: str = "",
        sales_person: str = "",
        editor_person: str = "",
        customer_name: str = "",
        contract_type: str = "",
        amount: str = "",
        period_start: str = "",
        period_end: str = "",
        special_terms: str = "",
        sales_comment: str = "",
    ) -> str:
        request_id = str(uuid.uuid4())[:8].upper()
        now = datetime.now().isoformat()
        self._append_row("transaction_log", {
            "request_id": request_id,
            "title": title,
            "requester_email": requester_email,
            "status": "未着手",
            "current_version": "1",
            "created_at": now,
            "last_updated_at": now,
            "scheduled_date": scheduled_date,
            "sales_person": sales_person,
            "editor_person": editor_person,
            "customer_name": customer_name,
            "contract_type": contract_type,
            "amount": amount,
            "period_start": period_start,
            "period_end": period_end,
            "special_terms": special_terms,
            "sales_comment": sales_comment,
        })
        return request_id

    def update_transaction_status(
        self, request_id: str, new_status: str, changed_by: str, comment: str = ""
    ):
        tx = self.get_transaction(request_id)
        if not tx:
            return
        version = int(tx.get("current_version", 1)) + 1
        now = datetime.now().isoformat()
        self._update_row("transaction_log", "request_id", request_id, {
            "status": new_status,
            "current_version": str(version),
            "last_updated_at": now,
        })
        self._append_row("status_history", {
            "history_id": str(uuid.uuid4())[:8].upper(),
            "request_id": request_id,
            "version": str(version),
            "status": new_status,
            "changed_at": now,
            "changed_by": changed_by,
            "comment": comment,
        })

    def update_transaction(self, request_id: str, updates: dict):
        updates["last_updated_at"] = datetime.now().isoformat()
        self._update_row("transaction_log", "request_id", request_id, updates)

    # ------------------------------------------------------------------
    # status_history
    # ------------------------------------------------------------------
    def get_status_history(self, request_id: str) -> list[dict]:
        return [r for r in self._all_records("status_history") if r.get("request_id") == request_id]

    # ------------------------------------------------------------------
    # workflow_definition
    # ------------------------------------------------------------------
    def get_workflow(self) -> list[dict]:
        steps = self._all_records("workflow_definition")
        return sorted(steps, key=lambda x: int(x.get("step_order", 0)))

    def save_workflow(self, steps: list[dict]):
        if self._dev_mode:
            self._mock_store["workflow_definition"] = steps
            return
        ws = self._get_ws("workflow_definition")
        headers = SHEET_HEADERS["workflow_definition"]
        ws.clear()
        ws.append_row(headers)
        for step in steps:
            ws.append_row([str(step.get(h, "")) for h in headers])

    # ------------------------------------------------------------------
    # review_rules
    # ------------------------------------------------------------------
    def get_active_review_rules(self) -> list[dict]:
        return [r for r in self._all_records("review_rules") if str(r.get("is_active", "true")).lower() == "true"]

    def get_all_review_rules(self) -> list[dict]:
        return self._all_records("review_rules")

    def add_review_rule(self, rule: dict):
        rule["rule_id"] = str(uuid.uuid4())[:8].upper()
        rule["is_active"] = "true"
        rule["created_at"] = datetime.now().isoformat()
        self._append_row("review_rules", rule)

    def update_review_rule(self, rule_id: str, updates: dict):
        self._update_row("review_rules", "rule_id", rule_id, updates)

    def deactivate_review_rule(self, rule_id: str):
        self._update_row("review_rules", "rule_id", rule_id, {"is_active": "false"})

    # ------------------------------------------------------------------
    # workflow_rules
    # ------------------------------------------------------------------
    def get_active_workflow_rules(self) -> list[dict]:
        return [r for r in self._all_records("workflow_rules") if str(r.get("is_active", "true")).lower() == "true"]

    def get_all_workflow_rules(self) -> list[dict]:
        return self._all_records("workflow_rules")

    def add_workflow_rule(self, rule: dict):
        rule["rule_id"] = str(uuid.uuid4())[:8].upper()
        rule["is_active"] = "true"
        rule["created_at"] = datetime.now().isoformat()
        self._append_row("workflow_rules", rule)

    def update_workflow_rule(self, rule_id: str, updates: dict):
        self._update_row("workflow_rules", "rule_id", rule_id, updates)

    def deactivate_workflow_rule(self, rule_id: str):
        self._update_row("workflow_rules", "rule_id", rule_id, {"is_active": "false"})

    # ------------------------------------------------------------------
    # template_registry
    # ------------------------------------------------------------------
    def get_active_templates(self) -> list[dict]:
        return [r for r in self._all_records("template_registry") if str(r.get("is_active", "true")).lower() == "true"]

    def get_all_templates(self) -> list[dict]:
        return self._all_records("template_registry")

    def add_template(self, template: dict):
        template["template_id"] = str(uuid.uuid4())[:8].upper()
        template["is_active"] = "true"
        template["uploaded_at"] = datetime.now().isoformat()
        self._append_row("template_registry", template)

    def update_template(self, template_id: str, updates: dict):
        self._update_row("template_registry", "template_id", template_id, updates)

    def deactivate_template(self, template_id: str):
        self._update_row("template_registry", "template_id", template_id, {"is_active": "false"})

    # ------------------------------------------------------------------
    # validation_rules
    # ------------------------------------------------------------------
    def get_active_validation_rules(self) -> list[dict]:
        return [r for r in self._all_records("validation_rules") if str(r.get("is_active", "true")).lower() == "true"]

    def get_all_validation_rules(self) -> list[dict]:
        return self._all_records("validation_rules")

    def add_validation_rule(self, rule: dict):
        rule["rule_id"] = str(uuid.uuid4())[:8].upper()
        rule["is_active"] = "true"
        rule["created_at"] = datetime.now().isoformat()
        self._append_row("validation_rules", rule)

    def update_validation_rule(self, rule_id: str, updates: dict):
        self._update_row("validation_rules", "rule_id", rule_id, updates)

    def delete_validation_rule(self, rule_id: str):
        self._delete_row("validation_rules", "rule_id", rule_id)
