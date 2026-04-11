"""ひな形管理画面 - Admin専用 (v1.4) - 閲覧アコーディオン・フォームリセット追加"""
import os
import tempfile

import streamlit as st
from utils.auth import check_access
from services.drive_uploader import DriveUploader
from services.word_generator import WordGenerator

CONTRACT_TYPES = ["業務委託", "売買", "NDA", "その他"]

_DEFAULT_TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "templates", "contract_template.docx")
_FALLBACK_TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "assets", "templates", "default.docx")


def show(db):
    user = check_access(roles=("Admin",))
    st.title("📁 ひな形管理")

    # ─── 登録済みひな形一覧 ───
    st.subheader("登録済みひな形")
    templates = db.get_all_templates()

    if templates:
        for tmpl in templates:
            _render_template_row(db, tmpl)
    else:
        st.info("ひな形が登録されていません。")

    st.divider()

    # ─── 新規アップロード ───
    with st.expander("＋ 新規ひな形アップロード"):
        # フォームリセット用キー（アップロード成功後にインクリメント）
        form_key = st.session_state.get("upload_form_key", 0)

        with st.form(f"upload_form_{form_key}"):
            tmpl_name     = st.text_input("ひな形名")
            contract_type = st.selectbox("契約種別", CONTRACT_TYPES)
            version       = st.text_input("バージョン", value="v1.0")
            description   = st.text_area("説明")
            uploaded_file = st.file_uploader(
                "Word ファイル (.docx)", type=["docx"], accept_multiple_files=False
            )

            if st.form_submit_button("📤 アップロード", type="primary"):
                if not tmpl_name:
                    st.warning("ひな形名を入力してください。")
                elif not uploaded_file:
                    st.warning(".docx ファイルを選択してください。")
                else:
                    success = _handle_upload(db, user, tmpl_name, contract_type, version, description, uploaded_file)
                    if success:
                        # フォームをリセット: キーをインクリメントして再レンダリング
                        st.session_state["upload_form_key"] = form_key + 1
                        st.rerun()


def _render_template_row(db, tmpl: dict):
    is_active = str(tmpl.get("is_active", "true")).lower() == "true"
    tmpl_id   = tmpl["template_id"]

    with st.container(border=True):
        c1, c2, c3, c4, c5, c6 = st.columns([3, 2, 1, 1, 1, 1])

        c1.markdown(f"**{tmpl.get('template_name','')}**")
        c1.caption(
            f"種別: {tmpl.get('contract_type','')} | "
            f"ver: {tmpl.get('version','')} | "
            f"登録: {(tmpl.get('uploaded_at') or '')[:10]}"
        )
        if tmpl.get("description"):
            c1.caption(tmpl["description"])

        new_active = c2.toggle("有効", value=is_active, key=f"ta_{tmpl_id}")
        if new_active != is_active:
            db.update_template(tmpl_id, {"is_active": str(new_active).lower()})
            st.rerun()

        # 閲覧ボタン
        if c3.button("👁️ 閲覧", key=f"tv_{tmpl_id}", use_container_width=True):
            key = f"view_{tmpl_id}"
            st.session_state[key] = not st.session_state.get(key, False)

        drive_url = tmpl.get("drive_url", "")
        if drive_url and "mock" not in drive_url.lower():
            c4.link_button("DL", drive_url, use_container_width=True)
        else:
            c4.caption("(Mock)")

        if c5.button("削除", key=f"td_{tmpl_id}", use_container_width=True):
            st.session_state[f"confirm_{tmpl_id}"] = True

        # 削除確認
        if st.session_state.get(f"confirm_{tmpl_id}"):
            st.warning(f"「{tmpl.get('template_name')}」を削除しますか？（論理削除）")
            yes_col, no_col = st.columns(2)
            if yes_col.button("削除する", key=f"yes_{tmpl_id}"):
                db.deactivate_template(tmpl_id)
                st.session_state.pop(f"confirm_{tmpl_id}", None)
                st.toast(f"「{tmpl.get('template_name')}」を削除しました", icon="🗑️")
                st.rerun()
            if no_col.button("キャンセル", key=f"no_{tmpl_id}"):
                st.session_state.pop(f"confirm_{tmpl_id}", None)
                st.rerun()

        # アコーディオン形式の閲覧パネル
        if st.session_state.get(f"view_{tmpl_id}"):
            _render_template_viewer(tmpl)


def _render_template_viewer(tmpl: dict):
    """登録されたひな形の中身をアコーディオン形式で表示"""
    tmpl_id   = tmpl["template_id"]
    drive_url = tmpl.get("drive_url", "")
    is_mock   = os.getenv("DEV_MODE", "false").lower() == "true"

    with st.expander(f"📄 ひな形の内容: {tmpl.get('template_name','')}", expanded=True):
        # テンプレートパスの解決
        local_path = None
        if is_mock or "mock" in drive_url.lower():
            for p in [_DEFAULT_TEMPLATE, _FALLBACK_TEMPLATE]:
                if os.path.exists(p):
                    local_path = p
                    break
            if local_path:
                st.caption("（Mockモード: ローカルテンプレートを表示しています）")
        else:
            if drive_url:
                try:
                    uploader = DriveUploader()
                    file_id = uploader.extract_file_id(drive_url)
                    if file_id:
                        local_path = os.path.join(tempfile.gettempdir(), f"view_{file_id}.docx")
                        if not os.path.exists(local_path):
                            uploader.download_to_path(file_id, local_path)
                except Exception as e:
                    st.warning(f"Driveからのダウンロード失敗: {e}")
                    for p in [_DEFAULT_TEMPLATE, _FALLBACK_TEMPLATE]:
                        if os.path.exists(p):
                            local_path = p
                            break

        if not local_path:
            st.error("テンプレートファイルが見つかりません。")
            return

        # 変数一覧
        variables = WordGenerator.extract_variables(local_path)
        st.markdown("**含まれる変数（{{...}} タグ）**")
        if variables:
            var_cols = st.columns(min(len(variables), 4))
            for i, var in enumerate(variables):
                label_info = WordGenerator.get_field_info(var)
                var_cols[i % 4].markdown(
                    f"<div style='background:#e8f0fe;border-radius:6px;padding:6px 10px;"
                    f"margin:2px;font-size:13px;'>"
                    f"<code>{{{{{var}}}}}</code><br>"
                    f"<span style='color:#555;font-size:11px;'>{label_info[0]}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.warning("変数が見つかりませんでした。テンプレートに `{{変数名}}` 形式で記述してください。")

        # テキスト内容プレビュー
        st.markdown("**テキスト内容（プレビュー）**")
        try:
            from docx import Document
            doc = Document(local_path)
            preview_lines = []
            for para in doc.paragraphs:
                if para.text.strip():
                    preview_lines.append(para.text)
            if preview_lines:
                st.text_area(
                    "本文",
                    value="\n".join(preview_lines[:30]),  # 最大30行
                    height=200,
                    disabled=True,
                    label_visibility="collapsed",
                )
            else:
                st.caption("テキスト内容が見つかりませんでした。")
        except Exception as e:
            st.error(f"プレビュー生成エラー: {e}")

        if st.button("閉じる", key=f"close_view_{tmpl_id}"):
            st.session_state.pop(f"view_{tmpl_id}", None)
            st.rerun()


def _handle_upload(db, user, tmpl_name, contract_type, version, description, uploaded_file) -> bool:
    with st.spinner("Google Drive にアップロード中..."):
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                tmp.write(uploaded_file.read())
                tmp_path = tmp.name

            # 変数チェック（アップロード前バリデーション）
            variables = WordGenerator.extract_variables(tmp_path)
            if not variables:
                st.warning(
                    "このファイルに `{{変数名}}` 形式の変数が見つかりませんでした。"
                    "正しいテンプレート形式か確認してください。アップロードは続行します。"
                )

            uploader  = DriveUploader()
            drive_url = uploader.upload(tmp_path, "契約書ひな形")

            db.add_template({
                "template_name": tmpl_name,
                "contract_type": contract_type,
                "drive_url":     drive_url,
                "version":       version,
                "description":   description,
                "uploaded_by":   user["email"],
            })

            os.unlink(tmp_path)

            st.toast(f"「{tmpl_name}」をアップロードしました", icon="✅")
            if variables:
                st.success(f"変数 {len(variables)} 個を検出: `{'`, `'.join(variables)}`")
            return True

        except Exception as e:
            st.error(f"アップロードエラー: {e}")
            return False
