"""作業画面 - 動的フォーム生成 (v1.4)"""
import os
import tempfile
from datetime import date, datetime

import streamlit as st
from utils.auth import check_access, is_workflow_approver
from services.ai_agent import AIAgent
from services.kintone_api import KintoneClient
from services.word_generator import WordGenerator
from services.drive_uploader import DriveUploader

_FALLBACK_TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "assets", "templates", "default.docx")
_DEFAULT_TEMPLATE  = os.path.join(os.path.dirname(__file__), "..", "templates", "contract_template.docx")


def show(db):
    user = check_access(roles=("Editor", "Admin", "Sales"))
    role  = user.get("role")
    email = user.get("email")

    st.title("📝 契約作成・編集")

    request_id = st.session_state.get("current_request_id")
    tx = db.get_transaction(request_id) if request_id else None

    # ─── ステータスバナー ───
    _render_status_banner(tx)

    # ═══════════════════════════════════════════
    # 上段: 依頼文 & AI解析
    # ═══════════════════════════════════════════
    st.subheader("① 依頼内容・AI解析")
    top_left, top_right = st.columns(2)

    with top_left:
        st.markdown("**営業からの依頼文**")
        request_text = st.text_area(
            "依頼文",
            value=st.session_state.get("request_text", ""),
            height=180,
            placeholder="例: 株式会社〇〇との業務委託契約を4月末までに締結したい。金額は月100万円、期間は2025年4月〜12月末...",
            label_visibility="collapsed",
        )
        if st.button("🤖 AI解析", type="primary", use_container_width=True):
            if not request_text.strip():
                st.warning("依頼文を入力してください。")
            else:
                with st.spinner("AIが依頼文を解析中..."):
                    try:
                        agent = AIAgent()
                        result = agent.analyze_request(request_text)
                        st.session_state["ai_result"] = result.model_dump()
                        st.session_state["request_text"] = request_text
                        st.success("✅ 解析完了")
                        st.rerun()
                    except Exception as e:
                        st.error(f"AI解析エラー: {e}")

    with top_right:
        st.markdown("**AI解析結果**")
        ai_result = st.session_state.get("ai_result")
        if ai_result:
            st.json(ai_result)
            # 締結予定日が抽出された場合に通知
            ecd = ai_result.get("expected_conclusion_date", "")
            if ecd:
                st.success(f"📅 締結希望日を検出: **{ecd}** → 締結予定日に自動入力済み")
        else:
            st.caption("「🤖 AI解析」を押すと契約項目が自動抽出されます")
            st.markdown(
                """<div style="color:#888;font-size:13px;padding:8px 0;">
                抽出される項目:<br>・顧客名・契約種別・契約金額<br>
                ・開始日・終了日・支払条件<br>・特記事項・<b>締結希望日（新）</b>
                </div>""",
                unsafe_allow_html=True,
            )

    st.divider()

    # ═══════════════════════════════════════════
    # 下段: kintone（左） & 動的Wordフォーム（右）
    # ═══════════════════════════════════════════
    st.subheader("② 既存データ確認 & パラメータ編集")
    bottom_left, bottom_right = st.columns(2)

    # ─── 下段左: kintone ───
    with bottom_left:
        _render_kintone_panel()

    # ─── 下段右: 動的Wordフォーム ───
    with bottom_right:
        _render_word_form(db, user, role, tx)

    # ─── 承認操作 ───
    if tx and tx.get("status") == "承認待ち":
        st.divider()
        _render_approval_panel(db, request_id, email)


# ─────────────────────────────────────────────
# ステータスバナー
# ─────────────────────────────────────────────
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

    # 残り日数
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


# ─────────────────────────────────────────────
# kintoneパネル
# ─────────────────────────────────────────────
def _render_kintone_panel():
    st.markdown("**既存契約データ (kintone)**")
    default_company = (st.session_state.get("ai_result") or {}).get("company_name", "")
    company_name = st.text_input("顧客名で検索", value=default_company, key="kintone_search")

    if st.button("🔍 kintone検索", use_container_width=True):
        if company_name:
            with st.spinner("kintoneを検索中..."):
                try:
                    data = KintoneClient().get_latest_contract(company_name)
                    st.session_state["kintone_data"] = data
                    st.session_state["is_new_customer"] = data is None
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
        if st.button("📊 差異確認（AI）", use_container_width=True):
            ai_res = st.session_state.get("ai_result")
            if not ai_res:
                st.warning("先に「🤖 AI解析」を実行してください。")
            else:
                with st.spinner("AIが差異を分析中..."):
                    try:
                        summary = AIAgent().generate_diff_summary(kintone_data, ai_res)
                        st.session_state["diff_summary"] = summary
                    except Exception as e:
                        st.error(f"差異分析エラー: {e}")
        diff = st.session_state.get("diff_summary")
        if diff:
            with st.expander("変更サマリー", expanded=True):
                st.markdown(diff)
    elif is_new:
        st.warning("**新規顧客モード**: kintoneにデータがありません。AIの解析結果から初期値を生成します。")
        if not st.session_state.get("ai_result"):
            st.info("上の「🤖 AI解析」を先に実行してください。")
    else:
        st.caption("顧客名を入力して「kintone検索」してください")


# ─────────────────────────────────────────────
# 動的Wordフォーム（v1.4 コア機能）
# ─────────────────────────────────────────────
def _render_word_form(db, user, role, tx):
    st.markdown("**Word生成パラメータ**")

    templates = db.get_active_templates()
    template_options = {t["template_name"]: t for t in templates}

    # ── ひな形選択 ──
    tmpl_names = ["デフォルト（ローカル）"] + list(template_options.keys())
    selected_tmpl = st.selectbox("使用するひな形", options=tmpl_names, key="tmpl_select")

    # ── 選択されたひな形のテンプレートパスを解決し変数を抽出 ──
    tmpl_path = _resolve_template_path(selected_tmpl, template_options)
    if tmpl_path:
        cache_key = f"tmpl_vars_{selected_tmpl}"
        if cache_key not in st.session_state:
            vars_found = WordGenerator.extract_variables(tmpl_path)
            st.session_state[cache_key] = vars_found

        template_vars: list[str] = st.session_state.get(cache_key, [])

        if template_vars:
            st.caption(f"このひな形の変数: `{'`, `'.join(template_vars)}`")
        else:
            st.caption("変数が検出されませんでした。標準フォームを使用します。")
    else:
        template_vars = []

    # ── 動的フォーム生成 ──
    defaults = _get_defaults(tx)
    params, meta = _build_dynamic_form(template_vars, defaults, user, tx, role)

    col_gen, col_approve = st.columns(2)
    generate_btn = col_gen.button("📄 Word生成", type="primary", use_container_width=True, key="gen_btn")
    approve_btn  = col_approve.button(
        "✅ 承認申請",
        use_container_width=True,
        disabled=(role == "Sales"),
        key="approve_btn",
    )

    if generate_btn:
        _handle_word_generate(db, user, params, meta, selected_tmpl, template_options, tmpl_path)
    if approve_btn:
        _handle_approve(db, user, params, meta)


def _build_dynamic_form(
    template_vars: list[str],
    defaults: dict,
    user: dict,
    tx,
    role: str,
) -> tuple[dict, dict]:
    """
    template_vars が空なら標準フォームを、
    ある場合はその変数に対応する入力欄のみを生成する。
    contract_type は非表示（テンプレートから決定）。
    返り値: (params dict, meta dict)
    """
    # フォームに使う変数リスト決定
    if template_vars:
        # contract_type は hidden（フォームから除外）
        form_vars = [v for v in template_vars if v != "contract_type"]
    else:
        # 標準セット
        form_vars = ["company_name", "contract_amount", "start_date", "end_date",
                     "payment_terms", "special_notes"]

    params: dict = {}
    if template_vars:
        # contract_type はデフォルト値から自動セット（フォームには出さない）
        params["contract_type"] = defaults.get("contract_type", "業務委託契約")

    with st.form("word_form"):
        # ── 変数フォーム ──
        for var in form_vars:
            label, input_type, required = WordGenerator.get_field_info(var)
            label_display = f"{label} {'*' if required else ''}"
            default_val = defaults.get(var, "")

            if input_type == "textarea":
                params[var] = st.text_area(label_display, value=default_val, height=80, key=f"f_{var}")
            elif input_type == "date":
                params[var] = st.text_input(label_display, value=default_val, placeholder="YYYY-MM-DD", key=f"f_{var}")
            elif input_type == "hidden":
                params[var] = default_val  # フォームに出さずそのまま
            else:
                params[var] = st.text_input(label_display, value=default_val, key=f"f_{var}")

        st.markdown("---")
        st.markdown("**案件管理情報**")
        col_m1, col_m2 = st.columns(2)

        # 締結予定日: AI抽出結果 or 既存トランザクションから自動補完
        scheduled_default = (
            defaults.get("expected_conclusion_date")   # AI が抽出した締結希望日
            or (tx or {}).get("scheduled_date", "")
        )
        scheduled_date = col_m1.text_input(
            "締結予定日", value=scheduled_default, placeholder="YYYY-MM-DD"
        )
        sales_person   = col_m2.text_input(
            "営業担当", value=(tx or {}).get("sales_person", user.get("name", ""))
        )
        editor_person  = st.text_input(
            "作業担当", value=(tx or {}).get("editor_person", "")
        )

        # ── フォーム送信ボタンはフォーム外で管理するため、ここでは dummy ──
        st.form_submit_button("（このボタンは使用しません）", disabled=True)

    meta = {
        "scheduled_date": scheduled_date,
        "sales_person": sales_person,
        "editor_person": editor_person,
    }
    return params, meta


# ─────────────────────────────────────────────
# テンプレートパス解決
# ─────────────────────────────────────────────
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


# ─────────────────────────────────────────────
# デフォルト値取得
# ─────────────────────────────────────────────
def _get_defaults(tx) -> dict:
    ai = st.session_state.get("ai_result") or {}
    kt = st.session_state.get("kintone_data") or {}
    return {
        "company_name":              ai.get("company_name")              or kt.get("company_name", ""),
        "contract_type":             ai.get("contract_type")             or kt.get("contract_type", "業務委託契約"),
        "contract_amount":           ai.get("contract_amount")           or kt.get("contract_amount", ""),
        "start_date":                ai.get("start_date")                or kt.get("start_date", str(date.today())),
        "end_date":                  ai.get("end_date")                  or kt.get("end_date", ""),
        "payment_terms":             ai.get("payment_terms")             or kt.get("payment_terms", ""),
        "special_notes":             ai.get("special_notes", ""),
        "expected_conclusion_date":  ai.get("expected_conclusion_date", ""),
    }


# ─────────────────────────────────────────────
# Word生成ハンドラ
# ─────────────────────────────────────────────
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

            uploader = DriveUploader()
            drive_url = uploader.upload(output_file, "生成済み契約書")
            st.session_state["generated_drive_url"] = drive_url

            request_id = st.session_state.get("current_request_id")
            title = f"{params.get('company_name','?')} - {params.get('contract_type','')}"
            if not request_id:
                request_id = db.create_transaction(
                    title, user["email"],
                    scheduled_date=meta.get("scheduled_date", ""),
                    sales_person=meta.get("sales_person", ""),
                    editor_person=meta.get("editor_person", ""),
                )
                st.session_state["current_request_id"] = request_id
                db.update_transaction_status(request_id, "作業中", user["email"], "Word生成")
            else:
                db.update_transaction(request_id, {"title": title, **meta})

            st.toast("✅ Word生成 & Driveアップロード完了", icon="✅")
            if "mock" not in drive_url.lower():
                st.link_button("📂 Google Driveで開く", drive_url)
        except FileNotFoundError as e:
            st.error(f"テンプレートが見つかりません: {e}")
        except Exception as e:
            st.error(f"Word生成エラー: {e}")


# ─────────────────────────────────────────────
# 承認申請ハンドラ
# ─────────────────────────────────────────────
def _handle_approve(db, user, params, meta):
    if not params.get("company_name"):
        st.error("顧客名を入力してください。")
        return
    request_id = st.session_state.get("current_request_id")
    title = f"{params.get('company_name','?')} - {params.get('contract_type','')}"
    if not request_id:
        request_id = db.create_transaction(
            title, user["email"],
            scheduled_date=meta.get("scheduled_date", ""),
            sales_person=meta.get("sales_person", ""),
            editor_person=meta.get("editor_person", ""),
        )
        st.session_state["current_request_id"] = request_id
    else:
        db.update_transaction(request_id, {"title": title, **meta})
    db.update_transaction_status(request_id, "承認待ち", user["email"], "承認申請")
    st.toast("✅ 承認申請しました", icon="✅")
    st.rerun()


# ─────────────────────────────────────────────
# 承認操作パネル
# ─────────────────────────────────────────────
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
