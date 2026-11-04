
import json
import os
from pathlib import Path

from pypdf import PdfReader

DATASET_DIR = Path(os.getenv("OSHA_DATASET_DIR", "data/raw"))
OUTPUT_FILE = Path("chunks.jsonl")

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


def split_text(text):
    chunks = []
    start = 0

    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        start += CHUNK_SIZE - CHUNK_OVERLAP

    return chunks


def ingest_pdfs():
    pdf_files = list(DATASET_DIR.glob("*.pdf"))

    if not pdf_files:
        print("No PDF files found in the dataset folder.")
        return

    total_chunks = 0

    with OUTPUT_FILE.open("w", encoding="utf-8") as output:
        for pdf_path in pdf_files:
            print(f"Processing: {pdf_path.name}")

            reader = PdfReader(str(pdf_path))

            for page_number, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""

                for chunk_number, chunk in enumerate(
                    split_text(text), start=1
                ):
                    record = {
                        "document": pdf_path.name,
                        "page": page_number,
                        "chunk_id": chunk_number,
                        "text": chunk
                    }

                    output.write(json.dumps(record) + "\n")
                    total_chunks += 1

    print("\nIngestion complete!")
    print(f"Total chunks created: {total_chunks}")
    print(f"Output saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    ingest_pdfs()
