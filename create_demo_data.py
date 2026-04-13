"""
デモデータ投入スクリプト (v1.4)
- 6名ユーザー (Sales x2, Editor x2, Admin x2)
- 各ステータス2件ずつ計8件（うち3件に期限超過日付を設定）
- 期限超過アラートの動作確認が可能

使い方: python create_demo_data.py
"""
import os, sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DEV_MODE", "true")
os.environ.setdefault("USE_MOCK_KINTONE", "true")

from dotenv import load_dotenv
load_dotenv()

from services.sheets_db import SheetsDB


def inject_demo_data(db: SheetsDB):
    today = datetime.today()

    # ──────────────────────────────────────────
    # 1. ユーザー（6名）
    # ──────────────────────────────────────────
    demo_users = [
        {"email": "sales_user1@example.com",  "name": "営業 一郎",   "role": "Sales"},
        {"email": "sales_user2@example.com",  "name": "営業 二子",   "role": "Sales"},
        {"email": "editor_user1@example.com", "name": "法務 三郎",   "role": "Editor"},
        {"email": "editor_user2@example.com", "name": "法務 四子",   "role": "Editor"},
        {"email": "admin_user1@example.com",  "name": "管理者 五郎", "role": "Admin"},
        {"email": "admin_user2@example.com",  "name": "管理者 六子", "role": "Admin"},
    ]
    existing = {u["email"] for u in db.get_all_users()}
    added = sum(1 for u in demo_users if u["email"] not in existing and db.add_user(u["email"], u["name"], u["role"]) is None)
    print(f"[OK] Users: {len(demo_users)} (added: {len(demo_users) - len(existing & {u['email'] for u in demo_users})})")

    # ──────────────────────────────────────────
    # 2. ワークフロー（3ステップ）
    # ──────────────────────────────────────────
    db.save_workflow([
        {"step_order": "1", "step_name": "確認",            "approver_email": "editor_user1@example.com", "action_type": "確認"},
        {"step_order": "2", "step_name": "リーガルチェック", "approver_email": "editor_user2@example.com", "action_type": "リーガルチェック"},
        {"step_order": "3", "step_name": "承認",            "approver_email": "admin_user1@example.com",  "action_type": "承認"},
    ])
    print("[OK] Workflow: 3 steps")

    # ──────────────────────────────────────────
    # 3. 審査ルール
    # ──────────────────────────────────────────
    demo_rules = [
        {"rule_name": "高額案件：法務確認必須",
         "condition_field": "contract_amount", "condition_operator": "以上", "condition_value": "5000000",
         "action": "法務確認必須", "action_target": "editor_user1@example.com",
         "description": "500万円以上は法務確認必須", "created_by": "admin_user1@example.com"},
        {"rule_name": "NDA：管理者承認追加",
         "condition_field": "contract_type", "condition_operator": "等しい", "condition_value": "NDA",
         "action": "上長承認追加", "action_target": "admin_user1@example.com",
         "description": "NDA契約は管理者の追加承認", "created_by": "admin_user1@example.com"},
        {"rule_name": "新規顧客：リーガルチェック",
         "condition_field": "company_name", "condition_operator": "含む", "condition_value": "新規",
         "action": "法務確認必須", "action_target": "editor_user2@example.com",
         "description": "新規顧客はリーガルチェック必須", "created_by": "admin_user1@example.com"},
    ]
    existing_rules = {r["rule_name"] for r in db.get_all_review_rules()}
    for rule in demo_rules:
        if rule["rule_name"] not in existing_rules:
            db.add_review_rule(rule)
    print(f"[OK] Rules: {len(demo_rules)}")

    # ──────────────────────────────────────────
    # 4. 案件（各ステータス2件 = 計8件）
    #    ★ 期限超過案件を3件含める（アラート動作確認用）
    # ──────────────────────────────────────────
    D = lambda days: (today + timedelta(days=days)).strftime("%Y-%m-%d")

    demo_transactions = [
        # ── 未着手 ──
        {"title": "株式会社フューチャーテック - 利用申込書",
         "requester_email": "sales_user1@example.com", "status": "未着手",
         "scheduled_date": D(30), "sales_person": "営業 一郎", "editor_person": "",
         "customer_name": "株式会社フューチャーテック", "contract_type": "利用申込書",
         "amount": "500,000円/月", "period_start": D(35), "period_end": D(365),
         "special_terms": "自動更新条項を追加したい", "sales_comment": "先方の要望でサービス開始を来月に前倒し",
         "history": [("未着手", "sales_user1@example.com", "新規依頼")]},

        {"title": "合同会社スマートワーク - NDA",
         "requester_email": "sales_user2@example.com", "status": "未着手",
         "scheduled_date": D(-5),   # ★ 期限超過
         "sales_person": "営業 二子", "editor_person": "",
         "customer_name": "合同会社スマートワーク", "contract_type": "NDA",
         "amount": "", "period_start": D(1), "period_end": D(365),
         "special_terms": "", "sales_comment": "急ぎ対応お願いします（締結日過ぎています）",
         "history": [("未着手", "sales_user2@example.com", "新規依頼")]},

        # ── 作業中 ──
        {"title": "株式会社グローバルソリューション - 業務委託契約",
         "requester_email": "sales_user1@example.com", "status": "作業中",
         "scheduled_date": D(14), "sales_person": "営業 一郎", "editor_person": "法務 三郎",
         "customer_name": "株式会社グローバルソリューション", "contract_type": "業務委託契約",
         "amount": "1,200,000円/月", "period_start": D(20), "period_end": D(385),
         "special_terms": "支払いサイトを60日に変更希望", "sales_comment": "前回から金額アップ・期間延長",
         "history": [("未着手", "sales_user1@example.com", "新規依頼"),
                     ("作業中",  "editor_user1@example.com", "Gemini分析・Word生成完了")]},

        {"title": "有限会社テックイノベーション - 覚書",
         "requester_email": "sales_user2@example.com", "status": "作業中",
         "scheduled_date": D(-3),   # ★ 期限超過
         "sales_person": "営業 二子", "editor_person": "法務 四子",
         "customer_name": "有限会社テックイノベーション", "contract_type": "覚書",
         "amount": "300,000円", "period_start": D(1), "period_end": D(180),
         "special_terms": "免責事項の範囲を縮小", "sales_comment": "",
         "history": [("未着手", "sales_user2@example.com", "新規依頼"),
                     ("作業中",  "editor_user2@example.com", "kintone確認・Word生成")]},

        # ── 承認待ち ──
        {"title": "株式会社デジタルパートナーズ - 業務委託契約",
         "requester_email": "sales_user1@example.com", "status": "承認待ち",
         "scheduled_date": D(5), "sales_person": "営業 一郎", "editor_person": "法務 三郎",
         "customer_name": "株式会社デジタルパートナーズ", "contract_type": "業務委託契約",
         "amount": "2,500,000円/月", "period_start": D(10), "period_end": D(375),
         "special_terms": "競業避止義務の追加", "sales_comment": "高額案件につき優先対応",
         "history": [("未着手",   "sales_user1@example.com",  "新規依頼"),
                     ("作業中",   "editor_user1@example.com", "Word生成完了"),
                     ("承認待ち", "editor_user1@example.com", "承認申請")]},

        {"title": "株式会社クリエイティブラボ - NDA",
         "requester_email": "sales_user2@example.com", "status": "承認待ち",
         "scheduled_date": D(-2),   # ★ 期限超過
         "sales_person": "営業 二子", "editor_person": "法務 四子",
         "customer_name": "株式会社クリエイティブラボ", "contract_type": "NDA",
         "amount": "", "period_start": D(1), "period_end": D(730),
         "special_terms": "第三者への開示禁止期間を10年に延長", "sales_comment": "締結日超過のため急ぎ",
         "history": [("未着手",   "sales_user2@example.com",  "新規依頼"),
                     ("作業中",   "editor_user2@example.com", "ドキュメント準備"),
                     ("承認待ち", "editor_user2@example.com", "最終確認依頼")]},

        # ── 完了 ──
        {"title": "株式会社サンプルコーポレーション - 業務委託契約",
         "requester_email": "sales_user1@example.com", "status": "完了",
         "scheduled_date": D(-10), "sales_person": "営業 一郎", "editor_person": "法務 三郎",
         "customer_name": "株式会社サンプルコーポレーション", "contract_type": "業務委託契約",
         "amount": "800,000円/月", "period_start": D(-5), "period_end": D(360),
         "special_terms": "", "sales_comment": "",
         "history": [("未着手",   "sales_user1@example.com",  "新規依頼"),
                     ("作業中",   "editor_user1@example.com", "Word生成完了"),
                     ("承認待ち", "editor_user1@example.com", "承認申請"),
                     ("完了",     "admin_user1@example.com",  "承認完了")]},

        {"title": "有限会社リアルエステート - 利用申込書",
         "requester_email": "sales_user2@example.com", "status": "完了",
         "scheduled_date": D(-5), "sales_person": "営業 二子", "editor_person": "法務 四子",
         "customer_name": "有限会社リアルエステート", "contract_type": "利用申込書",
         "amount": "150,000円/月", "period_start": D(-3), "period_end": D(362),
         "special_terms": "", "sales_comment": "",
         "history": [("未着手",   "sales_user2@example.com",  "新規依頼"),
                     ("作業中",   "editor_user2@example.com", "書類作成"),
                     ("承認待ち", "editor_user2@example.com", "承認申請"),
                     ("完了",     "admin_user2@example.com",  "問題なし。承認。")]},
    ]

    existing_titles = {t["title"] for t in db.get_all_transactions()}
    new_count = 0
    for demo_tx in demo_transactions:
        if demo_tx["title"] in existing_titles:
            continue
        rid = db.create_transaction(
            demo_tx["title"], demo_tx["requester_email"],
            scheduled_date=demo_tx["scheduled_date"],
            sales_person=demo_tx["sales_person"],
            editor_person=demo_tx["editor_person"],
            customer_name=demo_tx.get("customer_name", ""),
            contract_type=demo_tx.get("contract_type", ""),
            amount=demo_tx.get("amount", ""),
            period_start=demo_tx.get("period_start", ""),
            period_end=demo_tx.get("period_end", ""),
            special_terms=demo_tx.get("special_terms", ""),
            sales_comment=demo_tx.get("sales_comment", ""),
        )
        for i, (status, changed_by, comment) in enumerate(demo_tx["history"]):
            if i == 0:
                continue
            db.update_transaction_status(rid, status, changed_by, comment)
        new_count += 1

    print(f"[OK] Transactions: {len(demo_transactions)} total, {new_count} newly added")

    # ──────────────────────────────────────────
    # 5. バリデーションルール（決定論的エンジン用）
    # ──────────────────────────────────────────
    demo_vr = [
        {
            "target_template": "共通",
            "condition_field": "scheduled_date",
            "operator":        "is_empty",
            "threshold":       "",
            "action_type":     "ERROR",
            "action_value":    "",
            "message":         "締結予定日を入力してください",
            "created_by":      "admin_user1@example.com",
        },
        {
            "target_template": "共通",
            "condition_field": "company_name",
            "operator":        "is_empty",
            "threshold":       "",
            "action_type":     "ERROR",
            "action_value":    "",
            "message":         "顧客名を入力してください",
            "created_by":      "admin_user1@example.com",
        },
        {
            "target_template": "共通",
            "condition_field": "contract_amount",
            "operator":        "greater_than",
            "threshold":       "1000000",
            "action_type":     "FORCE_APPROVER",
            "action_value":    "admin_user1@example.com",
            "message":         "100万円超の契約は管理者承認が必要です",
            "created_by":      "admin_user1@example.com",
        },
        {
            "target_template": "共通",
            "condition_field": "contract_amount",
            "operator":        "greater_than",
            "threshold":       "5000000",
            "action_type":     "WARNING",
            "action_value":    "",
            "message":         "500万円超の高額契約です。内容を再確認してください",
            "created_by":      "admin_user1@example.com",
        },
    ]
    existing_vr_keys = {
        f"{r.get('condition_field')}|{r.get('operator')}|{r.get('threshold')}|{r.get('action_type')}"
        for r in db.get_all_validation_rules()
    }
    added_vr = 0
    for rule in demo_vr:
        key = f"{rule['condition_field']}|{rule['operator']}|{rule['threshold']}|{rule['action_type']}"
        if key not in existing_vr_keys:
            db.add_validation_rule(rule)
            added_vr += 1
    print(f"[OK] ValidationRules: {len(demo_vr)} (added: {added_vr})")

    # ──────────────────────────────────────────
    # 6. サマリー
    # ──────────────────────────────────────────
    from datetime import date
    today_date = date.today()
    all_tx = db.get_all_transactions()
    status_dist = {}
    overdue_list = []
    for t in all_tx:
        s = t.get("status", "?")
        status_dist[s] = status_dist.get(s, 0) + 1
        sd = t.get("scheduled_date", "")
        if sd:
            try:
                if datetime.strptime(sd, "%Y-%m-%d").date() < today_date:
                    overdue_list.append(t["title"][:30])
            except ValueError:
                pass

    print("\n=== Demo Data Summary ===")
    print(f"  Users:       {len(db.get_all_users())}")
    print(f"  Transactions:{len(all_tx)}  {status_dist}")
    print(f"  Overdue({len(overdue_list)}): {overdue_list}")
    print(f"  Workflow:    {len(db.get_workflow())} steps")
    print(f"  Rules:       {len(db.get_all_review_rules())}")
    print(f"  ValRules:    {len(db.get_all_validation_rules())}")
    print("\nRun: python -m streamlit run app.py")


if __name__ == "__main__":
    print("=== Injecting v1.7 demo data ===")
    db = SheetsDB()
    inject_demo_data(db)
