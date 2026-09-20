from pathlib import Path

from models import SourceType
from tools import web_tools
from tools.pdf_tools import load_document

for f in sorted(Path("data/samples").glob("*.txt")):
    kind = SourceType.JOB_DESCRIPTION if f.name.startswith("jd") else SourceType.RESUME
    doc = load_document(f.read_bytes(), f.name, kind)
    print(f"{doc.doc_id:28} ok={doc.ok} chars={len(doc.text):5} warnings={doc.warnings}")

web_tools.reset_tool_state()
print("\n--- search_web ---")
print(web_tools.search_web.run(query="Flipkart company headquarters"))
print("\n--- check_github: real repo ---")
print(web_tools.check_github.run(target="scikit-learn/scikit-learn"))
print("\n--- check_github: Ananya's repo (fictional, expect NOT FOUND) ---")
print(web_tools.check_github.run(target="ananyarao-demo/docparse-lite"))
print("\n--- check_github: contributor check (expect 0 merged PRs) ---")
print(web_tools.check_github.run(target="scikit-learn/scikit-learn", username="ananyarao-demo"))

print("\n--- audit log ---")
for r in web_tools.drain_tool_log():
    print(f"{r.tool_name:13} ok={r.ok} {r.input_summary}")