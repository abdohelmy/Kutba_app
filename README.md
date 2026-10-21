# Khutba

Khutba helps people follow the Friday sermon when they do not speak Arabic. Mosques upload their sermon, review its translation, and publish it for their congregation. Readers choose their mosque and open the khutba without creating an account.

The project includes a web app, Android and iOS apps, and a shared Python API. English and Danish translations are supported. The web app also lets a mosque use a microphone to help readers follow the imam's place in the sermon as he speaks.

[Open the web app](https://khutba-reader.abdohelmy1995.chatgpt.site/)

## Reading a khutba

Sermons are arranged by date so readers can find this week's khutba or return to an earlier one. The reader shows the translated text, with references and explanations available when needed.

- **Qur'an and hadith references:** A small citation beside a quotation opens its Arabic text, transliteration, and a link to the source.
- **Glossary explanations:** Some religious terms need more than a single translated word. Their Arabic wording appears beside the translation and can be tapped to see the phrase used in the text, its transliteration, and an explanation.
- **PDF downloads:** Readers can save the translated khutba as a PDF. Numbered references point to sources listed at the end.
- **Live following:** When a mosque starts a live session, readers can follow the highlighted passage while listening to the imam.

## Preparing and publishing a sermon

A mosque administrator uploads an Arabic PDF or Word document. The API extracts the text before translation; scanned PDFs can use OCR when it is available. The administrator checks the extracted Arabic first, since missing words or poor extraction can affect everything that follows.

The app then prepares an English draft, looks for Qur'an and hadith quotations, and adds relevant glossary explanations. Administrators can review and edit the translation alongside the Arabic, check its references, and approve it for publication. Drafts stay private until the required review is complete.

Danish is prepared from the approved, published English version. It keeps the connection to the original Arabic and the same source references, but its wording and glossary explanations need their own review. A reference supports the source quotation; it does not independently verify the Danish translation.

Titles can be suggested from the sermon and edited later. Uploads default to the upcoming Friday. Mosque administrators can also hide or remove sermons and update their mosque's name, city, and account settings.

## Translation, sources, and terminology

Ordinary sermon text is translated from the reviewed Arabic. Qur'an quotations are checked against Quran.com's Arabic text and linked to the selected published English translation. Hadith passages are looked up through Sunnah.com, with a search fallback for quotations that do not include a collection or hadith number.

Quotation marks and phrases such as قال الله and قال رسول الله help identify passages worth checking. The Arabic wording is compared with the retrieved source before a match is accepted. Reviewers can inspect the reference and any warnings alongside the translation.

The glossary handles Arabic spelling variations and vowel marks, with explanations intended for the context in which a term appears. Mosques can suggest entries and supply missing definitions after translation. An owner reviews these contributions before they become available for use.

Human review is central to the app. Translation models can misunderstand a passage, and a retrieved hadith still needs to be checked in its context, including its grading where available. The mosque is responsible for approving the wording its readers receive.

## Following the imam live

A mosque administrator can enable the microphone in the web app. Short audio chunks pass through the API to a speech worker running on a separate computer with an NVIDIA GPU. The worker currently uses Cohere's Arabic transcription model, with Silero voice activity detection to filter chunks with too little speech.

The API compares the transcript with the prepared Arabic khutba and maps the estimated position to the reader's translation. It allows for imperfect transcription, repeated words, and small changes in wording. When the imam speaks outside the written sermon, the tracker waits for enough evidence before moving to a different passage.

In the web reader, green marks the confirmed position. Pale yellow previews the next passage when the timer estimates that the current one has finished. It becomes yellow when the ending-word check passes, and stays there until the green highlight reaches or passes it. These previews help readers anticipate a transition; they do not confirm the imam's position themselves.

Live tracking is approximate and depends on microphone quality, transcription, and processing delay. The speech worker needs to remain connected during a live session. It also supports local diagnostic logs and experimental semantic comparisons for assessing matching quality.

## Managing the service

The web app includes an owner dashboard for approving mosque registrations and glossary contributions, managing accounts, reviewing sermons, and handling password resets. Mosque administrators manage their own mosque's content; readers only see published sermons from available mosques.

The API handles authentication, document extraction, translation, source retrieval, glossary data, publication, and live matching. Translation providers sit behind a common interface, with support for OpenAI and compatible model servers. Available features depend on the provider, particularly source-search tools.

## Inside the repository

| Folder | Contents |
| --- | --- |
| `backend/` | Python API, translation and review workflow, source retrieval, glossary, and live matching |
| `web/` | Web reader, mosque administration, owner dashboard, and microphone capture |
| `android/` | Native Android app built with Kotlin and Jetpack Compose |
| `ios/` | Native iPhone and iPad app built with SwiftUI |
| `live-worker/` | GPU speech worker, voice activity detection, and transcription diagnostics |
| `docs/` | Architecture notes, administration details, release notes, and privacy policy |

The clients use the same API, although features can differ between platforms and installed versions. Owner controls and microphone capture are currently available through the web app.
