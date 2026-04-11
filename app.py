"""契約書作成自動化システム - メインアプリ (v1.3)"""
import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="契約書作成自動化システム",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# サイドバーのフォントサイズを拡大するCSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
/* サイドバー全体のフォントサイズ */
[data-testid="stSidebar"] {
    font-size: 16px !important;
}
/* ナビゲーションリンクのフォントサイズ */
[data-testid="stSidebarNavLink"] span,
[data-testid="stSidebarNav"] a span {
    font-size: 17px !important;
    font-weight: 500 !important;
}
/* ナビゲーションリンクの余白 */
[data-testid="stSidebarNavLink"] {
    padding: 0.6rem 1rem !important;
    border-radius: 6px !important;
}
/* ユーザー情報テキスト */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] small {
    font-size: 15px !important;
}
/* アクティブなナビゲーションリンク */
[data-testid="stSidebarNavLink"][aria-current="page"] {
    background-color: rgba(255,75,75,0.1) !important;
    font-weight: 700 !important;
}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_db():
    from services.sheets_db import SheetsDB
    return SheetsDB()


def main():
    db = get_db()

    from utils.auth import initialize_auth
    user = initialize_auth(db)

    if user is None:
        st.title("📄 契約書作成自動化システム")
        st.info("ログインしてください。")
        if os.getenv("DEV_MODE", "false").lower() == "true":
            st.warning("DEV_MODE が有効です。Admin として自動ログインします。")
            st.rerun()
        return

    role = user.get("role", "Sales")

    # ─────────────────────────────────────────────
    # サイドバー: ユーザー情報
    # ─────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            f"""
            <div style="padding:10px 0 6px 0; border-bottom:1px solid #eee; margin-bottom:8px;">
                <div style="font-size:18px; font-weight:700;">📄 契約書作成自動化</div>
                <div style="font-size:15px; margin-top:4px;">
                    {user.get('name', user.get('email', ''))}
                </div>
                <div style="font-size:13px; color:#888;">ロール: {role}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ─────────────────────────────────────────────
    # ページ定義
    # ─────────────────────────────────────────────
    from pages import dashboard, workspace, admin, rules, templates_mgmt

    def _dash():
        dashboard.show(db)

    def _work():
        workspace.show(db)

    def _admin():
        admin.show(db)

    def _rules():
        rules.show(db)

    def _templates():
        templates_mgmt.show(db)

    dash_page = st.Page(_dash, title="ダッシュボード", icon="🏠", default=True)
    work_page = st.Page(_work, title="契約作成・編集", icon="📝")

    nav_structure = {
        "メインメニュー": [dash_page, work_page]
    }

    if role == "Admin":
        nav_structure["管理者メニュー"] = [
            st.Page(_admin,     title="管理設定",   icon="⚙️"),
            st.Page(_rules,     title="ルール管理", icon="📋"),
            st.Page(_templates, title="ひな形管理", icon="📁"),
        ]

    # ─────────────────────────────────────────────
    # ダッシュボード「開く」ボタンからのページ遷移
    # ─────────────────────────────────────────────
    if st.session_state.pop("_nav_to_workspace", False):
        st.switch_page(work_page)

    pg = st.navigation(nav_structure)

    # ログアウトボタン
    with st.sidebar:
        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
        if st.button("ログアウト", use_container_width=True, key="logout_btn"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.cache_resource.clear()
            st.rerun()

    pg.run()


if __name__ == "__main__":
    main()
