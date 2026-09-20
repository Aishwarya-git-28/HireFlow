"""app.py: HireFlow dashboard.  Run with:  streamlit run app.py

Layout of a run: theme -> state -> sidebar -> top bar -> navigation -> one page.
Nothing here calls a model directly; pages talk to the backend through ui.views.Backend.
"""
import signal
import threading

import streamlit as st

# Streamlit runs this script in a worker thread, and signal handlers can only be set from the main thread.
# Some libraries (CrewAI's shutdown hooks among them) try anyway, so make that attempt harmless.
if threading.current_thread() is not threading.main_thread() and not getattr(signal.signal, "_hireflow_safe", False):
    _orig_signal = signal.signal

    def _thread_safe_signal(signum, handler):
        try:
            return _orig_signal(signum, handler)
        except ValueError:
            return None

    _thread_safe_signal._hireflow_safe = True
    signal.signal = _thread_safe_signal

st.set_page_config(page_title="HireFlow", page_icon="🖍️", layout="wide", initial_sidebar_state="expanded")

from models import Workspace  # noqa: E402
from ui import components as C  # noqa: E402
from ui import theme, views  # noqa: E402

theme.inject()

ss = st.session_state
ss.setdefault("ws", Workspace())
ss.setdefault("mode", "live")
ss.setdefault("nav", "Setup")
if "goto" in ss:  # set by code that runs after the navigation widget was drawn (for example, after a screening run)
    ss["nav"] = ss.pop("goto")
if "flash" in ss:
    st.toast(ss.pop("flash"))

backend = views.detect_backend()
workspace = ss["ws"]

views.render_sidebar(workspace, backend)
st.markdown(C.topbar(views.topbar_chips(backend, ss["mode"])), unsafe_allow_html=True)
page = views.nav(views.PAGES)
views.render(page, workspace, backend)
