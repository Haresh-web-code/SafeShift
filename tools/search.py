
import json
import re
import time
from collections import Counter
from pathlib import Path

RESPONSE_BUDGET_MS = 2000
CHUNKS_FILE = Path("chunks.jsonl")


def tokenize(text):
    return re.findall(r"\b[a-zA-Z0-9]+\b", text.lower())


def load_chunks():
    if not CHUNKS_FILE.exists():
        raise FileNotFoundError(
            "chunks.jsonl not found. Run python ingest.py first."
        )

    chunks = []

    with CHUNKS_FILE.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                chunks.append(json.loads(line))

    return chunks





def search(query, top_k=5):
    total_start = time.perf_counter()

    # Step 1: Load chunks
    load_start = time.perf_counter()
    chunks = load_chunks()
    load_time = time.perf_counter() - load_start

    # Step 2: Prepare query
    search_start = time.perf_counter()

    query_words = set(tokenize(query))

    stop_words = {
        "what", "should", "the", "do", "does",
        "before", "after", "when", "how", "can",
        "workers", "worker", "a", "an", "is"
    }

    query_words -= stop_words

    if not query_words:
        return [], {
            "load_ms": load_time * 1000,
            "search_ms": 0,
            "total_ms": (
                time.perf_counter() - total_start
            ) * 1000
        }

    # Expand common safety-related terms
    synonyms = {
        "servicing": ["service", "maintenance", "servicing"],
        "service": ["servicing", "maintenance", "service"],
        "machine": ["machinery", "equipment", "machine"],
        "workers": ["employees", "authorized", "workers"],
        "isolation": ["isolated", "isolation", "deenergization"]
    }

    expanded_words = set(query_words)

    for word in query_words:
        expanded_words.update(synonyms.get(word, []))

    results = []

    # Step 3: Score each chunk
    for chunk in chunks:
        text = chunk["text"].lower()
        words = tokenize(text)
        counts = Counter(words)

        score = sum(counts[word] for word in expanded_words)

        # Reward important lockout/tagout concepts
        important_phrases = {
            "energy source": 5,
            "energy-isolating": 5,
            "hazardous energy": 5,
            "service or maintenance": 4,
            "verify that the energy": 5,
            "stored energy": 4,
            "lockout": 2,
            "tagout": 2
        }

        for phrase, weight in important_phrases.items():
            if phrase in text:
                score += weight

        # Prefer passages explicitly discussing preparation
        if "before performing service" in text:
            score += 6

        if "before performing" in text and "maintenance" in text:
            score += 3

        # Penalize table-of-contents passages
        if "contents" in text[:200]:
            score -= 10

        if score > 0:
            results.append((score, chunk))

    # Step 4: Sort by relevance
    results.sort(
        key=lambda item: item[0],
        reverse=True
    )

    # Step 5: Remove duplicate chunks, not pages
    unique_results = []
    seen_chunks = set()

    for score, chunk in results:
        chunk_key = (
            chunk["document"],
            chunk["page"],
            chunk["chunk_id"]
        )

        if chunk_key not in seen_chunks:
            unique_results.append((score, chunk))
            seen_chunks.add(chunk_key)

        if len(unique_results) >= top_k:
            break

    # Step 6: Measure search time
    search_time = time.perf_counter() - search_start
    total_time = time.perf_counter() - total_start

    return unique_results, {
        "load_ms": load_time * 1000,
        "search_ms": search_time * 1000,
        "total_ms": total_time * 1000
    }





if __name__ == "__main__":
    question = input("Ask a safety question: ")

    results, timings = search(question)
    remaining_ms = RESPONSE_BUDGET_MS - timings["total_ms"]

    print("\n--- RESPONSE BUDGET ---")
    print(f"Response budget: {RESPONSE_BUDGET_MS} ms")
    print(f"Remaining budget: {remaining_ms:.2f} ms")

    print("\nRelevant OSHA passages:\n")

    for score, chunk in results:
        print("-" * 60)
        print(f"Document: {chunk['document']}")
        print(f"Page: {chunk['page']}")
        print(f"Relevance score: {score}")
        print(f"Text: {chunk['text']}\n")

    print("\n--- PERFORMANCE METRICS ---")
    print(f"Data loading: {timings['load_ms']:.2f} ms")
    print(f"Search time: {timings['search_ms']:.2f} ms")
    print(f"Total time: {timings['total_ms']:.2f} ms")