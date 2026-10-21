# Khutba 1.1.1

Android version code: **3**. The backend fixes were deployed to `35.207.58.39` on 25 September 2026.

## Translation startup

The previous optimized Android release removed `TranslationQueued`, its companion, and its generated serializer. The translation response is ignored by the repository, while Retrofit needs its type at runtime. The old R8 removal report lists all three classes as removed; the new release explicitly keeps them, and its retention report confirms their presence.

The current sermon (`91a183dd-33de-4630-a906-596ae981a4bc`) was still a draft with four untranslated sections when diagnosed. The VM logged its successful upload and source confirmation but no translation-start request. This is consistent with the client failing before sending the request. No recorded model failure was present.

## Backend corrections

- Preserve complete bounded quotations across sentence and paragraph boundaries. A bounded quotation longer than the usual segment size is kept intact rather than losing its search delimiters.
- Re-segment older drafts when translation starts, only if no section has translated text. Completed sections on retries are retained.
- Extract DOCX paragraphs, tables, and nested tables in document order; avoid duplicating merged cells.
- Offload PDF/DOCX extraction and document storage from the API event loop.
- Confirm proposed hadith Arabic and English against the real referenced Sunnah.com page before accepting it as a canonical source. Reject conflicting direct-reference numbers. Redirects are limited to HTTPS Sunnah.com pages, with a download-size limit.
- Keep the existing 70% sermon/source Arabic overlap threshold, three-candidate selection, preferred collections, short search queries, and concurrency limit.
- Add conservative glossary fallback matching for explicit English renderings of Arabic forms present in the sermon. Preserve complete phrases, skip conflicting senses, and support the previously requested “God-consciousness” rendering of التقوى. Canonical quotation wording remains unchanged; reader annotations can still highlight terms within it.
- Reject non-ASCII incorrect permission passwords with HTTP 403 instead of crashing.
- Trim mosque/display names before validating their minimum length.
- Reject publication of empty sermons and sections with only whitespace.

## Verification

- Backend: **131 tests passed**; Ruff and Git whitespace checks passed.
- Android: **6 unit tests passed**, including the translation request/response contract.
- Signed release APK and AAB built successfully; APK signature verified.
- Release lint: no errors; four existing warnings.
- R8 retention report contains the translation response class, companion, and serializer.
- VM source checksums match the tested local files. Staged imports and API schema passed using the VM runtime.
- Public HTTPS `/health` returns 200. An unauthenticated translation-start request returns 401.
- The database's logical digest was unchanged across deployment.

## Backup and delivery

The previous backend code and a consistent database backup are stored at:

`/opt/khutba/backups/api-fixes-20260925-eJjb1h`

Builds:

- `output/releases/1.1.1/khutba-1.1.1.apk`
- `output/releases/1.1.1/khutba-1.1.1.aab`

Install the new Android build, reopen the existing draft, and start translation. Re-uploading is unnecessary. Use the AAB in the existing Google Play testing track for Play-installed copies; a directly installed APK may have a different signing certificate from Google Play's app-signing certificate.

## Verification limits

No paid model request, translation of the user's current sermon, or publication was initiated during this work. Actual model access, billing, and the quality of a complete live translation remain to be checked when translation is started.

Sunnah.com returned HTTP 403 to the development-machine page check. When independent page verification is unavailable, the backend now reports an issue for the reviewer and does not accept the unverified candidate as canonical evidence. This does not crash the translation job, but that passage may need manual source verification. The fix does not claim that every Sunnah.com page is retrievable from the VM.
