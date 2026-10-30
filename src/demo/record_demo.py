"""Record the live demo of the Streamlit UI as a silent video (narration is added later).

Runs inside the app container, against the real stack (Milvus with the loaded index):
    python -m src.demo.record_demo --url http://ui:8501
Output: results/demo/ui_demo.webm  and  results/demo/ui_demo_scenes.json (scene start times + captions)

Scenes (the captions are burned into the final video later):
  1. intern, general query            -> only `public` results
  2. CS manager, same query           -> cs-internal / cs-confidential appear
  3. intern types the EXACT title of a board-only paper -> it is NOT returned
  4. board member, same title          -> it is result #1, label board-restricted
  5. same, partition method            -> same answer through the other method
"""
import argparse
import json
import os
import time

from playwright.sync_api import sync_playwright
from pymilvus import MilvusClient

OUT = os.environ.get("PAVS_RESULTS", "/app/results") + "/demo"
GENERAL_QUERY = "graph neural networks for molecules"


def find_board_doc():
    """Title of a board-restricted paper that the board member gets as result #1 when searching its title
    (checked here, before recording, with the same search code the UI uses)."""
    from src.pavs.search import Searcher
    c = MilvusClient(uri=os.environ.get("PAVS_MILVUS_URI", "http://standalone:19530"))
    rows = c.query("docs_filter", filter='access_label == "board-restricted"',
                   output_fields=["doc_id", "title"], limit=200)
    s = Searcher(audit_path=None)
    for r in rows:
        title = " ".join(r["title"].split())
        if not (40 <= len(title) <= 110) or "$" in title or "\\" in title:
            continue
        top = s.search("arjun.board", query=title, k=1, audit=False).hits
        intern = s.search("ananya.intern", query=title, k=10, audit=False).hits
        if top and top[0]["doc_id"] == r["doc_id"] and all(h["doc_id"] != r["doc_id"] for h in intern):
            return title
    raise SystemExit("no suitable board-restricted title found")


def select_user(page, user):
    page.locator('[data-testid="stSelectbox"]').first.click()
    page.get_by_role("option", name=user, exact=True).click()


def set_query(page, text):
    box = page.locator('[data-testid="stTextInput"] input').first
    box.click()
    box.fill("")
    box.type(text, delay=35)           # visible typing in the video
    box.press("Enter")


def wait_results(page, settle=1.5, expect=None):
    """Wait until Streamlit has finished re-running the script. If `expect` is given, also wait until the
    results table shows that text (so the video never shows the previous user's results)."""
    status = page.locator('[data-testid="stStatusWidget"]')
    try:
        status.wait_for(state="visible", timeout=3000)
    except Exception:
        pass
    try:
        status.wait_for(state="hidden", timeout=30000)
    except Exception:
        pass
    page.get_by_text("results in").first.wait_for(timeout=30000)
    if expect:
        page.locator('[data-testid="stDataFrame"]').get_by_text(expect).first.wait_for(state="attached", timeout=30000)
    page.wait_for_timeout(int(settle * 1000))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://ui:8501")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    board_title = find_board_doc()
    print("board-only title:", board_title, flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        # warm-up (not recorded): loads the embedding model and the Milvus collections
        warm = browser.new_page(viewport={"width": 1920, "height": 1080})
        warm.goto(a.url)
        wait_results(warm, settle=0.5)
        warm.close()

        # 1536x864 page: text is larger relative to the frame; scaled to 1920x1080 when the video is edited
        ctx = browser.new_context(viewport={"width": 1536, "height": 864},
                                  record_video_dir=OUT, record_video_size={"width": 1536, "height": 864})
        page = ctx.new_page()
        t0 = time.time()
        scenes = []

        def scene(caption):
            scenes.append({"t": round(time.time() - t0, 2), "caption": caption})
            print(f"{scenes[-1]['t']:6.1f}s  {caption}", flush=True)

        page.goto(a.url)
        wait_results(page)
        scene("Signed in as an intern: every result is labelled public")
        page.wait_for_timeout(6000)

        select_user(page, "meera.csmgr")
        wait_results(page, settle=2.5)
        scene("CS manager, same query: cs-internal and cs-confidential papers now appear")
        page.wait_for_timeout(6000)

        select_user(page, "ananya.intern")
        wait_results(page, settle=0.5)
        scene("Intern searches the exact title of a board-only paper...")
        set_query(page, board_title)
        wait_results(page)
        scene("...the board-only paper is not returned (blocked inside Milvus, second check: 0)")
        page.wait_for_timeout(6000)

        select_user(page, "arjun.board")
        wait_results(page, expect="board-restricted")
        scene("Board member, same title: the paper is result #1, label board-restricted")
        page.wait_for_timeout(6000)

        page.get_by_text("partition", exact=True).first.click()
        wait_results(page)
        scene("Same search with the partition method: same answer")
        page.wait_for_timeout(5000)
        scene("end")

        video = page.video
        ctx.close()
        src = video.path()
        dst = f"{OUT}/ui_demo.webm"
        os.replace(src, dst)
        browser.close()

    json.dump({"board_title": board_title, "scenes": scenes}, open(f"{OUT}/ui_demo_scenes.json", "w"), indent=2)
    print("saved", dst)


if __name__ == "__main__":
    main()
