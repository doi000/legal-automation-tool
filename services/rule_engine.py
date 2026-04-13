"""決定論的バリデーションエンジン (v1.7) - AIを使わず純粋なPythonロジックで動作"""
from dataclasses import dataclass, field
from typing import Literal

OPERATORS = ["greater_than", "less_than", "equals", "contains", "is_empty", "is_not_empty"]
ACTION_TYPES = ["ERROR", "WARNING", "FORCE_APPROVER"]

OPERATOR_LABELS = {
    "greater_than":  "より大きい (>)",
    "less_than":     "より小さい (<)",
    "equals":        "等しい (=)",
    "contains":      "含む",
    "is_empty":      "が空",
    "is_not_empty":  "が空でない",
}

ACTION_LABELS = {
    "ERROR":           "エラー（生成ブロック）",
    "WARNING":         "警告（続行可）",
    "FORCE_APPROVER":  "承認者強制追加",
}

CONDITION_FIELDS = [
    "company_name", "contract_type", "contract_amount",
    "start_date", "end_date", "payment_terms", "special_notes", "scheduled_date",
]

FIELD_LABELS = {
    "company_name":    "顧客名",
    "contract_type":   "契約種別",
    "contract_amount": "契約金額",
    "start_date":      "開始日",
    "end_date":        "終了日",
    "payment_terms":   "支払条件",
    "special_notes":   "特記事項",
    "scheduled_date":  "締結予定日",
}


@dataclass
class ValidationResult:
    rule_id: str
    rule_message: str
    action_type: Literal["ERROR", "WARNING", "FORCE_APPROVER"]
    action_value: str = ""  # FORCE_APPROVER の場合は承認者メール


class RuleEngine:
    def __init__(self, rules: list[dict]):
        self._rules = [r for r in rules if str(r.get("is_active", "true")).lower() == "true"]

    def validate(self, data: dict, target_template: str = "") -> list[ValidationResult]:
        results = []
        for rule in self._rules:
            rule_target = rule.get("target_template", "")
            # 対象テンプレートが "共通" または空の場合は全テンプレートに適用
            if rule_target and rule_target != "共通":
                if target_template and rule_target != target_template:
                    continue

            cond_field  = rule.get("condition_field", "")
            operator    = rule.get("operator", "")
            threshold   = rule.get("threshold", "")
            action_type = rule.get("action_type", "WARNING")
            message     = rule.get("message", "")
            action_value = rule.get("action_value", "")

            value = data.get(cond_field, "")

            if self._matches(value, operator, threshold):
                results.append(ValidationResult(
                    rule_id=rule.get("rule_id", ""),
                    rule_message=message,
                    action_type=action_type,
                    action_value=action_value,
                ))

        return results

    @staticmethod
    def _matches(value: str, operator: str, threshold: str) -> bool:
        v = str(value).strip()
        t = str(threshold).strip()

        if operator == "is_empty":
            return v == ""
        elif operator == "is_not_empty":
            return v != ""
        elif operator == "equals":
            return v.lower() == t.lower()
        elif operator == "contains":
            return t.lower() in v.lower()
        elif operator == "greater_than":
            try:
                return float(v.replace(",", "").replace("円", "")) > float(t.replace(",", ""))
            except (ValueError, AttributeError):
                return False
        elif operator == "less_than":
            try:
                return float(v.replace(",", "").replace("円", "")) < float(t.replace(",", ""))
            except (ValueError, AttributeError):
                return False
        return False

    @staticmethod
    def has_errors(results: list[ValidationResult]) -> bool:
        return any(r.action_type == "ERROR" for r in results)

    @staticmethod
    def get_force_approvers(results: list[ValidationResult]) -> list[str]:
        return [r.action_value for r in results if r.action_type == "FORCE_APPROVER" and r.action_value]

    @staticmethod
    def natural_language(rule: dict) -> str:
        """ルールを自然言語で説明する（UI表示用）"""
        field      = rule.get("condition_field", "")
        field_lbl  = FIELD_LABELS.get(field, field)
        op         = rule.get("operator", "")
        op_lbl     = OPERATOR_LABELS.get(op, op)
        threshold  = rule.get("threshold", "")
        action     = rule.get("action_type", "")
        action_lbl = ACTION_LABELS.get(action, action)
        message    = rule.get("message", "")
        target     = rule.get("target_template", "共通") or "共通"
        av         = rule.get("action_value", "")

        threshold_part = f" {threshold}" if threshold and op not in ("is_empty", "is_not_empty") else ""
        av_part = f" ({av})" if av else ""
        return f"[{target}] {field_lbl} {op_lbl}{threshold_part} → {action_lbl}: {message}{av_part}"
