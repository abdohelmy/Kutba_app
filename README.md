# Khutba

Khutba is an iOS + Android + FastAPI starter for translating Arabic Friday-sermon PDF or DOCX documents into a
mosque-approved target language. AI output is never public by default: every segment must be
reviewed and explicitly approved by a mosque administrator before readers can see it.

## What is implemented

- A two-choice start screen: individual readers enter mosque selection without an account, while
  mosque administrators continue through a protected sign-in screen.
- Public mosque selection, date-sectioned published-sermon list with a prominent current-week
  group, and English-only reading view with source popups for canonical Arabic evidence.
- Mosque-admin login, Arabic khutba PDF/DOCX upload, translation status,
  segment review/edit/approval, publication, reversible hide/show, and confirmed removal. Titles
  are optional and inferred from the sermon when omitted. New uploads default to the upcoming
  Friday in both mobile clients.
- A bundled 1,000-entry Arabic khutba glossary highlights the first explicit difficult-term marker
  in each sermon. Tapping the colored English term opens its Arabic wording, contextual meaning,
  and literal wording from the supplied CSV.
- Tenant scoping: a mosque administrator cannot read or change another mosque's drafts.
- Provider-neutral translation interface:
  - OpenAI Responses API with structured Pydantic output.
  - OpenAI-compatible Chat Completions endpoint for vLLM, Ollama, or another local gateway.
  - Deterministic mock provider for tests.
- Canonical citations and verifier warnings are stored on each translated segment for reviewer audit.
- Reader-facing Quran citations use a Surah name and verse key such as `Al-Baqarah 2:152`; internal
  source IDs are confined to structured API data and are stripped if a model puts them in prose.
- Qur'anic quotations are matched against Quran.com's Arabic verse catalog and use the configured
  Quran.com English translation and Latin transliteration. Explicit collection/number hadith
  references use Sunnah.com's
  official API. If the hadith API cannot resolve a cue-marked passage, the OpenAI provider can run
  a hosted web search restricted to Sunnah.com. Accepted results must pass URL and Arabic-wording
  checks. Canonical sources produce direct source links in the mosque review screen.
- A separate verifier call can use a different configured model.
- Difficult or ambiguous religious terms retain the exact Arabic immediately after the English
  wording, such as `God-consciousness (التقوى)`. Citation popups place a checked Latin
  transliteration directly below the authenticated Arabic source text.
- Fail-closed publication: generated content remains unavailable to readers until all segments have
  `HUMAN_APPROVED` status.
- Files never cross the model-provider boundary. The API validates each PDF/DOCX, extracts its text,
  and sends only bounded text segments plus detected canonical excerpts to the configured provider.
- Scanned khutba PDFs use bounded local Arabic OCR. Every extracted Arabic khutba enters
  `SOURCE_REVIEW_REQUIRED`; a mosque reviewer must correct and confirm it before translation starts.

## Important accuracy boundary

No generative model or software pipeline can honestly guarantee a translation with zero mistakes.
This project treats translation as high-risk religious content and reduces risk through canonical
Qur'an/hadith retrieval, a second verification pass, visible evidence, and mandatory human
approval. The mosque remains responsible for appointing a qualified Arabic/target-language reviewer
and for approving the final wording. Canonical Qur'an and hadith quotations are retrieved from
Quran.com and Sunnah.com; ordinary sermon prose is translated directly from the reviewed Arabic.

## Repository

```text
backend/   FastAPI, SQLAlchemy, PDF/DOCX text extraction, retrieval, providers, tests
android/   Kotlin, Jetpack Compose, Retrofit Android client
ios/       Swift, SwiftUI, URLSession iPhone and iPad client
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
  --username mosque-admin \
  --name "Qualified Reviewer" \
  --password "replace-this-password"
uvicorn app.main:app --reload
```

Set a random `KHUTBA_SECRET_KEY` and `KHUTBA_OPENAI_API_KEY` in `backend/.env` before making a real
translation request. The OpenAI key belongs only on the API server; never put it in either mobile
client's build settings, resources, or local storage.

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
KHUTBA_QURAN_TRANSLITERATION_ID=57
```

For exact collection-and-number lookups, Sunnah.com requires an API key. Request one through the
official developer page at <https://sunnah.com/developers>, then set it only on the Python server:

```dotenv
KHUTBA_SUNNAH_API_KEY=your-sunnah-api-key
KHUTBA_SUNNAH_WEB_SEARCH_FALLBACK_ENABLED=true
```

The app detects full Arabic Qur'an verses, explicit references such as `(2:255)`, Qur'an quotation
marks such as `﴿...﴾`, cue phrases such as `بسم الله الرحمن الرحيم` and `قال الله`, and partially
quoted verses distinguished by tashkīl. It compares the Arabic words with Quran.com's verse catalog;
formatting alone is never enough to classify ordinary prose as Qur'an. The conventional sermon-opening
basmalah is linked to 1:1 unless the text explicitly cites 27:30.

Hadith cues include vocalized and unvocalized forms of `في الحديث` and `قال رسول الله`, as well as
quotation marks and tashkīl. An exact collection and number such as
`صحيح البخاري، حديث رقم 1` uses the official API first. If the API is unavailable, lacks credentials,
or the cue has no number, the OpenAI provider uses its web-search tool with an allow-list containing
only `sunnah.com`. A result is accepted only when its HTTPS Sunnah.com URL has the expected
collection/number form and its Arabic text has a contiguous match with the detected sermon passage.
Search failures, ambiguous results, unavailable APIs, and altered canonical wording are shown to the
reviewer. Generated output cannot be published until a human approves every segment. The hosted
fallback is unavailable when using a local OpenAI-compatible model, so those cases require manual
hadith verification unless a Sunnah API key is configured.

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

Open the `android/` directory in a current Android Studio installation with Android SDK 37. Start the
API on port 8000, then reverse that port before launching the debug app. Run the reverse command
again whenever the emulator or connected device is restarted. The debug build calls
`http://127.0.0.1:8000/api/v1/` through this tunnel. Configure the release `API_BASE_URL` in
`android/app/build.gradle.kts` to an HTTPS production domain.

```bash
adb reverse tcp:8000 tcp:8000
cd android
./gradlew assembleDebug
```

The scaffold follows current official Android guidance: AGP 9.2, Gradle 9.4.1, compile SDK 37, and the
stable Compose BOM. OpenAI integration uses the Responses API and structured outputs; the model is
configuration, not an Android dependency.

See [Architecture](docs/ARCHITECTURE.md) and [Production checklist](docs/PRODUCTION.md).

## Open iOS

Open `ios/Khutba.xcodeproj` in Xcode 16 or newer and run the `Khutba` scheme on an iOS 17+
simulator or device. The iOS app uses the same HTTPS API as Android and includes both the public
reader experience and the mosque-administrator upload, source-review, translation, approval,
publication, settings, and glossary workflows.

Select **Product → Test** to run the `KhutbaTests` target. See `ios/README.md` for configuration
details.
