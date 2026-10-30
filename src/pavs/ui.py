"""Demo UI (Streamlit). Pick a user, type a query, see only what that user may see.

Run:  streamlit run src/pavs/ui.py --server.port 8501 --server.address 0.0.0.0
Then open http://localhost:8501
"""
import pandas as pd
import streamlit as st

from src.pavs import policy
from src.pavs.search import Searcher

st.set_page_config(page_title="Permission-Aware Vector Search", layout="wide")


def _label_colour(label):
    """Background colour by sensitivity, so restricted results stand out in the demo."""
    if label.endswith("restricted"):
        return "background-color: #f8d7da"
    if label.endswith("confidential"):
        return "background-color: #ffe5c2"
    if label.endswith("internal"):
        return "background-color: #dbeafe"
    return ""


@st.cache_resource
def get_searcher():
    return Searcher()


st.title("Permission-Aware Vector Search")
st.caption("arXiv papers, 11 access labels, 10 roles. Search never returns a document "
           "outside the user's labels.")

left, right = st.columns([1, 3])
with left:
    user = st.selectbox("Signed in as", list(policy.USERS))
    role = policy.USERS[user]
    st.markdown(f"**Role:** `{role}`")
    st.markdown("**May read labels:**")
    for l in policy.ROLES[role]:
        st.markdown(f"- `{l}`")
    method = st.radio("Permission method", ["filter", "partition"], horizontal=True,
                      help="filter = metadata filter inside Milvus; partition = search only the "
                           "partitions of allowed labels")
    k = st.slider("Results (k)", 1, 50, 10)

with right:
    query = st.text_input("Search query", "graph neural networks for molecules")
    if query:
        res = get_searcher().search(user, query=query, k=k, method=method)
        st.markdown(f"**{len(res.hits)} results** in **{res.latency_ms:.0f} ms** "
                    f"(blocked by second check: {res.violations_blocked})")
        if res.hits:
            df = pd.DataFrame(res.hits)[["access_label", "title", "arxiv_id", "score"]]
            df["score"] = df["score"].round(3)
            st.dataframe(df.style.map(_label_colour, subset=["access_label"]).format({"score": "{:.3f}"}),
                         use_container_width=True, hide_index=True)
