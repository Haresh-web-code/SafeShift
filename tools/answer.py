
import multiprocessing
import os
import queue
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types
from search import search

load_dotenv()

MODEL_NAME = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.8-flash"
)

FALLBACK_MODEL = os.getenv(
    "GEMINI_FALLBACK_MODEL"
)

GEMINI_TIMEOUT = int(
    os.getenv("GEMINI_TIMEOUT", "10")
)

MAX_RETRIES = int(
    os.getenv("MAX_RETRIES", "2")
)

RESPONSE_BUDGET_MS = 2000

def gemini_worker(api_key, model_name, prompt, result_queue):
    client = None

    try:
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=10000,
                retry_options=types.HttpRetryOptions(
                    attempts=1
                )
            )
        )

        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )

        result_queue.put({
            "status": "success",
            "answer": response.text or ""
        })

    except Exception as error:
        result_queue.put({
            "status": "unavailable",
            "error": str(error)
        })

    finally:
        if client is not None:
            client.close()

def generate_answer(question):
    total_start = time.perf_counter()

    # 1. Retrieve relevant OSHA passages
    results, timings = search(question, top_k=5)

    if not results:
        return {
            "answer": (
                "No relevant OSHA passages were found. "
                "Consult your site's approved safety procedure."
            ),
            "sources": [],
            "ai_status": "not_used",
            "retrieval_ms": timings["total_ms"],
            "generation_ms": 0,
            "total_ms": (
                time.perf_counter() - total_start
            ) * 1000
        }

    # 2. Prepare OSHA context and source references
    context = ""
    sources = []

    for _score, chunk in results:
        context += (
            f"\nDocument: {chunk['document']}\n"
            f"Page: {chunk['page']}\n"
            f"Text: {chunk['text']}\n"
        )

        source = {
            "document": chunk["document"],
            "page": chunk["page"]
        }

        if source not in sources:
            sources.append(source)

    # 3. Check API key
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing from your .env file."
        )

    prompt = f"""
You are SafeShift, a workplace safety assistant.

Answer the supervisor's question using ONLY the
OSHA passages provided below.

Rules:
1. Give a concise and clear answer.
2. Use numbered steps for procedures.
3. Never invent safety requirements.
4. If the passages are insufficient, say so.
5. Never claim an incomplete procedure is sufficient.
6. Refer users to their site's approved safety procedure.
7. Do not replace site-specific safety instructions.

Supervisor question:
{question}

OSHA source passages:
{context}
"""

    # 4. Generate answer using Gemini
    generation_start = time.perf_counter()
    ai_status = "success"
    client = None

    try:
        client = genai.Client(
    api_key=api_key,
    http_options=types.HttpOptions(
        timeout=GEMINI_TIMEOUT * 1000,
        retry_options=types.HttpRetryOptions(
            attempts=1
        )
    )
)

        # Check remaining response budget
        remaining_ms = (
            RESPONSE_BUDGET_MS
            - (time.perf_counter() - total_start) * 1000
        )

        if remaining_ms <= 0:
            raise TimeoutError(
                "Response budget exhausted before Gemini generation."
            )

        # Call Gemini
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )

        answer = response.text

        if not answer:
            raise RuntimeError("Gemini returned an empty answer.")

    except Exception:
        # 4. Prepare a safe OSHA fallback first
        ai_status = "unavailable"

        answer = (
            "AI ANSWER UNAVAILABLE - OSHA SOURCE SUMMARY\n\n"
        )

        procedure_chunk = None

        for _score, chunk in results:
            text = chunk["text"].lower()

            if (
                "before they begin service" in text
                or "before beginning service" in text
            ):
                procedure_chunk = chunk
                break

        if procedure_chunk:
            answer += (
                "OSHA describes the following sequence before "
                "service or maintenance:\n\n"
                "1. Prepare for shutdown.\n"
                "2. Shut down the machine.\n"
                "3. Disconnect or isolate the machine from "
                "its energy sources.\n"
                "4. Apply lockout or tagout devices to the "
                "energy-isolating devices.\n"
                "5. Release, restrain, or otherwise render safe "
                "hazardous stored or residual energy.\n"
                "6. Verify isolation and deenergization.\n\n"
                "Follow the employer's specific energy-control "
                "procedure. This summary does not replace it.\n\n"
                f"Source: {procedure_chunk['document']}, "
                f"page {procedure_chunk['page']}\n"
            )
        else:
            answer += (
                "No complete servicing procedure was identified "
                "in the retrieved passages. Consult the site's "
                "approved energy-control procedure.\n\n"
            )

            for _score, chunk in results:
                answer += (
                    f"Source: {chunk['document']}, "
                    f"page {chunk['page']}\n"
                )

    # 5. Run Gemini in a separate process
    print(
    f"DEBUG: elapsed before Gemini section: "
    f"{(time.perf_counter() - total_start) * 1000:.2f} ms"
)
    remaining_ms = (
        RESPONSE_BUDGET_MS
        - (time.perf_counter() - total_start) * 1000
    )

    if remaining_ms > 200:
        result_queue = None
        process = None

        try:
            ctx = multiprocessing.get_context("spawn")
            result_queue = ctx.Queue()

            process = ctx.Process(
                target=gemini_worker,
                args=(
                    api_key,
                    MODEL_NAME,
                    prompt,
                    result_queue
                )
            )

            process.start()

            # Reserve time for cleanup and returning the answer
            wait_seconds = max(
                0,
                (remaining_ms - 150) / 1000
            )

            process.join(timeout=wait_seconds)

            if process.is_alive():
                process.terminate()
                process.join(timeout=0.1)
                ai_status = "timeout"
                print("\nGemini exceeded the response budget.")

            else:
                try:
                    gemini_result = result_queue.get(timeout=0.1)

                    if (
                        gemini_result["status"] == "success"
                        and gemini_result["answer"].strip()
                    ):
                        answer = gemini_result["answer"]
                        ai_status = "success"
                    else:
                        ai_status = "unavailable"
                        print(
                            "\nGemini error: "
                            + gemini_result.get(
                                "error", "Empty response"
                            )
                        )

                except queue.Empty:
                    ai_status = "unavailable"
                    print("\nGemini returned no result.")

        except Exception as error:
            ai_status = "unavailable"
            print(f"\nGemini error: {error}")

            if process is not None and process.is_alive():
                process.terminate()
                process.join(timeout=0.1)

        finally:
            if result_queue is not None:
                result_queue.close()
                result_queue.cancel_join_thread()

    else:
        ai_status = "skipped"
        print("\nGemini skipped: insufficient response budget.")

    generation_ms = (
        time.perf_counter() - generation_start
    ) * 1000
    print(
    f"DEBUG: elapsed before metrics: "
    f"{(time.perf_counter() - total_start) * 1000:.2f} ms"
)

    total_ms = (
        time.perf_counter() - total_start
    ) * 1000

    if total_ms > RESPONSE_BUDGET_MS:
        print(
            "\nWARNING: Internal processing exceeded "
            "the response budget."
        )

    # 5. Return answer and performance metrics
    return {
        "answer": answer,
        "sources": sources,
        "ai_status": ai_status,
        "retrieval_ms": timings["total_ms"],
        "generation_ms": generation_ms,
        "total_ms": total_ms
    }


if __name__ == "__main__":
    question = input("Ask a safety question: ")

    try:
        result = generate_answer(question)

        print("\n========== SAFESHIFT ANSWER ==========\n")
        print(result["answer"])

        print("\n========== OSHA SOURCES ==========\n")

        for source in result["sources"]:
            print(
                f"{source['document']} - "
                f"Page {source['page']}"
            )

        print("\n========== PERFORMANCE ==========\n")

        print(f"AI status: {result['ai_status']}")
        print(f"Retrieval: {result['retrieval_ms']:.2f} ms")
        print(f"Generation: {result['generation_ms']:.2f} ms")
        print(f"Total: {result['total_ms']:.2f} ms")
        print(f"Budget: {RESPONSE_BUDGET_MS} ms")

        if result["total_ms"] > RESPONSE_BUDGET_MS:
            print("WARNING: Response budget exceeded.")
        else:
            print("Response completed within budget.")

    except Exception as error:
        print(f"\nSafeShift error: {error}")
