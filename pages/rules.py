"""ルール管理 & 動的ワークフローデザイナー - Admin専用 (v1.4)"""
import time

import streamlit as st
import streamlit.components.v1 as components
from utils.auth import check_access

CONDITION_FIELDS   = ["contract_amount", "contract_type", "start_date", "end_date", "payment_terms", "company_name"]
CONDITION_OPERATORS = ["以上", "以下", "等しい", "含む"]
ACTIONS             = ["法務確認必須", "上長承認追加", "警告表示", "自動通知"]
TRIGGER_STATUSES    = ["承認待ち", "差し戻し", "完了", "作業中"]

ACTION_PRESETS = [
    {"label": "承認ステップを追加",       "value": "承認",           "color": "#198754", "icon": "✅"},
    {"label": "確認ステップを追加",       "value": "確認",           "color": "#0d6efd", "icon": "👁️"},
    {"label": "リーガルチェックを追加",    "value": "リーガルチェック","color": "#6f42c1", "icon": "⚖️"},
    {"label": "最終確認ステップを追加",   "value": "最終確認",        "color": "#fd7e14", "icon": "🔍"},
]
ACTION_COLORS = {p["value"]: p["color"] for p in ACTION_PRESETS}
ACTION_COLORS["完了"] = "#20c997"


def show(db):
    user = check_access(roles=("Admin",))
    st.title("📋 ルール管理")

    tab1, tab2, tab3 = st.tabs(["⚙️ ワークフローデザイナー", "📌 審査・チェックルール", "🔄 ワークフロールール"])
    with tab1:
        _render_workflow_designer(db, user)
    with tab2:
        _render_review_rules_tab(db, user)
    with tab3:
        _render_workflow_rules_tab(db, user)


# ═══════════════════════════════════════════════════════════
# ワークフローデザイナー
# ═══════════════════════════════════════════════════════════
def _render_workflow_designer(db, user):
    st.subheader("ワークフローデザイナー")

    # Editor / Admin ユーザーのみ担当者候補
    all_users      = db.get_all_users()
    approver_users = [u for u in all_users if u.get("role") in ("Editor", "Admin")]
    approver_opts  = ["（未設定）"] + [u["email"] for u in approver_users]
    approver_disp  = {u["email"]: f"{u['name']}  [{u['role']}]" for u in approver_users}

    workflow = db.get_workflow()
    if "wf_design_steps" not in st.session_state:
        st.session_state["wf_design_steps"] = [dict(s) for s in workflow]

    steps = st.session_state["wf_design_steps"]

    # ── 常時フロー図表示 ──
    st.markdown("#### 現在のフロー")
    render_mermaid(build_mermaid_diagram(steps), height=190)

    st.divider()

    # ── プリセットボタンでステップ追加 ──
    st.markdown("#### ステップを追加")
    btn_cols = st.columns(len(ACTION_PRESETS))
    for i, preset in enumerate(ACTION_PRESETS):
        with btn_cols[i]:
            if st.button(
                f"{preset['icon']} {preset['label']}",
                use_container_width=True,
                key=f"add_p_{preset['value']}_{i}",
            ):
                steps.append({
                    "step_order":    str(len(steps) + 1),
                    "step_name":     preset["value"],
                    "approver_email":"",
                    "action_type":   preset["value"],
                })
                st.session_state["wf_design_steps"] = steps
                st.rerun()

    st.divider()

    # ── ステップ編集 ──
    st.markdown("#### ステップ設定")
    if not steps:
        st.info("上のボタンからステップを追加してください。")
    else:
        for i, step in enumerate(steps):
            action = step.get("action_type", "")
            color  = ACTION_COLORS.get(action, "#6c757d")

            with st.container(border=True):
                hc1, hc2 = st.columns([1, 8])
                hc1.markdown(
                    f"<div style='font-size:24px;font-weight:700;color:#aaa;"
                    f"text-align:center;padding-top:6px;'>#{i+1}</div>",
                    unsafe_allow_html=True,
                )
                hc2.markdown(
                    f"<span style='background:{color};color:#fff;padding:4px 14px;"
                    f"border-radius:20px;font-size:13px;font-weight:600;'>{action}</span>",
                    unsafe_allow_html=True,
                )

                ec1, ec2, ec3, ec4 = st.columns([3, 4, 1, 1])

                # ステップ名セレクトボックス
                name_opts = [p["value"] for p in ACTION_PRESETS]
                cur_name  = step.get("step_name", action)
                if cur_name not in name_opts:
                    name_opts.insert(0, cur_name)
                step["step_name"] = ec1.selectbox(
                    "ステップ名",
                    options=name_opts,
                    index=name_opts.index(cur_name) if cur_name in name_opts else 0,
                    key=f"wfd_n_{i}",
                )

                # 担当者セレクトボックス（Editor/Adminのみ）
                cur_email = step.get("approver_email", "")
                email_idx = approver_opts.index(cur_email) if cur_email in approver_opts else 0
                sel_email = ec2.selectbox(
                    "担当者（Editor/Admin）",
                    options=approver_opts,
                    index=email_idx,
                    key=f"wfd_e_{i}",
                    format_func=lambda e: approver_disp.get(e, e) if e != "（未設定）" else "（未設定）",
                )
                step["approver_email"] = "" if sel_email == "（未設定）" else sel_email

                if i > 0 and ec3.button("↑", key=f"wfd_up_{i}", use_container_width=True):
                    steps[i - 1], steps[i] = steps[i], steps[i - 1]
                    _renumber(steps)
                    st.session_state["wf_design_steps"] = steps
                    st.rerun()

                if ec4.button("🗑️", key=f"wfd_d_{i}", use_container_width=True):
                    steps.pop(i)
                    _renumber(steps)
                    st.session_state["wf_design_steps"] = steps
                    st.rerun()

    st.divider()

    save_col, reset_col = st.columns(2)
    if save_col.button("💾 ワークフローを保存", type="primary", use_container_width=True):
        try:
            _renumber(steps)
            db.save_workflow(steps)
            # st.toast で2秒後自動消去（Streamlit が自動管理）
            st.toast("✅ 保存完了！ワークフローを更新しました", icon="✅")
            st.session_state.pop("wf_design_steps", None)
            time.sleep(0.5)  # Toast が表示されてから rerun
            st.rerun()
        except Exception as e:
            st.toast(f"❌ 保存エラー: {e}", icon="❌")

    if reset_col.button("↩️ 変更をリセット", use_container_width=True):
        st.session_state.pop("wf_design_steps", None)
        st.rerun()


def _renumber(steps):
    for i, s in enumerate(steps):
        s["step_order"] = str(i + 1)


# ═══════════════════════════════════════════════════════════
# Mermaid ユーティリティ
# ═══════════════════════════════════════════════════════════
def build_mermaid_diagram(steps: list) -> str:
    if not steps:
        return "graph LR\n    A[ステップ未設定]"

    lines = ["graph LR"]
    nodes = [("NODE_START", "開始", "#6c757d")]

    for step in sorted(steps, key=lambda x: int(x.get("step_order", 0))):
        nid     = f"S{step.get('step_order', len(nodes))}"
        action  = step.get("action_type", "")
        name    = step.get("step_name", action)
        email   = step.get("approver_email", "")
        short   = email.split("@")[0] if email else ""
        label   = f"{name}\\n({short})" if short else name
        color   = ACTION_COLORS.get(action, "#6c757d")
        nodes.append((nid, label, color))

    nodes.append(("NODE_END", "完了", "#198754"))

    for nid, label, _ in nodes:
        lines.append(f'    {nid}["{label.replace(chr(34), chr(39))}"]')
    for i in range(len(nodes) - 1):
        lines.append(f"    {nodes[i][0]} --> {nodes[i+1][0]}")
    for nid, _, color in nodes:
        lines.append(f"    style {nid} fill:{color},color:#fff,stroke:none")

    return "\n".join(lines)


def render_mermaid(diagram: str, height: int = 220):
    html = f"""<!DOCTYPE html><html>
<head>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>body{{margin:0;padding:4px;background:transparent;}}
.mermaid{{display:flex;justify-content:center;}}</style>
</head>
<body>
<div class="mermaid">
{diagram}
</div>
<script>
mermaid.initialize({{startOnLoad:true,theme:'base',
  themeVariables:{{fontSize:'14px',fontFamily:'sans-serif'}},
  flowchart:{{curve:'linear',padding:10}}}});
</script>
</body></html>"""
    components.html(html, height=height, scrolling=False)


# ═══════════════════════════════════════════════════════════
# 審査・チェックルール タブ
# ═══════════════════════════════════════════════════════════
def _render_review_rules_tab(db, user):
    st.subheader("審査・チェックルール")
    for r in db.get_all_review_rules():
        _render_review_rule(db, r)
    if not db.get_all_review_rules():
        st.info("ルールが登録されていません。")
    st.divider()
    with st.expander("＋ 新規ルール追加"):
        with st.form("add_rv"):
            rule_name    = st.text_input("ルール名")
            cond_field   = st.selectbox("条件フィールド", CONDITION_FIELDS)
            cond_op      = st.selectbox("条件演算子", CONDITION_OPERATORS)
            cond_val     = st.text_input("条件値")
            action       = st.selectbox("アクション", ACTIONS)
            action_target= st.text_input("アクション対象")
            description  = st.text_area("説明")
            if st.form_submit_button("追加", type="primary"):
                if rule_name and cond_val:
                    db.add_review_rule({"rule_name": rule_name, "condition_field": cond_field,
                                        "condition_operator": cond_op, "condition_value": cond_val,
                                        "action": action, "action_target": action_target,
                                        "description": description, "created_by": user["email"]})
                    st.success("追加しました。")
                    st.rerun()
                else:
                    st.warning("ルール名と条件値を入力してください。")


def _render_review_rule(db, r):
    is_active = str(r.get("is_active", "true")).lower() == "true"
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([4, 2, 1, 1])
        c1.markdown(f"**{r.get('rule_name','')}**")
        c1.caption(f"{r.get('condition_field','')} {r.get('condition_operator','')} {r.get('condition_value','')} → **{r.get('action','')}**")
        if r.get("description"):
            c1.caption(r["description"])
        new_act = c2.toggle("有効", value=is_active, key=f"rv_a_{r['rule_id']}")
        if new_act != is_active:
            db.update_review_rule(r["rule_id"], {"is_active": str(new_act).lower()})
            st.rerun()
        if c3.button("編集", key=f"rv_e_{r['rule_id']}"):
            st.session_state[f"erv_{r['rule_id']}"] = True
        if c4.button("削除", key=f"rv_d_{r['rule_id']}"):
            db.deactivate_review_rule(r["rule_id"])
            st.rerun()
        if st.session_state.get(f"erv_{r['rule_id']}"):
            with st.form(f"frv_{r['rule_id']}"):
                n = st.text_input("ルール名", value=r.get("rule_name",""))
                a = st.selectbox("アクション", ACTIONS, index=_idx(ACTIONS, r.get("action","")))
                t = st.text_input("対象", value=r.get("action_target",""))
                d = st.text_area("説明", value=r.get("description",""))
                if st.form_submit_button("更新"):
                    db.update_review_rule(r["rule_id"], {"rule_name":n,"action":a,"action_target":t,"description":d})
                    st.session_state.pop(f"erv_{r['rule_id']}", None)
                    st.rerun()


# ═══════════════════════════════════════════════════════════
# ワークフロールール タブ
# ═══════════════════════════════════════════════════════════
def _render_workflow_rules_tab(db, user):
    st.subheader("ワークフロールール")
    for r in db.get_all_workflow_rules():
        _render_workflow_rule(db, r)
    if not db.get_all_workflow_rules():
        st.info("ルールが登録されていません。")
    st.divider()
    with st.expander("＋ 新規ワークフロールール追加"):
        with st.form("add_wfr"):
            wf_name  = st.text_input("ルール名")
            trigger  = st.selectbox("トリガーステータス", TRIGGER_STATUSES)
            cond     = st.text_input("条件")
            nxt      = st.text_input("次ステップ上書き")
            notif    = st.text_input("通知先メール（カンマ区切り）")
            desc     = st.text_area("説明")
            if st.form_submit_button("追加", type="primary"):
                if wf_name:
                    db.add_workflow_rule({"rule_name":wf_name,"trigger_status":trigger,"condition":cond,
                                          "next_step_override":nxt,"notification_emails":notif,
                                          "description":desc,"created_by":user["email"]})
                    st.success("追加しました。")
                    st.rerun()


def _render_workflow_rule(db, r):
    is_active = str(r.get("is_active","true")).lower() == "true"
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([4, 2, 1, 1])
        c1.markdown(f"**{r.get('rule_name','')}**")
        c1.caption(f"トリガー: **{r.get('trigger_status','')}** | 条件: {r.get('condition','')}")
        if r.get("notification_emails"):
            c1.caption(f"通知先: {r.get('notification_emails','')}")
        new_act = c2.toggle("有効", value=is_active, key=f"wf_a_{r['rule_id']}")
        if new_act != is_active:
            db.update_workflow_rule(r["rule_id"], {"is_active": str(new_act).lower()})
            st.rerun()
        if c3.button("編集", key=f"wf_e_{r['rule_id']}"):
            st.session_state[f"ewf_{r['rule_id']}"] = True
        if c4.button("削除", key=f"wf_d_{r['rule_id']}"):
            db.deactivate_workflow_rule(r["rule_id"])
            st.rerun()
        if st.session_state.get(f"ewf_{r['rule_id']}"):
            with st.form(f"fwf_{r['rule_id']}"):
                n  = st.text_input("ルール名", value=r.get("rule_name",""))
                c  = st.text_input("条件", value=r.get("condition",""))
                nx = st.text_input("次ステップ", value=r.get("next_step_override",""))
                nt = st.text_input("通知先", value=r.get("notification_emails",""))
                d  = st.text_area("説明", value=r.get("description",""))
                if st.form_submit_button("更新"):
                    db.update_workflow_rule(r["rule_id"],{"rule_name":n,"condition":c,"next_step_override":nx,"notification_emails":nt,"description":d})
                    st.session_state.pop(f"ewf_{r['rule_id']}", None)
                    st.rerun()


def _idx(lst, val):
    try:
        return lst.index(val)
    except ValueError:
        return 0
