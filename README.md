# Khutba

Khutba is an Android + FastAPI starter for translating Arabic Friday-sermon PDF or DOCX documents into a
mosque-approved target language. AI output is never public by default: every segment must be
reviewed and explicitly approved by a mosque administrator before readers can see it.

## What is implemented

- Individual registration/login, mosque selection, published-sermon list, and bilingual reading view.
- A polished account-type selector keeps individual and mosque sign-in flows clear.
- Mosque-admin login, trusted-source PDF/DOCX upload, Arabic khutba PDF/DOCX upload, translation status,
  segment review/edit/approval, and publication.
- Tenant scoping: a mosque administrator cannot read or change another mosque's drafts or sources.
- Provider-neutral translation interface:
  - OpenAI Responses API with structured Pydantic output.
  - OpenAI-compatible Chat Completions endpoint for vLLM, Ollama, or another local gateway.
  - Deterministic mock provider for tests.
- Source excerpts and verifier warnings are stored on each translated segment for reviewer audit.
- Qur'anic quotations are matched against Quran.com's Arabic verse catalog and use the configured
  Quran.com English translation. Explicit collection/number hadith references use Sunnah.com's
  official API. Both produce direct source links in the mosque review screen.
- A separate verifier call can use a different configured model.
- Fail-closed publication: generated content remains unavailable to readers until all segments have
  `HUMAN_APPROVED` status.
- Files never cross the model-provider boundary. The API validates each PDF/DOCX, extracts its text,
  and sends only bounded text segments plus approved source excerpts to the configured provider.
- Scanned khutba PDFs use bounded local Arabic OCR. Every extracted Arabic khutba enters
  `SOURCE_REVIEW_REQUIRED`; a mosque reviewer must correct and confirm it before translation starts.

## Important accuracy boundary

No generative model or software pipeline can honestly guarantee a translation with zero mistakes.
This project treats translation as high-risk religious content and reduces risk through controlled
sources, bounded retrieval, a second verification pass, visible evidence, and mandatory human
approval. The mosque remains responsible for appointing a qualified Arabic/target-language reviewer
and for deciding which sources are authoritative.

For this MVP, trusted-source retrieval is lexical and provider-neutral. Reference documents should be
bilingual or contain Arabic headings/terms beside the approved target-language wording. A later
production phase should add reviewed multilingual embeddings and an evaluation set; do not silently
replace the human review gate with a similarity score.

## Repository

```text
backend/   FastAPI, SQLAlchemy, PDF/DOCX text extraction, retrieval, providers, tests
android/   Kotlin, Jetpack Compose, Retrofit Android client
docs/      architecture, workflow, and production-readiness notes
```

## Run the API

Python 3.11 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e 'backend[dev]'
cp .env.example backend/.env
cd backend
python -m app.seed \
  --mosque "Central Mosque" \
  --city "Copenhagen" \
  --email admin@example.com \
  --name "Qualified Reviewer" \
  --password "replace-this-password"
uvicorn app.main:app --reload
```

Set a random `KHUTBA_SECRET_KEY` and `KHUTBA_OPENAI_API_KEY` in `backend/.env` before making a real
translation request. The OpenAI key belongs only on the API server; never put it in Android's
`BuildConfig`, resources, or local storage.

The interactive API documentation is at `http://localhost:8000/docs`.

### Configure Qur'an and hadith sources

For local testing, the default `KHUTBA_QURAN_API_MODE=legacy` uses Quran.com's current public content
endpoint and resource `20` (Saheeh International). For production, request Quran Foundation API
access at <https://api-docs.quran.com/request-access/>, then configure the server-only credentials:

```dotenv
KHUTBA_QURAN_API_MODE=oauth
KHUTBA_QURAN_FOUNDATION_ENVIRONMENT=production
KHUTBA_QURAN_FOUNDATION_CLIENT_ID=your-client-id
KHUTBA_QURAN_FOUNDATION_CLIENT_SECRET=your-client-secret
KHUTBA_QURAN_TRANSLATION_ID=20
```

Sunnah.com requires an API key. Request one through the official developer page at
<https://sunnah.com/developers>, then set it only on the Python server:

```dotenv
KHUTBA_SUNNAH_API_KEY=your-sunnah-api-key
```

The app detects full Arabic Qur'an verses, explicit references such as `(2:255)`, Qur'an quotation
marks such as `﴿...﴾`, cue phrases such as `بسم الله الرحمن الرحيم` and `قال الله`, and partially
quoted verses distinguished by tashkīl. It compares the Arabic words with Quran.com's verse catalog;
formatting alone is never enough to classify ordinary prose as Qur'an. The conventional sermon-opening
basmalah is linked to 1:1 unless the text explicitly cites 27:30.

Hadith cues include vocalized and unvocalized forms of `في الحديث` and `قال رسول الله`, as well as
quotation marks and tashkīl. A canonical Sunnah.com lookup still requires an exact collection and
number, for example `صحيح البخاري، حديث رقم 1`, because the official API does not offer a supported
free-text search endpoint. A detected hadith without that reference is shown to the reviewer with a
passage excerpt and must be verified manually. Unavailable APIs and canonical wording not copied
verbatim are also shown as blocking-quality warnings. Generated output cannot be published until a
human approves every segment.

PDF and DOCX extraction preserves text, paragraph breaks, quotation characters, and tashkīl when the
source parser/OCR returns them. Font, colour, and bold styling are not used as trust signals because
PDF extraction and OCR do not preserve them reliably.

Sunnah.com supplies the referenced English wording and any grade returned by its API. A successful
lookup does not mean every narration in every collection is automatically *sahih*; the qualified
reviewer must still inspect the collection, number, and displayed grading.

### Enable scanned-PDF OCR

The API uses local Poppler and Tesseract commands. The official Tesseract Arabic language code is
`ara`, which is the default because khutbas are expected to be Arabic. Set
`KHUTBA_OCR_LANGUAGES=ara+eng` only for genuinely bilingual scanned pages.

```bash
# macOS with Conda (keeps OCR tools inside this project)
conda create -y -p .local/ocr -c conda-forge tesseract poppler
export KHUTBA_TESSERACT_COMMAND="$PWD/.local/ocr/bin/tesseract"
export KHUTBA_PDFTOPPM_COMMAND="$PWD/.local/ocr/bin/pdftoppm"

# Ubuntu/Debian alternative
sudo apt-get install tesseract-ocr tesseract-ocr-ara poppler-utils
```

Confirm the installation before starting the API:

```bash
$KHUTBA_TESSERACT_COMMAND --list-langs
# Must include: ara and eng
```

OCR is limited by page count, file size, render DPI, and command timeouts. The generated Arabic is
never trusted automatically and cannot proceed to English translation until the mosque confirms it.

## Use a local/open model

Point the same API at an OpenAI-compatible server:

```dotenv
KHUTBA_TRANSLATION_PROVIDER=openai_compatible
KHUTBA_OPENAI_BASE_URL=http://localhost:11434/v1
KHUTBA_OPENAI_API_KEY=local
KHUTBA_OPENAI_MODEL=your-translation-model
KHUTBA_VERIFIER_MODEL=your-independent-verifier-model
```

The selected server/model must support JSON-object responses. Before using any open model for
publication, run mosque-approved Arabic test sermons through it and measure omissions, additions,
Qur'an/hadith wording, names, numbers, polarity, and Islamic legal terminology.

## Run tests

```bash
cd backend
../.venv/bin/ruff check .
../.venv/bin/pytest -q
```

## Open Android

Open the `android/` directory in a current Android Studio installation with Android SDK 37. The debug
build calls `http://10.0.2.2:8000/api/v1/`, which maps the emulator to the host machine. Configure the
release `API_BASE_URL` in `android/app/build.gradle.kts` to an HTTPS production domain.

```bash
cd android
./gradlew assembleDebug
```

The scaffold follows current official Android guidance: AGP 9.2, Gradle 9.4.1, compile SDK 37, and the
stable Compose BOM. OpenAI integration uses the Responses API and structured outputs; the model is
configuration, not an Android dependency.

See [Architecture](docs/ARCHITECTURE.md) and [Production checklist](docs/PRODUCTION.md).
