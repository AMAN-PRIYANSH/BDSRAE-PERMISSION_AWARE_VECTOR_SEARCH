# Demo videos: what is in them and what to say

All videos are silent with captions burned in. Speak live while it plays, and pause where marked.

| File (in `results/demo/`) | Length | Use it when |
|---|---|---|
| `demo_video_v2.mp4` | 2:58 | Only one video is played: pipeline animation + live system + results |
| `part1_pipeline.mp4` | 1:18 | Showing slides too: play it on the architecture/example slide |
| `part2_live_demo.mp4` | 0:55 | Showing slides too: play it after the example slide |
| `demo_video.mp4` | 3:00 | Old version (kept for reference) |

## Part 1: the pipeline animation (0:00 - 1:18 in demo_video_v2)

| Time | On screen | Say (or pause here) |
|---|---|---|
| 0:00 | Title card | "Let's follow one search through our system. There are three paths." |
| 0:05 | Path A lights up (grey) | "A, loading, done once: Kaggle makes the embeddings, Spark adds the access labels, Iceberg stores everything, Spark loads Milvus." |
| 0:17 | Rahul types a question | **Pause.** "B is what happens on every search. Rahul is a CS engineer." |
| 0:21 - 0:30 | API, then allowed labels | "The API checks who he is. His role may read only public and cs-internal." |
| 0:30 | Embedding | "His question becomes 384 numbers." |
| 0:34 | Milvus shelves grey out | **Pause.** "Milvus searches only the allowed shelves. A board paper is never even a candidate. The filter comes from his role, not from his words." |
| 0:41 - 0:53 | Second check, audit, results | "Every result is checked again, the search is logged, and he gets only allowed papers. Spark, Iceberg and FAISS are not used here." |
| 0:53 | Path C (orange) | **Pause.** "C, revocation: an admin takes access away. The event goes through Kafka to Spark Streaming." |
| 1:00 | Fast path to Milvus | "Milvus is updated first, every 0.2 seconds, so the paper disappears in about one second." |
| 1:04 | Slow dashed path to Iceberg | "The lakehouse and audit history catch up a few seconds later, off the security path." |

## Part 2: the live system (1:18 - 2:13)

| Time | On screen | Say |
|---|---|---|
| 1:21 | Intern's results, all public | "This is the real search page on one million papers. The intern sees only public papers." |
| 1:34 | CS manager | "The CS manager also gets cs-internal and cs-confidential papers." |
| 1:40 | Intern types a long title | "Now the intern types the exact title of a board-only paper." |
| 1:46 | It is not in the list | **Pause.** "It is not there. Milvus removed it inside the search." |
| 1:57 | Board member: result #1 | "The board member searches the same title and gets it first." |
| 2:07 | Partition method | "Our second method gives the same answer." |

If asked about the "ms" number on the page: it includes turning the question into numbers on the CPU;
the search itself takes a few milliseconds.

## Results (2:13 - 2:58)

| Time | On screen | Say |
|---|---|---|
| 2:13 | Recall chart | "When a user may see 1%, search-then-filter returns about 1% of the right papers. Milvus stays near 100%." |
| 2:28 | Leakage tests | "38 tests, zero leaks, at 100 thousand and at one million papers. With the filter broken on purpose, 16 tests failed, so the tests really catch leaks." |
| 2:43 | Revocation chart | "Revocation went from 5 seconds to 1 second once we split the stream." |
| 2:53 | End card | "Thank you." |
