import streamlit as st
from streamlit_autorefresh import st_autorefresh
import time
import sqlite3
import pandas as pd
import base64
import os

try:
    import plotly.express as px
    import plotly.graph_objects as go
    has_plotly = True
except ImportError:
    has_plotly = False

# Dummy imports to prevent crash if not implemented yet
try:
    from stuckpoint.store.db import Store
except ImportError:
    class Store:
        def __init__(self, db_path="stuckpoint.db"): pass
        def pending_signals(self): return []
        def update_signal_status(self, sid, status): pass
        def hints_for(self, sid): return []
        def mark_solved(self, pk, solved): pass
        def save_hint(self, h): pass
        
try:
    from stuckpoint.models import HintRequest
except ImportError:
    class HintRequest:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)

try:
    from stuckpoint.llm.hints import next_hint, project_help
except ImportError:
    def next_hint(req): 
        class Resp:
            text = "Dummy hint"
            level = req.level
            is_code = False
            blocked = False
            block_reason = None
        return Resp()
    def project_help(req):
        class Resp:
            text = "Dummy code solution"
            level = req.level
            is_code = True
            blocked = False
            block_reason = None
        return Resp()

try:
    from stuckpoint.report.build import build_report
except ImportError:
    def build_report():
        return {
            "metrics": {"overall": {"problems": 0, "total_active_min": 0, "stuck_episodes": 0, "hints_used": 0}, "topics": {}},
            "sessions": [],
            "claims": [],
            "gate_summary": {"passed": 0, "downgraded": 0, "rejected": 0}
        }

st.set_page_config(page_title="StuckPoint", page_icon="⚓", layout="wide")

# Theme state
if "theme" not in st.session_state:
    st.session_state.theme = "light"

# Load CSS
css_path = os.path.join(os.path.dirname(__file__), "styles.css")
if os.path.exists(css_path):
    with open(css_path) as f:
        css = f.read()
else:
    css = ""
st.markdown(f'<style>{css}</style>', unsafe_allow_html=True)
if st.session_state.theme == "dark":
    st.markdown('<script>document.documentElement.setAttribute("data-theme", "dark");</script>', unsafe_allow_html=True)

# SVG Icons (Lucide)
ICONS = {
    "compass": '<svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"></polygon></svg>',
    "bar-chart": '<svg class="icon" viewBox="0 0 24 24"><line x1="12" y1="20" x2="12" y2="10"></line><line x1="18" y1="20" x2="18" y2="4"></line><line x1="6" y1="20" x2="6" y2="16"></line></svg>',
    "history": '<svg class="icon" viewBox="0 0 24 24"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path><polyline points="3 3 3 8 8 8"></polyline><polyline points="12 7 12 12 15 15"></polyline></svg>',
    "check": '<svg class="icon" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg>',
    "alert": '<svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>',
    "clock": '<svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>',
    "refresh": '<svg class="icon" viewBox="0 0 24 24"><path d="M21 2v6h-6"></path><path d="M3 12a9 9 0 0 1 15-6.7L21 8"></path><path d="M3 22v-6h6"></path><path d="M21 12a9 9 0 0 1-15 6.7L3 16"></path></svg>',
    "download": '<svg class="icon" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>',
    "moon": '<svg class="icon" viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>',
    "sun": '<svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>',
    "anchor": '<svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="5" r="3"></circle><line x1="12" y1="22" x2="12" y2="8"></line><path d="M5 12H2a10 10 0 0 0 20 0h-3"></path></svg>'
}

# Hero Header
st.markdown(f"""
<div class="hero-header animate-in">
    {ICONS['anchor']} <h1>StuckPoint</h1>
    <p>Navigate your learning currents</p>
    <div class="hero-wave"></div>
</div>
""", unsafe_allow_html=True)

# Sidebar - Ship Shell
with st.sidebar:
    st.markdown(f"<h3 style='display:flex;align-items:center;'>{ICONS['compass']} Dashboard</h3>", unsafe_allow_html=True)
    st.caption("Welcome aboard")
    
    st.write("---")
    solved_count = st.session_state.get("solved_count", 0)
    progress_val = min(solved_count * 10, 100)
    st.markdown("**Depth Meter**")
    st.progress(progress_val)
    st.caption(f"{solved_count} problems solved")
    
    st.write("---")
    st.markdown("**SETTINGS**")
    theme_btn_label = "Switch to Day Sea" if st.session_state.theme == "dark" else "Switch to Deep Sea"
    icon = ICONS['sun'] if st.session_state.theme == "dark" else ICONS['moon']
    if st.button(f"Toggle Theme", key="theme_toggle"):
        st.session_state.theme = "dark" if st.session_state.theme == "light" else "light"
        st.rerun()

st_autorefresh(interval=5000, key="data_refresh")
store = Store("stuckpoint.db")

def get_mode_badge(mode):
    if mode == "practice": return f"<span class='status-badge status-verified'>Practice</span>"
    if mode == "project": return f"<span class='status-badge status-neutral'>Project</span>"
    return f"<span class='status-badge status-low'>Exam/Other</span>"

tab1, tab2, tab3 = st.tabs(["Assistant", "Skills Report", "History"])

with tab1:
    signals = store.pending_signals()
    signals = [s for s in signals if getattr(s, "status", "pending") in ["confirmed", "offered"]]
    
    if not signals:
        st.markdown(f"""
        <div class="animate-in" style="text-align: center; padding: 48px 0; max-width: 400px; margin: auto;">
            <div style="color: var(--color-primary); opacity: 0.5; margin-bottom: 16px;">
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z"/>
                    <path d="M8 14C8 14 9.5 16 12 16C14.5 16 16 14 16 14"/>
                    <path d="M9 9H9.01"/>
                    <path d="M15 9H15.01"/>
                </svg>
            </div>
            <h3 style="color: var(--color-navy); margin-bottom: 8px;">Calm waters</h3>
            <p style="color: var(--color-text-light); font-size: 14px;">No stuck episodes detected. You are sailing smoothly.</p>
        </div>
        """, unsafe_allow_html=True)
    
    for sig in signals:
        state_key = f"sig_state_{getattr(sig, 'id', id(sig))}"
        if state_key not in st.session_state:
            st.session_state[state_key] = {"show_hint": False, "hints": [], "user_context": ""}
            
        problem_title = getattr(sig, 'problem_title', 'Unknown Problem')
        mode_html = get_mode_badge(getattr(sig, "mode", "practice"))
        mins = getattr(sig, 'minutes_on_problem', 0)
        
        st.markdown(f"""
        <div class="animate-in" style="background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: var(--spacing-4); margin-bottom: var(--spacing-4); display: flex; align-items: center; justify-content: space-between;">
            <div>
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                    <h3 style="margin:0; font-size: 16px;">{problem_title}</h3>
                    {mode_html}
                </div>
                <div style="font-size: 13px; color: var(--color-text-light); display: flex; align-items: center; gap: 12px;">
                    <span>{ICONS['clock']} {mins:.1f} min elapsed</span>
                    <span>{ICONS['refresh']} {getattr(sig, 'loops', 0)} loops</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if not st.session_state[state_key]["show_hint"]:
            c1, c2, c3 = st.columns([1,1,2])
            with c1:
                if st.button("I'm stuck", key=f"hint_{getattr(sig, 'id', id(sig))}"):
                    store.update_signal_status(getattr(sig, 'id', id(sig)), "accepted")
                    st.session_state[state_key]["show_hint"] = True
                    st.rerun()
            with c2:
                st.markdown('<div class="secondary-btn">', unsafe_allow_html=True)
                if st.button("Not now", key=f"snooze_{getattr(sig, 'id', id(sig))}"):
                    store.update_signal_status(getattr(sig, 'id', id(sig)), "snoozed")
                    st.toast("Snoozed for 15 minutes.")
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
            with c3:
                st.markdown('<div class="secondary-btn">', unsafe_allow_html=True)
                if st.button("Dismiss", key=f"fine_{getattr(sig, 'id', id(sig))}"):
                    store.update_signal_status(getattr(sig, 'id', id(sig)), "dismissed")
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            mode = getattr(sig, "mode", "practice")
            hints = st.session_state[state_key]["hints"]
            
            # Chat UI
            st.markdown('<div class="chat-bubble user animate-in">I need some help.</div>', unsafe_allow_html=True)
            for h in hints:
                st.markdown(f'<div class="chat-bubble assistant animate-in"><b>Level {h.level}:</b><br/>{h.text}</div>', unsafe_allow_html=True)
                if getattr(h, "is_code", False):
                    st.code(h.text)
                    
            level = len(hints) + 1
            
            if level == 1:
                with st.spinner("Analyzing..."):
                    req = HintRequest(
                        signal_id=getattr(sig, 'id', ''), problem_key=getattr(sig, 'problem_key', ''),
                        problem_title=problem_title, mode=mode, level=level,
                        user_context=st.session_state[state_key]["user_context"],
                        previous_hints=[h.text for h in hints]
                    )
                    h_resp = next_hint(req)
                    st.session_state[state_key]["hints"].append(h_resp)
                    store.save_hint(h_resp)
                st.rerun()
            
            # Action Buttons
            st.write("")
            if mode == "practice":
                ac1, ac2 = st.columns(2)
                with ac1:
                    if level <= 3:
                        btn_label = "Hint" if level == 2 else "Explain simply"
                        if st.button(btn_label, key=f"nexth_{getattr(sig, 'id', id(sig))}"):
                            with st.spinner("Generating..."):
                                req = HintRequest(
                                    signal_id=getattr(sig, 'id', ''), problem_key=getattr(sig, 'problem_key', ''),
                                    problem_title=problem_title, mode=mode, level=level, user_context=None,
                                    previous_hints=[h.text for h in hints]
                                )
                                h_resp = next_hint(req)
                                st.session_state[state_key]["hints"].append(h_resp)
                                store.save_hint(h_resp)
                            st.rerun()
                with ac2:
                    st.markdown('<div class="secondary-btn">', unsafe_allow_html=True)
                    if st.button("Mark solved", key=f"solved_{getattr(sig, 'id', id(sig))}"):
                        store.mark_solved(getattr(sig, 'problem_key', ''), True)
                        store.update_signal_status(getattr(sig, 'id', id(sig)), "dismissed")
                        st.session_state["solved_count"] = st.session_state.get("solved_count", 0) + 1
                        st.balloons()
                        st.toast("Marked as solved!", icon="✅")
                        time.sleep(1.5)
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
            elif mode == "project":
                user_ctx = st.text_area("Paste your code or error (optional)", key=f"ctx_{getattr(sig, 'id', id(sig))}")
                st.session_state[state_key]["user_context"] = user_ctx
                
                # Chips
                col_chip1, col_chip2 = st.columns(2)
                if col_chip1.button("Why is this error happening?", key=f"q1_{getattr(sig, 'id', id(sig))}"):
                    st.toast("Querying model...", icon="⏳")
                if col_chip2.button("How do I fix this?", key=f"q2_{getattr(sig, 'id', id(sig))}"):
                    st.toast("Querying model...", icon="⏳")
                    
                pc1, pc2, pc3 = st.columns(3)
                with pc1:
                    if level <= 3:
                        if st.button("Hint", key=f"phint_{getattr(sig, 'id', id(sig))}"):
                            with st.spinner("Generating..."):
                                req = HintRequest(
                                    signal_id=getattr(sig, 'id', ''), problem_key=getattr(sig, 'problem_key', ''),
                                    problem_title=problem_title, mode=mode, level=level, user_context=user_ctx,
                                    previous_hints=[h.text for h in hints]
                                )
                                h_resp = project_help(req)
                                st.session_state[state_key]["hints"].append(h_resp)
                                store.save_hint(h_resp)
                            st.rerun()
                with pc2:
                    if st.button("Show example", key=f"full_{getattr(sig, 'id', id(sig))}"):
                        with st.spinner("Generating code..."):
                            req = HintRequest(
                                signal_id=getattr(sig, 'id', ''), problem_key=getattr(sig, 'problem_key', ''),
                                problem_title=problem_title, mode=mode, level=4, user_context=user_ctx,
                                previous_hints=[h.text for h in hints]
                            )
                            h_resp = project_help(req)
                            st.session_state[state_key]["hints"].append(h_resp)
                            store.save_hint(h_resp)
                        st.rerun()
                with pc3:
                    st.markdown('<div class="secondary-btn">', unsafe_allow_html=True)
                    if st.button("Mark solved", key=f"psolved_{getattr(sig, 'id', id(sig))}"):
                        store.mark_solved(getattr(sig, 'problem_key', ''), True)
                        store.update_signal_status(getattr(sig, 'id', id(sig)), "dismissed")
                        st.session_state["solved_count"] = st.session_state.get("solved_count", 0) + 1
                        st.balloons()
                        st.toast("Marked as solved!", icon="✅")
                        time.sleep(1.5)
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)

with tab2:
    st.write("")
    rc1, rc2 = st.columns([5, 1])
    with rc2:
        if st.button("Refresh", icon="🔄", use_container_width=True):
            with st.spinner("Recomputing..."):
                st.session_state["report_data"] = build_report()
            st.toast("Report updated", icon="✅")
            st.rerun()
            
    report = st.session_state.get("report_data", None)
    if report:
        overall = report.get("metrics", {}).get("overall", {})
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("Attempted", overall.get("problems", 0))
        mc2.metric("Active Min", f'{overall.get("total_active_min", 0):.1f}')
        mc3.metric("Episodes", overall.get("stuck_episodes", 0))
        mc4.metric("Hints", overall.get("hints_used", 0))
        
        gate = report.get("gate_summary", {})
        total_claims = len(report.get("claims", []))
        
        st.markdown(f"""
        <div style="margin: 24px 0 16px 0; font-size: 14px; color: var(--color-text-light);">
            <b>Gate summary:</b> 
            <span class="status-badge status-neutral">{total_claims} claims</span>
            <span class="status-badge status-verified">{gate.get('passed',0)} verified</span>
            <span class="status-badge status-low">{gate.get('downgraded',0)} low-confidence</span>
            <span class="status-badge status-rejected">{gate.get('rejected',0)} rejected</span>
        </div>
        """, unsafe_allow_html=True)
        
        claims = report.get("claims", [])
        for c in claims:
            status = getattr(c, "gate_status", "unchecked")
            if status == "passed": badge_cls = "status-verified"
            elif status == "downgraded": badge_cls = "status-low"
            else: badge_cls = "status-rejected"
            
            kind = getattr(c, "kind", "recommendation").capitalize()
            text = getattr(c, "text", "")
            
            with st.container():
                st.markdown(f"#### <span class='status-badge {badge_cls}'>{kind}</span>", unsafe_allow_html=True)
                if status == "rejected":
                    st.markdown(f"<del style='color: var(--color-text-light);'>{text}</del>", unsafe_allow_html=True)
                    st.error(f"{getattr(c, 'gate_reason', 'Unknown reason')}")
                elif status == "downgraded":
                    st.write(text)
                    st.warning(f"{getattr(c, 'gate_reason', 'Unknown reason')}")
                else:
                    st.write(text)
                    
                with st.expander("Evidence"):
                    st.write("**Problems:**", ", ".join(getattr(c, "about_problems", [])))
                    st.write("**Metrics:**", getattr(c, "recomputed", {}))
                st.write("---")
                
        topics = report.get("metrics", {}).get("topics", {})
        if topics and has_plotly:
            st.subheader("Topic Activity")
            df = pd.DataFrame([{"Topic": t, "Minutes": md.get("avg_active_min", 0)} for t, md in topics.items()])
            fig = px.bar(df, x="Topic", y="Minutes", 
                         color_discrete_sequence=["#13609A"],
                         template="plotly_white")
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              margin=dict(l=0,r=0,t=20,b=0))
            st.plotly_chart(fig, use_container_width=True)
        elif topics:
            st.subheader("Topic Activity")
            df = pd.DataFrame([{"Topic": t, "Minutes": md.get("avg_active_min", 0)} for t, md in topics.items()])
            st.bar_chart(df, x="Topic", y="Minutes", color="#13609A")
            
        csv = "Topic,Minutes\n" + "\n".join([f"{t},{md.get('avg_active_min',0)}" for t, md in topics.items()])
        st.download_button("Export CSV", data=csv, file_name="report.csv", mime="text/csv")
            
    else:
        st.markdown("""
        <div class="animate-in" style="text-align: center; padding: 48px; border: 1px dashed var(--color-border); border-radius: 12px; margin-top: 16px;">
            <p style="color: var(--color-text-light);">No data yet. Click Refresh to scan.</p>
        </div>
        """, unsafe_allow_html=True)

with tab3:
    st.markdown("<p style='color: var(--color-text-light);'>History empty.</p>", unsafe_allow_html=True)
