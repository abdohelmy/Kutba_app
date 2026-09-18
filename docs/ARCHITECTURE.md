# Architecture

## Trust model

The generated translation is a draft, not an authoritative religious text. Trust is established by
canonical quotation checks and a qualified mosque reviewer, not by a model confidence score.

```mermaid
flowchart LR
    C["Mosque admin uploads Arabic khutba PDF or DOCX"] --> D["Extract text or run bounded local Arabic OCR"]
    D --> R["SOURCE_REVIEW_REQUIRED: mosque corrects and confirms Arabic"]
    R --> C1["Match Qur'an verses and exact hadith references"]
    C1 --> C2["Retrieve canonical Arabic, English, and Quran.com transliteration"]
    C2 --> F["Translation provider returns draft, source IDs, and hadith transliteration"]
    F --> G["Verifier checks translation, difficult terms, quotations, and transliteration"]
    G --> H["REVIEW_REQUIRED"]
    H --> I["Qualified reviewer edits and approves every segment"]
    I --> J["PUBLISHED"]
    J --> K["Guest readers choose a mosque"]
```

Only the transition from `REVIEW_REQUIRED` to `PUBLISHED` makes content visible to readers. The API
checks that every segment is `HUMAN_APPROVED`; neither mobile client can bypass this server-side rule.

## Backend layers

- `app/api/routes`: JSON/multipart HTTP contracts and authorization boundaries.
- `app/models`: mosque, user, sermon, segment, and state records.
- `app/services/documents.py`: bounded PDF/DOCX upload, signature validation, text extraction,
  Arabic check, segmentation, and storage.
- `app/services/ocr.py`: local Poppler rendering and Arabic Tesseract OCR with page/time limits.
- `app/services/retrieval.py`: canonical source data contract shared by retrieval and providers.
- `app/services/canonical_sources.py`: exact Qur'an matching, explicit hadith-reference detection,
  backend-only Quran.com/Sunnah.com clients, and safe reviewer warnings.
- `app/services/providers`: translation/verifier abstraction and OpenAI/open-model implementations.
- `app/services/translation.py`: background state machine and audit persistence.
- `app/services/glossary.py`: validated CSV loading and first-occurrence glossary annotations for
  explicit difficult-term markers in published translations.

The uploaded file is never sent to OpenAI or an OpenAI-compatible server. The provider receives only
the current extracted Arabic segment and detected canonical excerpts. Canonical excerpts from
Quran.com and Sunnah.com are marked separately, linked directly, and must not be re-translated when
their full Arabic quotation is matched. It is instructed to cite only supplied chunk IDs. The server
discards invented IDs, adds detected canonical citations deterministically, and flags a segment that
has no valid citation. Quran transliteration is copied from the configured Quran.com resource;
hadith transliteration is generated from the authenticated Sunnah.com Arabic and checked again by
the verifier. Difficult or ambiguous religious terms must keep their exact Arabic in parentheses
immediately after the English wording. Internal source IDs are accepted only in structured fields;
the server removes any `[S:...]` marker from translated prose, while the mobile clients render the
Surah name and verse key beside the citation link. The verifier runs as a separate request and may use
`KHUTBA_VERIFIER_MODEL` to separate the draft and checking models.

## API surface

| Actor | Endpoint | Purpose |
| --- | --- | --- |
| Anyone | `GET /api/v1/reader/mosques` | Choose mosque without an account |
| Anyone | `GET /api/v1/reader/mosques/{id}/sermons` | List only published khutbas |
| Anyone | `GET /api/v1/reader/sermons/{id}` | Read reviewed segments, references, and glossary annotations |
| Mosque admin | `POST /api/v1/auth/login` | Receive a short-lived admin bearer token |
| Admin | `POST /api/v1/admin/sermons` | Add and segment Arabic khutba PDF/DOCX |
| Admin | `DELETE /api/v1/admin/sermons/{id}` | Remove one tenant-scoped khutba and its stored file |
| Admin | `POST /api/v1/admin/sermons/{id}/hide` | Hide a published khutba from readers without deleting it |
| Admin | `POST /api/v1/admin/sermons/{id}/show` | Restore a hidden khutba to the public reader list |
| Admin | `PUT /api/v1/admin/sermons/{id}/source-text` | Correct and confirm extracted Arabic |
| Admin | `POST /api/v1/admin/sermons/{id}/translate` | Start grounded draft job |
| Admin | `PATCH /api/v1/admin/sermons/{id}/segments/{id}` | Edit/approve one segment |
| Admin | `POST /api/v1/admin/sermons/{id}/publish` | Publish only fully approved sermon |

## Provider substitution

`TranslationProvider` has two required operations: `translate` and `verify`. The OpenAI adapter uses
structured Pydantic output from the Responses API. The compatible adapter uses Chat Completions with
a JSON schema included in the prompt, which works with many local gateways but needs model-specific
evaluation.

Provider substitution does not change the database, API, or mobile clients. It also does not relax
the review gate.

## Current deliberate limitations

- Text PDFs and DOCX files are supported. Scanned khutba PDFs require local Poppler, Tesseract, and
  the `ara` language data; OCR output must pass mosque review before translation.
- Background tasks run in the API process. Production should move translation to a durable queue.
- SQLite and automatic table creation are for development. Production needs PostgreSQL and versioned
  migrations.
- Qur'an matching combines normalized full-verse matching with bounded partial matching for
  cue-following, quoted, or sufficiently vocalized passages. Formatting
  never establishes a Qur'an citation without a match to the Arabic catalog. Hadith detection uses
  vocalized/unvocalized cues, quotation marks, and tashkīl, but canonical retrieval still requires a
  collection and number because the official Sunnah.com API does not expose a free-text lookup in its
  published API specification.
- One target language is stored per sermon. Reuse the Arabic parent across language-specific
  translation records in the next schema revision.
- Reviewer signatures are not yet modeled.
