"""管理設定画面 - ユーザー管理・承認フロー・監査ログ (v1.2)"""
import streamlit as st
from utils.auth import check_access
from pages.rules import render_mermaid, build_mermaid_diagram


def show(db):
    check_access(roles=("Admin",))
    st.title("⚙️ 管理設定")

    tab1, tab2, tab3 = st.tabs(["👥 ユーザー管理", "🔀 承認フロー設定", "📜 監査ログ"])

    # ═══════════════════════════════════════════
    # タブ1: ユーザー管理
    # ═══════════════════════════════════════════
    with tab1:
        st.subheader("ユーザー一覧")
        users = db.get_all_users()

        if users:
            for u in users:
                with st.container(border=True):
                    c1, c2, c3, c4, c5 = st.columns([3, 3, 2, 1, 1])
                    c1.write(u.get("email", ""))
                    c2.write(u.get("name", ""))
                    new_role = c3.selectbox(
                        "ロール",
                        options=["Sales", "Editor", "Admin"],
                        index=["Sales", "Editor", "Admin"].index(u.get("role", "Sales")),
                        key=f"role_{u['email']}",
                        label_visibility="collapsed",
                    )
                    if c4.button("保存", key=f"save_{u['email']}"):
                        db.update_user(u["email"], {"role": new_role})
                        st.success(f"ロールを {new_role} に変更しました。")
                        st.rerun()
                    if c5.button("削除", key=f"del_{u['email']}"):
                        db.delete_user(u["email"])
                        st.rerun()
        else:
            st.info("ユーザーが登録されていません。")

        st.divider()
        st.subheader("新規ユーザー追加")
        with st.form("add_user_form"):
            col1, col2, col3 = st.columns(3)
            new_email = col1.text_input("メールアドレス")
            new_name = col2.text_input("氏名")
            new_role = col3.selectbox("ロール", options=["Sales", "Editor", "Admin"])
            if st.form_submit_button("追加", type="primary"):
                if new_email and new_name:
                    db.add_user(new_email, new_name, new_role)
                    st.success(f"{new_email} を追加しました。")
                    st.rerun()
                else:
                    st.warning("全項目を入力してください。")

    # ═══════════════════════════════════════════
    # タブ2: 承認フロー設定（読み取り & Mermaid表示）
    # ═══════════════════════════════════════════
    with tab2:
        st.subheader("現在の承認フロー")
        workflow = db.get_workflow()

        if workflow:
            render_mermaid(build_mermaid_diagram(workflow), height=250)
            st.divider()
            st.markdown("**ステップ詳細**")
            for step in workflow:
                color = "#6c757d"
                with st.container(border=True):
                    c1, c2, c3 = st.columns([1, 3, 3])
                    c1.metric("Step", step.get("step_order", ""))
                    c2.write(f"**{step.get('step_name', '')}**")
                    c3.caption(f"承認者: {step.get('approver_email', '（未設定）')}")
        else:
            st.info("ワークフローが設定されていません。「ルール管理」→「ワークフローデザイナー」で設定してください。")

        st.info("フローの編集は「📋 ルール管理」の「ワークフローデザイナー」で行えます。")

    # ═══════════════════════════════════════════
    # タブ3: 監査ログ
    # ═══════════════════════════════════════════
    with tab3:
        st.subheader("監査ログ（バージョン履歴）")
        transactions = db.get_all_transactions()

        if not transactions:
            st.info("案件がありません。")
            return

        options = {
            f"{t['request_id']} - {t['title']}": t["request_id"]
            for t in transactions
        }
        selected = st.selectbox("案件を選択", options=list(options.keys()))
        request_id = options[selected]

        # 案件サマリー
        tx = db.get_transaction(request_id)
        if tx:
            cols = st.columns(4)
            cols[0].metric("ステータス", tx.get("status", ""))
            cols[1].metric("バージョン", f"v{tx.get('current_version', 1)}")
            cols[2].metric("締結予定日", tx.get("scheduled_date", "-"))
            cols[3].metric("営業担当", tx.get("sales_person", "-"))

        st.divider()
        history = db.get_status_history(request_id)
        if history:
            st.markdown("**タイムライン**")
            for h in sorted(history, key=lambda x: x.get("changed_at", "")):
                with st.container(border=True):
                    c1, c2 = st.columns([2, 3])
                    c1.markdown(f"**{(h.get('changed_at') or '')[:16]}**")
                    c1.caption(f"変更者: {h.get('changed_by', '')}")
                    c2.markdown(f"ステータス: **{h.get('status', '')}** (v{h.get('version', '')})")
                    if h.get("comment"):
                        c2.caption(f"💬 {h.get('comment', '')}")
        else:
            st.info("この案件の履歴がありません。")
