"""バリデーションモジュール（Pydantic）"""
import re
from typing import Optional

from pydantic import BaseModel, field_validator


class ContractParamsValidator(BaseModel):
    company_name: str
    contract_type: str
    contract_amount: str
    start_date: str
    end_date: str
    payment_terms: str
    special_notes: str = ""

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        if v and not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError(f"日付は YYYY-MM-DD 形式で入力してください: {v}")
        return v

    @field_validator("contract_amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        # カンマ・数字のみ許可（空文字も可）
        cleaned = v.replace(",", "")
        if cleaned and not cleaned.isdigit():
            raise ValueError(f"金額は数字とカンマのみ入力してください: {v}")
        return v


class UserValidator(BaseModel):
    email: str
    name: str
    role: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("有効なメールアドレスを入力してください")
        return v.lower().strip()

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("Sales", "Editor", "Admin"):
            raise ValueError("ロールは Sales / Editor / Admin のいずれかです")
        return v


class ReviewRuleValidator(BaseModel):
    rule_name: str
    condition_field: str
    condition_operator: str
    condition_value: str
    action: str
    action_target: str = ""
    description: str = ""
    created_by: str = ""


class WorkflowRuleValidator(BaseModel):
    rule_name: str
    trigger_status: str
    condition: str = ""
    next_step_override: str = ""
    notification_emails: str = ""
    description: str = ""
    created_by: str = ""
