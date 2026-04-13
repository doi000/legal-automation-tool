"""作業画面 - v1.5: Sales依頼フォーム + Gemini比較分析 + 決定論的バリデーション"""
import os
import tempfile
from datetime import date, datetime

import streamlit as st
from utils.auth import check_access, is_workflow_approver
from services.gemini_agent import GeminiAgent
from services.kintone_api import KintoneClient
from services.word_generator import WordGenerator
from services.drive_uploader import DriveUploader
from services.rule_engine import RuleEngine

_FALLBACK_TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "assets", "templates", "default.docx")
_DEFAULT_TEMPLATE  = os.path.join(os.path.dirname(__file__), "..", "templates", "contract_template.docx")

CONTRACT_TYPES = ["NDA", "利用申込書", "覚書", "業務委託契約", "売買契約", "その他"]


# ═══════════════════════════════════════════════════════════
# メインエントリ
# ═══════════════════════════════════════════════════════════
def show(db):
    user = check_access(roles=("Editor", "Admin", "Sales"))
    role  = user.get("role")
    email = user.get("email")

    request_id = st.session_state.get("current_request_id")
    tx = db.get_transaction(request_id) if request_id else None

    # 案件切り替え時に分析/フォームデータをリセット
    if st.session_state.get("_ws_request_id") != request_id:
        for k in ["kintone_data", "is_new_customer", "gemini_analysis"]:
            st.session_state.pop(k, None)
        for k in [k for k in st.session_state if k.startswith("f_")]:
            del st.session_state[k]
        st.session_state["_ws_request_id"] = request_id

    if role == "Sales":
        st.title("📋 契約依頼フォーム")
        if not tx:
            _render_sales_form(db, user)
        else:
            _render_status_banner(tx)
            _render_sales_view(tx)
    else:
        # Editor / Admin
        st.title("📝 契約作成・編集")
        _render_status_banner(tx)
        if not tx:
            st.info("ダッシュボードから案件を選択してください。")
            return
        # 上段: 依頼内容サマリー
        st.subheader("① 依頼内容（営業入力）")
        _render_request_summary(tx)
        st.divider()
        # 下段: kintone（左） & Gemini分析 + Word生成（右）
        st.subheader("② データ確認 & 比較分析・編集")
        col_left, col_right = st.columns(2)
        with col_left:
            _render_kintone_panel(tx)
        with col_right:
            _render_word_form(db, user, role, tx)
        # 承認操作
        if tx and tx.get("status") == "承認待ち":
            st.divider()
            _render_approval_panel(db, request_id, email)


# ═══════════════════════════════════════════════════════════
# Sales: 依頼フォーム（新規）
# ═══════════════════════════════════════════════════════════
def _render_sales_form(db, user):
    """Sales ロール専用: 構造化依頼フォーム（決定論的バリデーション付き）"""
    st.markdown(
        "<div style='color:#555;font-size:14px;margin-bottom:16px;'>"
        "必要事項を入力し「依頼を提出する」ボタンを押してください。"
        "<br>顧客名・契約種別・締結希望日は必須項目です。</div>",
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    customer_name = col1.text_input(
        "顧客名 *", key="sf_customer_name", placeholder="株式会社〇〇"
    )
    contract_type = col2.selectbox(
        "契約種別 *", CONTRACT_TYPES, key="sf_contract_type"
    )

    col3, col4 = st.columns(2)
    scheduled_date = col3.date_input(
        "締結希望日 *", value=None, min_value=date.today(), key="sf_scheduled_date"
    )
    amount = col4.text_input(
        "金額", key="sf_amount", placeholder="例: 1,000,000円/月"
    )

    col5, col6 = st.columns(2)
    period_start = col5.date_input("契約期間（開始）", value=None, key="sf_period_start")
    period_end   = col6.date_input("契約期間（終了）", value=None, key="sf_period_end")

    special_terms = st.text_area(
        "変更・追加したい条件（特約事項）",
        key="sf_special_terms",
        placeholder="例: 支払いサイトを60日に変更、機密保持期間を5年に延長 等",
        height=100,
    )
    sales_comment = st.text_area(
        "補足コメント（担当Editorへ）",
        key="sf_sales_comment",
        placeholder="前回との相違点、急ぎの場合はその旨 等",
        height=80,
    )

    # ── 決定論的バリデーション: 必須項目チェック ──
    required_ok = bool(customer_name and customer_name.strip()) and (scheduled_date is not None)

    if not required_ok:
        st.caption("⚠️ 顧客名と締結希望日を入力すると「依頼を提出する」ボタンが有効になります")

    if st.button(
        "📨 依頼を提出する",
        type="primary",
        use_container_width=True,
        disabled=not required_ok,
        key="sf_submit",
    ):
        sched_str = str(scheduled_date) if scheduled_date else ""
        ps_str    = str(period_start) if period_start else ""
        pe_str    = str(period_end) if period_end else ""

        # 送信者の名前を取得
        all_users = db.get_all_users()
        user_name = next((u["name"] for u in all_users if u["email"] == user["email"]), user["email"])

        title = f"{customer_name} - {contract_type}"
        request_id = db.create_transaction(
            title=title,
            requester_email=user["email"],
            scheduled_date=sched_str,
            sales_person=user_name,
            customer_name=customer_name.strip(),
            contract_type=contract_type,
            amount=amount,
            period_start=ps_str,
            period_end=pe_str,
            special_terms=special_terms,
            sales_comment=sales_comment,
        )
        # フォーム状態をクリア
        for k in [k for k in st.session_state if k.startswith("sf_")]:
            del st.session_state[k]

        st.session_state["current_request_id"] = request_id
        st.toast("依頼を提出しました！ダッシュボードで進捗を確認できます。", icon="✅")
        st.session_state["_nav_to_dashboard"] = True
        st.rerun()


# ═══════════════════════════════════════════════════════════
# Sales: 既存依頼の閲覧（読み取り専用）
# ═══════════════════════════════════════════════════════════
def _render_sales_view(tx):
    """Sales が自分の提出済み依頼を閲覧するビュー"""
    st.markdown("### 依頼内容")
    _render_request_summary(tx)

    st.markdown("### ステータス履歴")
    history = st.session_state.get("_status_history")
    st.caption("※ ダッシュボードに戻るには左サイドバーの「ダッシュボード」を選択してください")


# ═══════════════════════════════════════════════════════════
# 依頼内容サマリー（Editor/Admin 上段 & Sales 閲覧用）
# ═══════════════════════════════════════════════════════════
def _render_request_summary(tx):
    """Sales フォームの入力値を読み取り専用で表示"""
    if not tx:
        st.caption("依頼データがありません")
        return

    customer   = tx.get("customer_name", "") or tx.get("title", "")
    ctype      = tx.get("contract_type", "")
    amount     = tx.get("amount", "")
    p_start    = tx.get("period_start", "")
    p_end      = tx.get("period_end", "")
    sched      = tx.get("scheduled_date", "")
    terms      = tx.get("special_terms", "")
    comment    = tx.get("sales_comment", "")
    sales_p    = tx.get("sales_person", "")

    sched_disp = sched.replace("-", "/") if sched else "未設定"
    _, sched_color = _calc_days(sched)

    def _row(label, val, color="#333"):
        if val:
            return (
                f"<div style='margin-bottom:6px;'>"
                f"<span style='font-size:11px;color:#888;'>{label}</span><br>"
                f"<span style='font-size:14px;color:{color};font-weight:500;'>{val}</span>"
                f"</div>"
            )
        return ""

    period_str = ""
    if p_start or p_end:
        period_str = f"{p_start or '?'} 〜 {p_end or '?'}"

    html = (
        "<div style='background:#f8f9fa;border:1px solid #dee2e6;border-radius:8px;"
        "padding:14px 18px;display:flex;gap:24px;flex-wrap:wrap;'>"
        + _row("顧客名", customer)
        + _row("契約種別", ctype)
        + _row("締結希望日", sched_disp, sched_color)
        + _row("金額", amount)
        + _row("契約期間", period_str)
        + _row("営業担当", sales_p)
        + "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)

    if terms:
        st.markdown(
            f"<div style='margin-top:8px;background:#fff3e0;border-left:4px solid #fd7e14;"
            f"padding:8px 12px;border-radius:0 6px 6px 0;font-size:13px;'>"
            f"<b>特約事項:</b> {terms}</div>",
            unsafe_allow_html=True,
        )
    if comment:
        st.markdown(
            f"<div style='margin-top:6px;background:#e8f5e9;border-left:4px solid #198754;"
            f"padding:8px 12px;border-radius:0 6px 6px 0;font-size:13px;'>"
            f"<b>補足コメント:</b> {comment}</div>",
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════════════════════════
# ステータスバナー
# ═══════════════════════════════════════════════════════════
def _render_status_banner(tx):
    if not tx:
        st.info("新規依頼を作成します")
        return

    STATUS_COLORS = {"未着手": "#6c757d", "作業中": "#0d6efd", "承認待ち": "#fd7e14", "完了": "#198754"}
    status    = tx.get("status", "")
    scolor    = STATUS_COLORS.get(status, "#6c757d")
    scheduled = tx.get("scheduled_date", "")
    version   = tx.get("current_version", 1)
    sales     = tx.get("sales_person", "")
    editor_p  = tx.get("editor_person", "")

    days_label, sched_color = _calc_days(scheduled)
    scheduled_disp = scheduled.replace("-", "/") if scheduled else "未設定"

    extras = ""
    if sales:
        extras += f"<div><div style='font-size:11px;color:#888;'>営業担当</div><div style='font-size:14px;'>{sales}</div></div>"
    if editor_p:
        extras += f"<div><div style='font-size:11px;color:#888;'>作業担当</div><div style='font-size:14px;'>{editor_p}</div></div>"

    st.markdown(
        f"""<div style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:8px;
                    padding:12px 18px;margin-bottom:16px;display:flex;
                    align-items:center;gap:20px;flex-wrap:wrap;">
            <div>
                <div style="font-size:11px;color:#888;">案件名</div>
                <div style="font-size:16px;font-weight:700;">{tx.get('title','')}</div>
            </div>
            <div style="border-left:1px solid #ddd;height:40px;"></div>
            <div>
                <div style="font-size:11px;color:#888;">ステータス</div>
                <span style="background:{scolor};color:#fff;padding:3px 14px;
                             border-radius:20px;font-size:14px;font-weight:600;">{status}</span>
            </div>
            <div style="border-left:1px solid #ddd;height:40px;"></div>
            <div>
                <div style="font-size:11px;color:#888;">締結予定日</div>
                <div style="font-size:20px;font-weight:700;color:{sched_color};">
                    📅 {scheduled_disp}
                    <span style="font-size:13px;">{days_label}</span>
                </div>
            </div>
            <div style="border-left:1px solid #ddd;height:40px;"></div>
            <div>
                <div style="font-size:11px;color:#888;">バージョン</div>
                <div style="font-size:15px;font-weight:600;">v{version}</div>
            </div>
            {extras}
        </div>""",
        unsafe_allow_html=True,
    )


def _calc_days(scheduled: str) -> tuple[str, str]:
    if not scheduled:
        return "", "#aaa"
    try:
        delta = (datetime.strptime(scheduled, "%Y-%m-%d") - datetime.today()).days
        if delta < 0:
            return f"（{abs(delta)}日超過）", "#d32f2f"
        elif delta == 0:
            return "（本日）", "#d32f2f"
        elif delta <= 7:
            return f"（残り{delta}日）", "#e65100"
        else:
            return f"（残り{delta}日）", "#2e7d32"
    except ValueError:
        return "", "#555"


# ═══════════════════════════════════════════════════════════
# kintone パネル（左）
# ═══════════════════════════════════════════════════════════
def _render_kintone_panel(tx=None):
    st.markdown("**既存契約データ (kintone)**")

    # 依頼の顧客名を初期値としてプリセット
    default_company = (tx or {}).get("customer_name", "") or ""
    company_name = st.text_input("顧客名で検索", value=default_company, key="kintone_search")

    if st.button("🔍 kintone検索", use_container_width=True):
        if company_name:
            with st.spinner("kintoneを検索中..."):
                try:
                    data = KintoneClient().get_latest_contract(company_name)
                    st.session_state["kintone_data"] = data
                    st.session_state["is_new_customer"] = data is None
                    # Gemini分析キャッシュをクリア（新しいkintoneデータで再分析させる）
                    st.session_state.pop("gemini_analysis", None)
                except Exception as e:
                    st.error(f"kintone検索エラー: {e}")
        else:
            st.warning("顧客名を入力してください。")

    kintone_data = st.session_state.get("kintone_data")
    is_new = st.session_state.get("is_new_customer", False)

    if kintone_data:
        st.success("既存契約データを取得しました")
        st.dataframe(
            [{"項目": k, "値": v} for k, v in kintone_data.items()],
            use_container_width=True, hide_index=True, height=200,
        )
    elif is_new:
        st.warning("**新規顧客**: kintoneにデータがありません。新規契約として処理します。")
    else:
        st.caption("顧客名を入力して「kintone検索」してください")


# ═══════════════════════════════════════════════════════════
# Word生成フォーム + Gemini分析（右）
# ═══════════════════════════════════════════════════════════
def _render_word_form(db, user, role, tx):
    # ── Gemini比較分析セクション ──
    st.markdown("**Gemini AI 比較分析**")

    gemini_ok = bool(st.session_state.get("kintone_data") is not None or st.session_state.get("is_new_customer"))
    if not gemini_ok:
        st.caption("先に「kintone検索」を実行してから分析してください")
    else:
        if st.button("🤖 Gemini 比較分析実行", use_container_width=True, key="gemini_btn"):
            request_data = {
                "customer_name": (tx or {}).get("customer_name", ""),
                "contract_type": (tx or {}).get("contract_type", ""),
                "amount":        (tx or {}).get("amount", ""),
                "period_start":  (tx or {}).get("period_start", ""),
                "period_end":    (tx or {}).get("period_end", ""),
                "special_terms": (tx or {}).get("special_terms", ""),
                "sales_comment": (tx or {}).get("sales_comment", ""),
                "scheduled_date":(tx or {}).get("scheduled_date", ""),
            }
            kintone_data = st.session_state.get("kintone_data")
            with st.spinner("Geminiが比較分析中..."):
                try:
                    agent = GeminiAgent()
                    result = agent.analyze_comparison(request_data, kintone_data)
                    st.session_state["gemini_analysis"] = result
                except Exception as e:
                    st.error(f"Gemini分析エラー: {e}")
            st.rerun()

    analysis = st.session_state.get("gemini_analysis")
    if analysis:
        with st.expander("分析結果", expanded=True):
            st.markdown(analysis)

    st.markdown("---")

    # ── ひな形選択 ──
    st.markdown("**Word生成パラメータ**")
    templates = db.get_active_templates()
    template_options = {t["template_name"]: t for t in templates}
    tmpl_names = ["デフォルト（ローカル）"] + list(template_options.keys())
    selected_tmpl = st.selectbox("使用するひな形", options=tmpl_names, key="tmpl_select")

    tmpl_path = _resolve_template_path(selected_tmpl, template_options)
    if tmpl_path:
        cache_key = f"tmpl_vars_{selected_tmpl}"
        if cache_key not in st.session_state:
            st.session_state[cache_key] = WordGenerator.extract_variables(tmpl_path)
        template_vars: list[str] = st.session_state.get(cache_key, [])
        if template_vars:
            st.caption(f"このひな形の変数: `{'`, `'.join(template_vars)}`")
    else:
        template_vars = []

    # ── 案件切り替え時フォームリセット ──
    curr_rid = st.session_state.get("current_request_id")
    if st.session_state.get("_form_request_id") != curr_rid:
        for k in [k for k in st.session_state if k.startswith("f_")]:
            del st.session_state[k]
        st.session_state["_form_request_id"] = curr_rid

    # ── 動的フォーム生成 ──
    defaults = _get_defaults(tx)
    params, meta = _build_dynamic_form(template_vars, defaults, user, tx, role)

    # ── バリデーション（決定論的ルールエンジン）──
    rules     = db.get_active_validation_rules()
    engine    = RuleEngine(rules)
    v_results = engine.validate({**params, **meta}, selected_tmpl)

    errors   = [r for r in v_results if r.action_type == "ERROR"]
    warnings = [r for r in v_results if r.action_type == "WARNING"]
    forced   = RuleEngine.get_force_approvers(v_results)

    for err in errors:
        st.error(f"エラー: {err.rule_message}")
    for warn in warnings:
        st.warning(f"警告: {warn.rule_message}")
    if forced:
        st.info(f"承認者が自動追加されます: {', '.join(forced)}")

    has_errors = bool(errors)

    col_gen, col_approve = st.columns(2)
    generate_btn = col_gen.button(
        "📄 Word生成", type="primary", use_container_width=True, key="gen_btn",
        disabled=has_errors,
    )
    approve_btn = col_approve.button(
        "✅ 承認申請",
        use_container_width=True,
        disabled=(role == "Sales" or has_errors),
        key="approve_btn",
    )

    if generate_btn:
        _handle_word_generate(db, user, params, meta, selected_tmpl, template_options, tmpl_path)
    if approve_btn:
        _handle_approve(db, user, params, meta)


# ═══════════════════════════════════════════════════════════
# 動的フォーム（Word生成パラメータ編集）
# ═══════════════════════════════════════════════════════════
def _build_dynamic_form(template_vars, defaults, user, tx, role) -> tuple[dict, dict]:
    if template_vars:
        form_vars = [v for v in template_vars if v != "contract_type"]
    else:
        form_vars = ["company_name", "contract_amount", "start_date", "end_date",
                     "payment_terms", "special_notes"]

    params: dict = {}
    if template_vars:
        params["contract_type"] = defaults.get("contract_type", "")

    for var in form_vars:
        label, input_type, required = WordGenerator.get_field_info(var)
        label_display = f"{label} {'*' if required else ''}"
        default_val   = defaults.get(var, "")

        if input_type == "textarea":
            params[var] = st.text_area(label_display, value=default_val, height=80, key=f"f_{var}")
        elif input_type == "date":
            params[var] = st.text_input(label_display, value=default_val, placeholder="YYYY-MM-DD", key=f"f_{var}")
        elif input_type == "hidden":
            params[var] = default_val
        else:
            params[var] = st.text_input(label_display, value=default_val, key=f"f_{var}")

    st.markdown("---")
    st.markdown("**案件管理情報**")
    col_m1, col_m2 = st.columns(2)

    scheduled_default = (tx or {}).get("scheduled_date", "") or defaults.get("expected_conclusion_date", "")
    scheduled_date = col_m1.text_input(
        "締結予定日", value=scheduled_default, placeholder="YYYY-MM-DD", key="f_scheduled_date"
    )
    sales_person = col_m2.text_input(
        "営業担当", value=(tx or {}).get("sales_person", user.get("name", "")), key="f_sales_person"
    )
    editor_person = st.text_input(
        "作業担当", value=(tx or {}).get("editor_person", ""), key="f_editor_person"
    )

    meta = {
        "scheduled_date": scheduled_date,
        "sales_person":   sales_person,
        "editor_person":  editor_person,
    }
    return params, meta


# ═══════════════════════════════════════════════════════════
# テンプレートパス解決
# ═══════════════════════════════════════════════════════════
def _resolve_template_path(selected_tmpl: str, template_options: dict) -> str | None:
    is_mock = (
        os.getenv("DEV_MODE", "false").lower() == "true"
        or os.getenv("USE_MOCK_KINTONE", "false").lower() == "true"
    )
    if selected_tmpl == "デフォルト（ローカル）":
        for p in [_DEFAULT_TEMPLATE, _FALLBACK_TEMPLATE]:
            if os.path.exists(p):
                return p
        return None

    if selected_tmpl in template_options:
        drive_url = template_options[selected_tmpl].get("drive_url", "")
        if is_mock or "mock" in drive_url.lower():
            st.info("Mockモード: ローカルテンプレートを使用します。", icon="ℹ️")
            for p in [_DEFAULT_TEMPLATE, _FALLBACK_TEMPLATE]:
                if os.path.exists(p):
                    return p
            return None
        try:
            uploader = DriveUploader()
            file_id = uploader.extract_file_id(drive_url)
            if file_id:
                local_path = os.path.join(tempfile.gettempdir(), f"tmpl_{file_id}.docx")
                if not os.path.exists(local_path):
                    uploader.download_to_path(file_id, local_path)
                return local_path
        except Exception as e:
            st.warning(f"Driveからのダウンロード失敗。ローカルにフォールバック: {e}")

    for p in [_DEFAULT_TEMPLATE, _FALLBACK_TEMPLATE]:
        if os.path.exists(p):
            return p
    return None


# ═══════════════════════════════════════════════════════════
# デフォルト値（Sales フォームデータ → Word生成パラメータ）
# ═══════════════════════════════════════════════════════════
def _get_defaults(tx) -> dict:
    """Sales フォームの入力値を Word生成パラメータのデフォルトにマッピング（AIを介さない決定論的コピー）"""
    kt = st.session_state.get("kintone_data") or {}
    tx = tx or {}
    return {
        "company_name":    tx.get("customer_name")  or kt.get("company_name", ""),
        "contract_type":   tx.get("contract_type")  or kt.get("contract_type", ""),
        "contract_amount": tx.get("amount")          or kt.get("contract_amount", ""),
        "start_date":      tx.get("period_start")    or kt.get("start_date", ""),
        "end_date":        tx.get("period_end")       or kt.get("end_date", ""),
        "payment_terms":   kt.get("payment_terms", ""),
        "special_notes":   tx.get("special_terms")   or "",
        "expected_conclusion_date": tx.get("scheduled_date", ""),
    }


# ═══════════════════════════════════════════════════════════
# Word生成ハンドラ
# ═══════════════════════════════════════════════════════════
def _handle_word_generate(db, user, params, meta, selected_tmpl, template_options, tmpl_path):
    if not params.get("company_name"):
        st.error("顧客名を入力してください。")
        return
    with st.spinner("Wordファイルを生成中..."):
        try:
            gen = WordGenerator(tmpl_path)
            output_file = os.path.join(
                tempfile.gettempdir(),
                f"contract_{params['company_name']}_{date.today()}.docx",
            )
            gen.generate(params, output_file)

            uploader  = DriveUploader()
            drive_url = uploader.upload(output_file, "生成済み契約書")
            st.session_state["generated_drive_url"] = drive_url

            request_id = st.session_state.get("current_request_id")
            title = f"{params.get('company_name','?')} - {params.get('contract_type', meta.get('contract_type',''))}"
            if not request_id:
                request_id = db.create_transaction(
                    title, user["email"],
                    scheduled_date=meta.get("scheduled_date", ""),
                    sales_person=meta.get("sales_person", ""),
                    editor_person=meta.get("editor_person", ""),
                    customer_name=params.get("company_name", ""),
                    contract_type=params.get("contract_type", ""),
                )
                st.session_state["current_request_id"] = request_id
                db.update_transaction_status(request_id, "作業中", user["email"], "Word生成")
            else:
                db.update_transaction(request_id, {"title": title, **meta})

            st.toast("Word生成 & Driveアップロード完了", icon="✅")
            if "mock" not in drive_url.lower():
                st.link_button("📂 Google Driveで開く", drive_url)
        except FileNotFoundError as e:
            st.error(f"テンプレートが見つかりません: {e}")
        except Exception as e:
            st.error(f"Word生成エラー: {e}")


# ═══════════════════════════════════════════════════════════
# 承認申請ハンドラ
# ═══════════════════════════════════════════════════════════
def _handle_approve(db, user, params, meta):
    if not params.get("company_name"):
        st.error("顧客名を入力してください。")
        return
    request_id = st.session_state.get("current_request_id")
    title = f"{params.get('company_name','?')} - {params.get('contract_type', '')}"
    if not request_id:
        request_id = db.create_transaction(
            title, user["email"],
            scheduled_date=meta.get("scheduled_date", ""),
            sales_person=meta.get("sales_person", ""),
            editor_person=meta.get("editor_person", ""),
            customer_name=params.get("company_name", ""),
            contract_type=params.get("contract_type", ""),
        )
        st.session_state["current_request_id"] = request_id
    else:
        db.update_transaction(request_id, {"title": title, **meta})
    db.update_transaction_status(request_id, "承認待ち", user["email"], "承認申請")
    st.toast("承認申請しました", icon="✅")
    st.rerun()


# ═══════════════════════════════════════════════════════════
# 承認操作パネル
# ═══════════════════════════════════════════════════════════
def _render_approval_panel(db, request_id, email):
    st.subheader("③ 承認操作")
    is_approver = is_workflow_approver(db, request_id)
    if not is_approver:
        st.info("このステップの承認者のみ操作できます。")
    comment = st.text_input("コメント（任意）", key="approve_comment")
    c1, c2, _ = st.columns([1, 1, 3])
    with c1:
        if st.button("✅ 承認", type="primary", disabled=not is_approver, use_container_width=True):
            db.update_transaction_status(request_id, "完了", email, comment)
            st.toast("承認しました", icon="✅")
            st.rerun()
    with c2:
        if st.button("↩️ 差し戻し", disabled=not is_approver, use_container_width=True):
            db.update_transaction_status(request_id, "作業中", email, f"差し戻し: {comment}")
            st.toast("差し戻しました", icon="↩️")
            st.rerun()
