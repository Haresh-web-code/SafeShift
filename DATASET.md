# SafeShift dataset

## Overview

The Week 1 evaluation dataset consists of publicly accessible U.S. Occupational Safety and Health Administration (OSHA) publications in PDF format. The selected documents cover hazardous-energy control and electrical hazards relevant to factory maintenance and supervision.

## Source documents and verification

| OSHA publication | Official source URL | Committed sample file | Verified PDF pages | SHA-256 |
|---|---|---|---:|---|
| OSHA 3120, *Control of Hazardous Energy (Lockout/Tagout)* | [osha3120.pdf](https://www.osha.gov/sites/default/files/publications/osha3120.pdf) | `data/sample/OSHA3120_safeshift.pdf` | 45 | `3ea7380fa10860417ed30720eaf8beb7a85d106e3dafb97b880001df6552767b` |
| OSHA 3075, *Controlling Electrical Hazards* | [osha3075.pdf](https://www.osha.gov/sites/default/files/publications/osha3075.pdf) | `data/sample/OSHA3075_safeshift.pdf` | 71 | `e32343de21329cd840b9c1a620a2c4cecf173b3357039a21c773e06cebb8bdb9` |

**Dataset total:** 2 documents, **116 PDF pages**. This exceeds the 50-page Week 1 requirement.

Page totals were counted from the local PDFs with `pypdf.PdfReader` and `len(reader.pages)`. Each committed sample was also checked against its corresponding file in `data/raw/`; the byte lengths and SHA-256 hashes match. Page references in [docs/QUESTIONS.md](docs/QUESTIONS.md) refer to 1-based physical PDF pages, not the page numbers printed inside a publication.

## Collection method and storage

The source URLs point to OSHA's official publication PDFs. The PDFs are retained as PDF files, and their source URLs, physical page totals, and checksums are recorded above. The sample copies are stored in `data/sample/` for review and evaluation. Full local copies, when present, belong under `data/raw/`, which is ignored by Git and is not included in the Week 1 commit.

The acquisition date was not recorded. Live requests to both OSHA PDF URLs returned HTTP 403 from the environment used for this verification, so a fresh download from the endpoints could not be confirmed during this run. The local PDF metadata/publication identifiers, page totals, and sample-to-raw byte identity were verified locally.

## Use and limitations

These are OSHA publications, not site-specific procedures. Attribution and official source links are retained. A separate reuse license was not confirmed during this review; check the publisher's terms before redistributing the documents. This small set does not comprehensively cover chemical handling, machine guarding, confined spaces, or all applicable standards, and it must not be used by itself to determine workplace compliance.

## Evaluation

The ten supervisor questions, their source PDF pages, and the out-of-scope question are documented in [docs/QUESTIONS.md](docs/QUESTIONS.md).
