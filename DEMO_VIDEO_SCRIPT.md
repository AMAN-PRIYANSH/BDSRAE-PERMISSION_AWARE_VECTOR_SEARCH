# 3-minute demo video: narration script

The video is already made and silent: `results/demo/demo_video.mp4` (3:00, 1920x1080, captions burned in).
Record the narration and lay it over the video (for example in Clipchamp, which comes with Windows:
drag in the video, record or import your voice, export at 1080p).

Times below match the video exactly. One person narrates. Speak calmly; each block has some spare seconds.

## 0:00 - 0:20  Title
Screen: title card.

Say: "Company chatbots search a vector database for the most similar documents. If that search ignores who
is asking, an intern can get a board-only document. We built semantic search over one million arXiv papers
that never returns a paper the user is not allowed to see, and we measured what that safety costs."

## 0:20 - 0:43  Pipeline
Screen: architecture diagram.

Say: "Embeddings are made on a free Kaggle GPU. Spark loads the papers into Apache Iceberg tables on MinIO,
gives every paper an access label from one policy file, and indexes them into Milvus. The permission filter
runs inside Milvus, before any result exists. Permission changes stream through Kafka and Spark Structured
Streaming, with a fast path straight to Milvus."

## 0:43 - 1:35  Live demo (real system, 1 million papers)
| Time | On screen | Say |
|---|---|---|
| 0:43 | Search page loads | "This is our search page, running on the full one-million-paper index." |
| 0:46 | Intern's results, all `public` | "Signed in as an intern. Every result is public." |
| 0:56 | CS manager, same query | "As the CS manager, the same question now also returns cs-internal and cs-confidential papers." |
| 1:02 | Intern types a long title | "Now the intern types the exact title of a paper that only the board may read." |
| 1:08 | Results without that paper | "It is not there. Milvus removed it inside the search, and our second safety check had nothing to block." |
| 1:19 | Board member: the paper is #1, red label | "The board member searches the same title, and the paper is the first result." |
| 1:29 | Partition method selected | "Our second method, one partition per label, gives the same answer." |

If asked about the "ms" number on the page: it includes turning the question into a vector on the CPU;
the search itself takes a few milliseconds (see the benchmark).

## 1:35 - 1:55  Leakage tests
Screen: "38 tests, 0 leaks".

Say: "Our leakage suite searches as all 10 roles with 200 queries each, uses the exact vectors of restricted
papers as queries, tries fake users and filter-injection text. All 38 tests pass, on one hundred thousand
and on one million papers."

## 1:55 - 2:15  Mutation check
Screen: red FAILED lines.

Say: "To prove the tests can catch a leak, we switched the filter off on purpose. Sixteen tests failed
immediately, exactly the ones that depend on that filter. The API test still passed, because our second
check removed the forbidden results: defence in depth."

## 2:15 - 2:35  Recall results
Screen: recall vs selectivity plot.

Say: "As users are allowed to see less, the usual approach, search first and then delete what they may not
see, loses almost everything: recall is about one percent when a user may see one percent of the papers.
Filtering inside Milvus keeps recall near one at every level, in about 5 to 20 milliseconds."

## 2:35 - 2:50  Revocation
Screen: revocation boxplot.

Say: "When access is taken away, our first pipeline left the paper visible for about 5 seconds. The cause
was the Spark micro-batch, not Milvus. Splitting the stream into a fast and a slow path brought it down to
about 1 second."

## 2:50 - 3:00  Close
Say: "Everything is free and open source, runs with one Docker Compose file, and the code, tests, report,
data card and model card are in our repository. Thank you."
