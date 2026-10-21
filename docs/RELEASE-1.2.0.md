# Khutba 1.2.0

Android version code: **4**. Application ID: `com.khutba.app`.

## Changes

- Shorter, clearer start-screen wording and simpler reader/admin choices.
- Optional definitions screen after publishing. Admins can add explanations for
  Arabic-marked ambiguous terms missing from the glossary, with the original
  sentence and a confirmed English highlight phrase.
- Shared glossary entries are available to all mosques. Existing entries cannot
  be overwritten through this flow. Mosque-specific overrides remain supported.
- Published khutbas have an “Add missing definitions” action to reopen the screen.
- More reliable complete-phrase highlighting across typography and line wrapping.
- Conservative divine-name matching and glossary suppression inside quotations.

The shared-glossary backend was deployed on 26 September 2026. These screens
require the new Android build; the backend alone does not update installed apps.

## Play release notes

Simpler start screen and clearer navigation.
Mosque admins can now add missing word definitions after publishing a khutba.
Improved glossary highlighting and handling of Allah’s names.

## Delivery

- Upload `output/releases/1.2.0/khutba-1.2.0.aab` to Google Play.
- `output/releases/1.2.0/khutba-1.2.0.apk` is for direct installation/testing.
- Keep `output/releases/1.2.0/mapping.txt` for release crash diagnostics.
- This release uses the existing local release-signing configuration. A directly
  installed APK may not update a Google Play installation if Play uses a different
  app-signing certificate. Use the Play testing track in that case.
- Version code 4 is newer than the previous local release (3). Play Console upload
  history has not been inspected; if 4 was used elsewhere, increment it again.

Nothing has been uploaded to Google Play by this task. No paid translation or
production publication was initiated for release verification.

## Verification

- Backend: 167 tests passed.
- Android: 10 unit tests passed; signed release APK and AAB built successfully.
- APK signature verified; manifest reports version 1.2.0, code 4.
- AAB JAR signature verified. The verifier also reported self-signed certificate,
  missing timestamp, and ZIP/JarInputStream manifest-order warnings. Play Console
  validation has not been performed.
- Release lint: no errors, six warnings and one hint (dependency/tooling updates,
  Kotlin extensions, and boxed state).
- R8 mapping retains the glossary candidate/contribution serializers and the
  translation-queued serializer.
- No on-device visual or complete production workflow test was performed for this
  release build. Test it through the existing Play testing track before rollout.
