"""ダッシュボード - 期限超過アラート付きカンバン (v1.4)"""
from datetime import datetime

import streamlit as st
from utils.auth import check_access

STATUSES   = ["未着手", "作業中", "承認待ち", "完了"]
STATUS_CLR = {"未着手": "#6c757d", "作業中": "#0d6efd", "承認待ち": "#fd7e14", "完了": "#198754"}
STATUS_BG  = {"未着手": "#f8f9fa", "作業中": "#e8f0fe", "承認待ち": "#fff3e0", "完了": "#e8f5e9"}

TODAY = datetime.today().date()


def show(db):
    user = check_access()
    role  = user.get("role")
    email = user.get("email")

    st.title("🏠 ダッシュボード")

    # 新規依頼ボタン
    col_new, _ = st.columns([1, 6])
    with col_new:
        if st.button("＋ 新規依頼", type="primary", use_container_width=True):
            for k in ["current_request_id", "ai_result", "kintone_data", "diff_summary", "request_text"]:
                st.session_state[k] = None if k != "request_text" else ""
            st.session_state["_nav_to_workspace"] = True
            st.rerun()

    transactions = db.get_all_transactions()
    if role == "Sales":
        transactions = [t for t in transactions if t.get("requester_email") == email]

    by_status = {s: [] for s in STATUSES}
    for tx in transactions:
        s = tx.get("status", "未着手")
        if s in by_status:
            by_status[s].append(tx)

    # ── 件数サマリー ──
    overdue_count = sum(1 for tx in transactions if _is_overdue(tx.get("scheduled_date", "")))
    if overdue_count > 0:
        st.markdown(
            f"<div style='background:#ffebee;border-left:4px solid #d32f2f;padding:10px 16px;"
            f"border-radius:6px;margin-bottom:12px;font-size:15px;'>"
            f"⚠️ <b>期限超過の案件が {overdue_count} 件あります</b></div>",
            unsafe_allow_html=True,
        )

    metric_cols = st.columns(4)
    for i, status in enumerate(STATUSES):
        color = STATUS_CLR[status]
        count = len(by_status[status])
        overdue = sum(1 for tx in by_status[status] if _is_overdue(tx.get("scheduled_date", "")))
        badge = f" <span style='color:#d32f2f;font-size:13px;'>（{overdue}件超過）</span>" if overdue else ""
        metric_cols[i].markdown(
            f"<div style='background:{STATUS_BG[status]};border-left:4px solid {color};"
            f"padding:12px;border-radius:6px;text-align:center;'>"
            f"<div style='font-size:28px;font-weight:700;color:{color};'>{count}</div>"
            f"<div style='font-size:14px;color:#555;'>{status}{badge}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # ── カンバン列 ──
    cols = st.columns(4)
    for i, status in enumerate(STATUSES):
        with cols[i]:
            color = STATUS_CLR[status]
            st.markdown(
                f"<div style='font-size:16px;font-weight:700;color:{color};"
                f"border-bottom:2px solid {color};padding-bottom:6px;margin-bottom:8px;'>"
                f"{status}</div>",
                unsafe_allow_html=True,
            )
            if not by_status[status]:
                st.markdown(
                    "<div style='color:#aaa;font-size:13px;text-align:center;padding:20px 0;'>"
                    "案件なし</div>",
                    unsafe_allow_html=True,
                )
            for tx in sorted(by_status[status], key=lambda x: x.get("last_updated_at", ""), reverse=True):
                _render_card(tx, color)


def _is_overdue(scheduled_date: str) -> bool:
    """締結予定日が今日より過去かどうかを判定"""
    if not scheduled_date:
        return False
    try:
        return datetime.strptime(scheduled_date, "%Y-%m-%d").date() < TODAY
    except ValueError:
        return False


def _render_card(tx: dict, color: str):
    request_id    = tx.get("request_id", "")
    title         = tx.get("title", "（タイトルなし）")
    updated       = (tx.get("last_updated_at") or "")[:16]
    scheduled     = tx.get("scheduled_date", "")
    sales         = tx.get("sales_person", "")
    editor        = tx.get("editor_person", "")
    overdue       = _is_overdue(scheduled)

    scheduled_disp = scheduled.replace("-", "/") if scheduled else "未設定"

    # 期限超過: 赤背景カード
    card_style = (
        "background:#fff8f8;border:2px solid #ef9a9a;border-radius:8px;padding:10px 12px;margin-bottom:8px;"
        if overdue else
        "background:#fff;border:1px solid #e0e0e0;border-radius:8px;padding:10px 12px;margin-bottom:8px;"
    )

    # 締結予定日の表示スタイル
    if overdue:
        sched_html = (
            f"<div style='font-size:13px;color:#d32f2f;font-weight:700;'>"
            f"⚠️ 締結予定: {scheduled_disp}（期限超過）</div>"
        )
    elif scheduled:
        sched_html = f"<div style='font-size:13px;color:{color};font-weight:500;'>📅 締結予定: {scheduled_disp}</div>"
    else:
        sched_html = "<div style='font-size:12px;color:#aaa;'>📅 締結予定: 未設定</div>"

    editor_html = f"<div style='font-size:12px;color:#555;'>✏️ 作業担当: {editor}</div>" if editor else ""
    sales_html  = f"<div style='font-size:12px;color:#555;'>👤 営業担当: {sales}</div>" if sales else ""

    with st.container():
        st.markdown(
            f"<div style='{card_style}'>"
            f"<div style='font-weight:600;font-size:14px;margin-bottom:4px;'>{title}</div>"
            f"{sched_html}"
            f"{editor_html}"
            f"{sales_html}"
            f"<div style='font-size:11px;color:#999;margin-top:3px;'>更新: {updated}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if st.button("開く →", key=f"open_{request_id}", use_container_width=True, type="secondary"):
            for k in ["ai_result", "kintone_data", "diff_summary", "request_text"]:
                st.session_state[k] = None if k != "request_text" else ""
            st.session_state["current_request_id"] = request_id
            st.session_state["_nav_to_workspace"] = True
            st.rerun()
