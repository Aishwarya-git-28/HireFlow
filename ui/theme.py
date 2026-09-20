"""ui/theme.py: the HireFlow look.

Design idea: an analyst's evidence desk. Cool paper, ink, one teal for structure, and a highlighter yellow that
is used for exactly one job: marking the words that a rating rests on. Evidence text is set in a serif (the
"document" voice); everything the interface says is set in a grotesque sans.
"""
import streamlit as st

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&family=Schibsted+Grotesk:wght@400;500;600;700&display=swap');

:root{
  --fog:#F2F5F7; --grid:#E8EDF0; --paper:#FFFFFF; --ink:#1D2A33; --body:#3A4852; --muted:#63717C;
  --line:#DCE2E7; --line2:#EBEFF2;
  --lagoon:#0F5C63; --lagoon2:#0A464C; --lagoon-soft:#DCEDEE;
  --marker:#FFE066; --marker-soft:#FFF5C2;
  --good:#2C8459; --good-soft:#E1F1E8; --warn:#A96A12; --warn-soft:#FBEFD6;
  --bad:#B93B51; --bad-soft:#F9E3E7; --slate:#6A7783; --slate-soft:#ECEFF2;
  --serif:'Newsreader',Georgia,'Times New Roman',serif;
  --sans:'Schibsted Grotesk','Segoe UI',system-ui,-apple-system,sans-serif;
}

/* ---------- page frame ---------- */
.stApp{
  background-color:var(--fog);
  background-image:linear-gradient(var(--grid) 1px,transparent 1px),linear-gradient(90deg,var(--grid) 1px,transparent 1px);
  background-size:32px 32px; background-position:-1px -1px; color:var(--ink);
}
.stApp,.stApp p,.stApp li,.stApp label,.stApp button,.stApp input,.stApp textarea,
.stApp [data-baseweb="select"] div,.stApp [data-testid="stMarkdownContainer"]{ font-family:var(--sans); }
.block-container{ max-width:1180px; padding:1.3rem 2rem 5rem; }
header[data-testid="stHeader"]{ background:transparent; }
#MainMenu,footer,.stDeployButton,[data-testid="stAppDeployButton"]{ display:none !important; }
[data-testid="stVerticalBlock"]{ gap:.85rem; }
h1,h2,h3{ font-family:var(--sans); letter-spacing:-.02em; }

/* ---------- sidebar ---------- */
section[data-testid="stSidebar"]{ background:var(--paper); border-right:1px solid var(--line); }
section[data-testid="stSidebar"] .block-container{ padding:1.4rem 1.2rem 2rem; }
.side-brand{ display:flex; align-items:center; gap:.65rem; font-weight:700; font-size:1.25rem; letter-spacing:-.02em; }
.side-note{ color:var(--muted); font-size:.86rem; line-height:1.45; margin:.5rem 0 0; }
.steps{ list-style:none; margin:.4rem 0 0; padding:0; }
.steps li{ display:grid; grid-template-columns:26px 1fr; gap:.65rem; padding:.5rem 0; }
.steps .n{ width:22px; height:22px; border-radius:50%; display:grid; place-items:center; font-size:.72rem; font-weight:700;
  background:var(--slate-soft); color:var(--slate); }
.steps li.done .n{ background:var(--lagoon); color:#fff; }
.steps b{ font-size:.9rem; font-weight:600; }
.steps small{ display:block; color:var(--muted); font-size:.78rem; line-height:1.3; }

/* ---------- top bar and headings ---------- */
.topbar{ display:flex; align-items:center; justify-content:space-between; gap:1rem; margin:0 0 .7rem; }
.brand{ display:flex; align-items:center; gap:.6rem; font-weight:700; font-size:1.2rem; letter-spacing:-.02em; }
.topbar-r{ display:flex; gap:.4rem; flex-wrap:wrap; justify-content:flex-end; }
.phead{ margin:.8rem 0 1.1rem; }
.phead h1{ font-size:2.05rem; line-height:1.1; letter-spacing:-.035em; font-weight:700; margin:0; padding:0; }
.phead p{ margin:.4rem 0 0; color:var(--muted); max-width:46rem; font-size:1rem; line-height:1.5; }
.sh{ display:flex; align-items:baseline; justify-content:space-between; gap:1rem; margin:1.9rem 0 .65rem;
  padding-bottom:.5rem; border-bottom:1px solid var(--line); }
.sh h2{ font-size:1.15rem; font-weight:650; letter-spacing:-.015em; margin:0; padding:0; }
.sh span{ font-size:.86rem; color:var(--muted); text-align:right; }

/* ---------- landing ---------- */
.landing{ display:grid; grid-template-columns:1.05fr .95fr; gap:2.8rem; align-items:center; padding:1.6rem 0 1rem; }
.landing h1{ font-size:clamp(2.3rem,4.6vw,3.5rem); line-height:1.03; letter-spacing:-.04em; font-weight:700; margin:0 0 1rem; padding:0; }
.landing p{ font-size:1.08rem; line-height:1.55; color:var(--body); max-width:33rem; margin:0; }
.specimen{ background:var(--paper); border:1px solid var(--line); border-radius:14px; padding:1.3rem 1.45rem;
  box-shadow:0 1px 0 rgba(29,42,51,.04),0 24px 44px -28px rgba(29,42,51,.4); }
.spec-cap{ font-size:.8rem; color:var(--muted); margin:0 0 .45rem; font-weight:600; }
.spec-doc{ font-family:var(--serif); font-size:1.05rem; line-height:1.62; color:#27343D; }
.spec-link{ height:28px; margin:.35rem 0 .35rem 1.2rem; border-left:2px dashed var(--lagoon); }
.spec-req{ font-weight:650; line-height:1.35; margin-bottom:.55rem; }
.spec-row{ display:flex; gap:.45rem; flex-wrap:wrap; }

/* ---------- evidence marker ---------- */
.hl,.spec-doc mark,.srcbox mark{
  background:linear-gradient(transparent 50%,var(--marker) 50%); color:inherit; padding:0 .12em; border-radius:2px;
  -webkit-box-decoration-break:clone; box-decoration-break:clone; }

/* ---------- chips, tags, legend ---------- */
.chip{ display:inline-flex; align-items:center; gap:.38rem; padding:.14rem .62rem; border-radius:999px; font-size:.76rem;
  font-weight:600; line-height:1.55; white-space:nowrap; background:var(--slate-soft); color:#3F4B55; }
.chip::before{ content:""; width:6px; height:6px; border-radius:50%; background:currentColor; opacity:.75; }
.chip.plain::before{ display:none; }
.chip.good{ background:var(--good-soft); color:var(--good); }
.chip.warn{ background:var(--warn-soft); color:var(--warn); }
.chip.bad{ background:var(--bad-soft); color:var(--bad); }
.chip.lagoon{ background:var(--lagoon-soft); color:var(--lagoon); }
.chip.marker{ background:var(--marker-soft); color:#735500; }
.tag{ display:inline-block; padding:.2rem .58rem; margin:0 .3rem .38rem 0; border-radius:5px; background:var(--slate-soft);
  font-size:.83rem; font-weight:500; color:#2F3C46; }
.legend{ display:flex; gap:1.1rem; flex-wrap:wrap; font-size:.82rem; color:var(--muted); margin:.2rem 0 .1rem; }
.legend span{ display:inline-flex; align-items:center; gap:.4rem; }
.sw{ width:12px; height:12px; border-radius:3px; display:inline-block; }
.sw.good,.cell.good,.mx td.c.good{ background:var(--good); }
.sw.warn,.cell.warn,.mx td.c.warn{ background:#E2AE49; }
.sw.slate,.cell.slate,.mx td.c.slate{ background:#D6DBE0; }
.sw.bad,.cell.bad,.mx td.c.bad{ background:var(--bad); }

/* ---------- summary strip ---------- */
.brief{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); background:var(--paper);
  border:1px solid var(--line); border-radius:14px; overflow:hidden; }
.brief>div{ padding:1rem 1.2rem; border-left:1px solid var(--line2); }
.brief>div:first-child{ border-left:none; }
.brief b{ display:block; font-size:1.95rem; line-height:1.05; letter-spacing:-.035em; font-variant-numeric:tabular-nums; }
.brief span{ display:block; font-size:.82rem; color:var(--muted); margin-top:.3rem; line-height:1.3; }

/* ---------- score meter (the only place a number is drawn big) ---------- */
.meter{ display:flex; align-items:center; gap:.75rem; }
.meter b{ font-size:1.6rem; line-height:1; letter-spacing:-.03em; min-width:2.1ch; font-variant-numeric:tabular-nums; color:var(--tone); }
.meter .ticks{ display:flex; gap:2px; align-items:center; }
.meter .ticks i{ width:4px; height:18px; border-radius:1px; background:var(--line); display:block; }
.meter .ticks i.on{ background:var(--tone); animation:tick .5s cubic-bezier(.2,.8,.2,1) both; animation-delay:calc(var(--d) * 28ms); }
.meter.lg b{ font-size:3rem; }
.meter.lg .ticks i{ width:5px; height:34px; }
.meter.good{ --tone:var(--good); } .meter.warn{ --tone:var(--warn); } .meter.bad{ --tone:var(--bad); }
@keyframes tick{ from{ transform:scaleY(.15); opacity:0; } }

/* ---------- coverage strip and matrix ---------- */
.strip{ display:flex; gap:4px; align-items:flex-end; flex-wrap:wrap; }
.cell{ display:block; width:13px; height:22px; border-radius:4px; }
.cell.nice{ height:13px; }
.mxwrap{ background:var(--paper); border:1px solid var(--line); border-radius:14px; padding:.9rem 1.1rem 1rem; overflow-x:auto; }
.mx{ border-collapse:separate; border-spacing:4px; width:100%; font-size:.78rem; }
.mx th{ font-weight:600; color:var(--muted); text-align:center; padding:.15rem .1rem; }
.mx th.must{ color:var(--lagoon); }
.mx th:first-child{ text-align:left; }
.mx td.name{ text-align:left; font-weight:600; font-size:.9rem; white-space:nowrap; padding-right:1.1rem; color:var(--ink); }
.mx td.c{ height:28px; min-width:26px; border-radius:6px; animation:pop .45s cubic-bezier(.2,.8,.2,1) both; animation-delay:calc(var(--d) * 14ms); }
.mx td.fit{ font-weight:700; font-variant-numeric:tabular-nums; text-align:right; padding-left:.7rem; color:var(--ink); font-size:.9rem; }
@keyframes pop{ from{ opacity:0; transform:scale(.5); } }

/* ---------- ranking board ---------- */
.hair{ height:1px; background:var(--line); margin:.1rem 0; }
.cand{ display:flex; gap:1rem; align-items:flex-start; }
.cand .rank{ font-size:1.7rem; font-weight:700; color:#B6C0C8; width:1.7rem; line-height:1.1; font-variant-numeric:tabular-nums; }
.cand .nm{ font-weight:700; font-size:1.12rem; letter-spacing:-.015em; line-height:1.2; }
.cand .sub{ color:var(--muted); font-size:.9rem; margin:.15rem 0 .55rem; }
.cand .row{ display:flex; gap:.4rem; flex-wrap:wrap; margin-top:.55rem; }

/* ---------- lanes (groups) ---------- */
.lanes{ display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); gap:1rem; }
.lane{ background:var(--paper); border:1px solid var(--line); border-top:4px solid var(--tone,var(--lagoon));
  border-radius:4px 4px 14px 14px; padding:1rem 1.15rem 1.1rem; }
.lane h3{ font-size:1.02rem; font-weight:650; margin:0; padding:0; line-height:1.3; letter-spacing:-.01em; }
.lane p{ color:var(--muted); font-size:.87rem; line-height:1.45; margin:.35rem 0 .8rem; }
.lane .m{ display:flex; justify-content:space-between; gap:.6rem; padding:.42rem 0; border-top:1px solid var(--line2); font-size:.9rem; }
.lane .m b{ font-weight:600; }
.lane .m span{ font-variant-numeric:tabular-nums; color:var(--muted); font-weight:600; }

/* ---------- ledgers (requirements, flags, verification, roles, audit) ---------- */
.ledger{ background:var(--paper); border:1px solid var(--line); border-radius:14px; overflow:hidden; }
.ledger>div:first-child{ border-top:none !important; }
.rq{ display:grid; grid-template-columns:3.2rem minmax(0,1.15fr) 8.6rem minmax(0,1.35fr); gap:1rem; padding:.95rem 1.2rem;
  border-top:1px solid var(--line2); align-items:start; }
.rq-id{ display:flex; align-items:center; gap:.42rem; font-weight:700; font-size:.8rem; color:var(--muted); }
.pri{ width:9px; height:9px; border-radius:2px; border:2px solid var(--lagoon); flex:none; box-sizing:border-box; }
.pri.must{ background:var(--lagoon); }
.rq-t{ font-weight:600; line-height:1.35; }
.rq-why{ color:var(--muted); font-size:.86rem; line-height:1.45; margin-top:.3rem; }
.rq-st{ display:flex; flex-direction:column; gap:.4rem; align-items:flex-start; }
.note-nv{ font-size:.76rem; font-weight:600; color:var(--warn); }
.ev{ font-family:var(--serif); font-size:.97rem; line-height:1.55; color:#27343D; }
.ev+.ev{ margin-top:.6rem; }
.ev .from{ display:block; font:500 .74rem/1.3 var(--sans); color:var(--muted); margin-top:.2rem; }
.ev .from a{ color:var(--lagoon); text-decoration:none; border-bottom:1px solid var(--lagoon-soft); }
.none{ color:#98A3AD; font-size:.86rem; font-style:italic; }
.item{ display:grid; grid-template-columns:11.5rem minmax(0,1fr); gap:1.1rem; padding:.95rem 1.2rem; border-top:1px solid var(--line2); align-items:start; }
.item .t{ font-weight:600; line-height:1.4; }
.item .chip{ white-space:normal; line-height:1.35; padding:.2rem .65rem; border-radius:10px; }
.item a{ color:var(--lagoon); text-decoration:none; border-bottom:1px solid var(--lagoon-soft); }
.item .d{ color:var(--body); font-size:.9rem; line-height:1.5; margin-top:.25rem; }
.item .ask{ font-size:.86rem; color:var(--muted); margin-top:.3rem; }
.role{ display:grid; grid-template-columns:9rem minmax(0,1fr); gap:1.2rem; padding:1rem 1.2rem; border-top:1px solid var(--line2); }
.role .when{ color:var(--muted); font-size:.85rem; font-variant-numeric:tabular-nums; line-height:1.45; }
.role .who{ font-weight:650; }
.role ul{ margin:.4rem 0 0; padding-left:1.1rem; color:var(--body); font-size:.9rem; line-height:1.5; }
.au{ display:grid; grid-template-columns:7.6rem minmax(0,1fr); gap:1.1rem; padding:.9rem 1.2rem; border-top:1px solid var(--line2); }
.au .when{ color:var(--muted); font-size:.78rem; line-height:1.5; font-variant-numeric:tabular-nums; }
.au .what{ line-height:1.5; }
.au .meta{ display:flex; gap:.5rem; flex-wrap:wrap; align-items:center; margin-bottom:.35rem; font-size:.78rem; color:var(--muted); }
.chk{ display:grid; grid-template-columns:3.4rem minmax(0,1fr); gap:.6rem; padding:.75rem 1.2rem; border-top:1px solid var(--line2); align-items:baseline; }
.chk b{ font-size:1.4rem; font-variant-numeric:tabular-nums; letter-spacing:-.03em; }
.chk span{ color:var(--body); line-height:1.45; }

/* ---------- panels, answers, source ---------- */
.panel{ background:var(--paper); border:1px solid var(--line); border-radius:14px; padding:1.1rem 1.3rem; }
.panel h3{ font-size:1rem; font-weight:650; margin:0 0 .5rem; padding:0; letter-spacing:-.01em; }
.panel .ins{ padding:.75rem 0; border-top:1px solid var(--line2); line-height:1.5; }
.panel h3+.ins{ border-top:none; padding-top:.2rem; }
.lede{ font-family:var(--serif); font-size:1.14rem; line-height:1.62; color:#27343D; max-width:52rem; }
.ans{ background:var(--paper); border:1px solid var(--line); border-left:4px solid var(--lagoon); border-radius:4px 14px 14px 4px; padding:1.1rem 1.3rem; }
.ans .q{ font-weight:700; font-size:1.05rem; letter-spacing:-.01em; }
.ans .a{ font-family:var(--serif); font-size:1.05rem; line-height:1.62; margin-top:.5rem; color:#27343D; }
.qcard{ background:var(--paper); border:1px solid var(--line); border-radius:14px; padding:1.1rem 1.3rem; }
.qcard .q{ font-weight:650; font-size:1.05rem; line-height:1.45; margin:.5rem 0 .3rem; }
.qcard .cols{ display:grid; grid-template-columns:1fr 1fr; gap:1.2rem; margin-top:.7rem; }
.qcard h4{ font-size:.86rem; margin:0 0 .25rem; padding:0; color:var(--muted); font-weight:600; }
.qcard ul{ margin:0; padding-left:1.05rem; font-size:.9rem; line-height:1.5; color:var(--body); }
.srcbox{ background:var(--paper); border:1px solid var(--line); border-radius:14px; padding:1.4rem 1.7rem; font-family:var(--serif);
  font-size:1.02rem; line-height:1.75; white-space:pre-wrap; max-height:640px; overflow:auto; color:#27343D; }
.empty{ border:1.5px dashed #C5CED6; border-radius:14px; padding:2.4rem 1.5rem; text-align:center; color:var(--muted);
  background:rgba(255,255,255,.65); line-height:1.5; }
.empty b{ display:block; color:var(--ink); font-size:1.15rem; margin-bottom:.3rem; letter-spacing:-.01em; }
.human{ border-left:3px solid var(--marker); padding:.4rem 0 .4rem .9rem; color:var(--body); font-size:.92rem; line-height:1.5; margin-top:1.4rem; }
.agents ol{ list-style:none; margin:0; padding:0; display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:1rem; counter-reset:a; }
.agents li{ position:relative; background:var(--paper); border:1px solid var(--line); border-radius:14px; padding:1rem 1.1rem 1.05rem; }
.agents li .n{ display:inline-grid; place-items:center; width:24px; height:24px; border-radius:50%; background:var(--lagoon); color:#fff; font-size:.76rem; font-weight:700; margin-bottom:.55rem; }
.agents b{ display:block; font-size:.98rem; letter-spacing:-.01em; }
.agents p{ margin:.3rem 0 0; color:var(--muted); font-size:.86rem; line-height:1.45; }

/* ---------- candidate dossier header ---------- */
.dossier{ display:grid; grid-template-columns:minmax(0,1fr) auto; gap:2rem; align-items:end; padding:.6rem 0 1.2rem;
  border-bottom:1px solid var(--line); margin-bottom:.4rem; }
.dossier h1{ font-size:2.3rem; line-height:1.05; letter-spacing:-.04em; font-weight:700; margin:0; padding:0; }
.dossier .sub{ color:var(--muted); font-size:.98rem; margin-top:.35rem; }
.dossier .row{ display:flex; gap:.4rem; flex-wrap:wrap; margin-top:.7rem; }
.dossier .cap{ color:var(--muted); font-size:.8rem; margin-top:.45rem; text-align:right; }

/* ---------- native widgets, tuned ---------- */
.stButton>button,.stDownloadButton>button{ border-radius:10px !important; font-weight:600 !important; padding:.5rem 1.1rem !important;
  border:1px solid var(--line) !important; background:var(--paper) !important; color:var(--ink) !important;
  transition:border-color .15s, color .15s, background .15s; }
.stButton>button:hover,.stDownloadButton>button:hover{ border-color:var(--lagoon) !important; color:var(--lagoon) !important; }
.stButton>button[kind="primary"],button[data-testid="stBaseButton-primary"]{ background:var(--lagoon) !important; color:#fff !important;
  border:1px solid var(--lagoon2) !important; }
.stButton>button[kind="primary"]:hover,button[data-testid="stBaseButton-primary"]:hover{ background:var(--lagoon2) !important; color:#fff !important; }
.stButton>button:focus-visible,.stDownloadButton>button:focus-visible{ outline:3px solid var(--marker) !important; outline-offset:2px; }
.stButton>button:disabled{ opacity:.5; }
textarea,input{ border-radius:10px !important; }
[data-testid="stExpander"]{ border:1px solid var(--line) !important; border-radius:12px !important; background:var(--paper); }
button[role="tab"]{ font-weight:600; }
div[data-baseweb="tab-highlight"]{ background-color:var(--lagoon) !important; }
[data-testid="stFileUploaderDropzone"]{ border-radius:12px; background:var(--paper); }
[data-testid="stStatusWidget"],[data-testid="stStatus"]{ border-radius:12px; }

@media (max-width:900px){
  .landing{ grid-template-columns:1fr; gap:1.4rem; }
  .rq{ grid-template-columns:1fr; gap:.55rem; }
  .item,.role,.au{ grid-template-columns:1fr; gap:.35rem; }
  .qcard .cols{ grid-template-columns:1fr; }
  .dossier{ grid-template-columns:1fr; }
  .dossier .cap{ text-align:left; }
  .block-container{ padding:1rem 1rem 4rem; }
}
@media (prefers-reduced-motion:reduce){
  .meter .ticks i.on,.mx td.c{ animation:none !important; }
}
"""


def inject() -> None:
    """Call once per run, right after st.set_page_config."""
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
