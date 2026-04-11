"""認証・権限管理モジュール（RBAC）"""
import os
import functools
from typing import Optional

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

ROLES = ("Sales", "Editor", "Admin")
DEV_USER = {
    "email": "dev@localhost",
    "name": "開発者（DevMode）",
    "role": "Admin",
}


def get_current_user() -> Optional[dict]:
    """セッションからログインユーザーを取得する"""
    return st.session_state.get("current_user")


def login_required(func=None, *, roles: tuple = None):
    """
    ログイン必須デコレータ。roles を指定するとロール制限も行う。
    ページ関数の先頭で呼び出すか、デコレータとして使用する。
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if user is None:
                st.error("ログインが必要です。")
                st.stop()
            if roles and user.get("role") not in roles:
                st.error(f"このページへのアクセス権限がありません（必要なロール: {', '.join(roles)}）")
                st.stop()
            return f(*args, **kwargs)
        return wrapper

    if func is not None:
        return decorator(func)
    return decorator


def check_access(roles: tuple = None) -> dict:
    """
    ページ先頭でアクセス制御チェックを行い、ユーザー情報を返す。
    権限不足の場合は st.stop() で処理を停止する。
    """
    user = get_current_user()
    if user is None:
        st.error("ログインが必要です。サイドバーからログインしてください。")
        st.stop()
    if roles and user.get("role") not in roles:
        st.error(f"このページへのアクセス権限がありません（必要なロール: {', '.join(roles)}）")
        st.stop()
    return user


def initialize_auth(db) -> Optional[dict]:
    """
    認証処理を行い、ログインユーザーをセッションに保存する。
    DEV_MODE=true の場合は認証をスキップしてAdminとして動作する。
    戻り値: ログインユーザー辞書、未ログインの場合は None
    """
    dev_mode = os.getenv("DEV_MODE", "false").lower() == "true"

    if dev_mode:
        st.session_state["current_user"] = DEV_USER
        return DEV_USER

    # Google OAuth (streamlit experimental_user)
    try:
        user_info = st.experimental_user
        if not user_info or not user_info.get("email"):
            return None

        email = user_info["email"]
        allowed_domain = os.getenv("ALLOWED_EMAIL_DOMAIN", "")

        # ドメインチェック
        if allowed_domain and not email.endswith(f"@{allowed_domain}"):
            st.error(f"許可されていないドメインです。@{allowed_domain} のアカウントでログインしてください。")
            st.stop()

        # user_master からロール照合
        user = db.get_user(email)
        if not user:
            st.warning(f"ユーザー '{email}' はシステムに登録されていません。管理者に連絡してください。")
            return None

        st.session_state["current_user"] = user
        return user

    except AttributeError:
        # experimental_user が利用不可の場合
        st.warning(
            "Google OAuth が設定されていません。"
            "DEV_MODE=true を設定するか、Streamlit Cloud の認証設定を行ってください。"
        )
        return None


def is_workflow_approver(db, request_id: str) -> bool:
    """現在のユーザーが指定リクエストの現ステップ承認者かどうかを確認する"""
    user = get_current_user()
    if not user:
        return False
    if user.get("role") == "Admin":
        return True

    tx = db.get_transaction(request_id)
    if not tx:
        return False

    workflow = db.get_workflow()
    if not workflow:
        return False

    # 現在のステップを特定
    status = tx.get("status", "")
    current_step = None
    for step in workflow:
        if step.get("step_name") == status:
            current_step = step
            break

    if not current_step:
        return False

    return current_step.get("approver_email") == user.get("email")
