# Khutba 1.1.0

Android version code: **2**. iOS version/build: **1.1.0 (2)**.

## Included changes

- Public sermons that a reader opens are saved on the device, including Arabic source notes,
  transliterations, source URLs, and glossary explanations. Mosque and sermon lists are cached too.
- The last selected mosque is remembered. Android remembers the scroll position; iOS remembers
  the current section. Text size is remembered on both platforms.
- Reader lists support pull-to-refresh. The reader supports search, highlighted matches, and
  navigation between matching sections. The English-only UI no longer asks for a language code.
- Cleaner section layout and scrollable source/glossary sheets.
- Admin workflow stages, approval counts, Needs attention filters, and a preview of saved edits.
- Glossary variations use Arabic/English rows, without requiring special separator syntax.
- Translation monitoring reconnects after temporary network errors, has no two-minute deadline,
  and resumes when an admin reopens a translating sermon. It never automatically restarts a paid
  translation request after a lost response.
- Completed translation sections are retained on retry. A server restart marks interrupted jobs
  as retryable, rather than leaving them permanently in TRANSLATING.
- Editing text around an unchanged quotation moves its citation. A changed or missing quotation
  is marked for review and cannot be approved until its source wording is restored. Ambiguous
  unanchored references are shown as section sources, not attached to a guessed sentence.
- Mobile citation and glossary offsets correctly convert the API's Unicode code-point indices.

## Important limits

- Open a sermon online once before relying on offline access. The external source website and
  PDF download still require an internet connection.
- Cached content can be older than the server. A successful list refresh removes downloaded
  copies of sermons that are now hidden or deleted. An offline device cannot learn about a
  withdrawal until it reconnects.
- Admin previews are authenticated, are not published, and are not saved in the reader cache.
  Preview includes saved edits only.
- Translation recovery assumes the existing **single API worker** deployment. Do not run multiple
  API workers against this startup-recovery implementation. A durable worker/queue is a separate
  future change, not part of this release.
- Login persistence, unsaved-edit recovery, glossary-version freezing, and the other unselected
  suggestions were not added.

## Verification

- Backend: 112 tests passed; Ruff checks passed.
- Android: 5 unit tests passed; release lint completed with no errors (dependency/style warnings
  remain); signed release APK and AAB built successfully.
- iOS: simulator build and all 10 tests passed.
- Final manual visual smoke test was blocked by the locked Mac. No live translation or paid
  model call was made during testing.

## Deployment and testing

The backend was **deployed on 18 September 2026 at 11:40 UTC** to
`instance-20260814-145151` (`35.207.58.39`). The API base URL remains
`https://35.207.58.39.sslip.io/api/v1/`.

- The existing `khutba-api` single-worker service is active with no automatic restart failures.
- Only the six intended backend source files changed. No dependency installation, database schema
  change, environment change, or VM scheduling change was needed.
- The database's complete logical dump digest is identical before and after deployment; all three
  users, one mosque, one published sermon, and three sections were preserved. Uploaded files and
  environment configuration also match their pre-deployment copies.
- A protected backup of the previous code, database, uploads, and configuration is stored on the VM
  at `/opt/khutba/backups/20260918T113544Z`.
- Verified the staged imports and schema using the VM's Python runtime, exact deployed source
  checksums, public HTTPS certificate/health, mosque and sermon reader endpoints, citation response
  fields, and unauthenticated rejection of the new admin preview endpoint.
- All 112 backend tests passed again before deployment. No live paid translation was triggered.

The following mobile/manual checks remain recommended before promoting the mobile release:

1. Open a published sermon; check text size, full-phrase glossary highlights, and both note sheets.
2. Return to the reader and confirm the remembered mosque and position. Test search and refresh.
3. Disconnect the test device: reopen a previously opened sermon and check the saved notes.
4. Reconnect and refresh after hiding a test sermon; confirm its saved copy is withdrawn.
5. Start a translation, leave the screen, then reopen it. Test a temporary network interruption.
6. In a test environment, restart the single-worker API during translation; retry and verify that
   already completed sections are retained.
7. Insert text before a citation and approve. Confirm the icon moves correctly in reader preview.
8. Change the quoted wording: approval must fail. Save as needing work, restore the quotation,
   and approve again.
9. Upload the AAB to the intended Play testing track. Version code 2 must be higher than every
   version already uploaded to that app; if a higher code has been used, increment and rebuild.

The APK uses the existing local release/upload signing key. A Play-installed copy may use Google's
app-signing key and reject a direct APK update; use the Play test track for those installations.
