# Khutba 1.2.1

Android version code: **5**. Application ID: `com.khutba.app`.

## Changes

- Glossary links highlight the Arabic word or expression, not the English phrase.
- Definition popups show the English phrase, Arabic, letter transliteration, and
  definition in that order.
- Unvocalized Arabic transliteration is labeled as potentially missing vowels;
  it is not presented as an exact pronunciation guide.
- Older cached glossary responses also use Arabic-only links where an Arabic
  note is available. Online refresh loads the new popup fields.

The corresponding backend was deployed on 27 September 2026. No backend changes
are required for this release rebuild.

## Play release notes

Tap Arabic glossary terms to see their meaning.
Updated definition popups now include the English phrase, Arabic, and letter transliteration.
Improved glossary link placement.

## Delivery

- Upload `output/releases/1.2.1/khutba-1.2.1.aab` to Google Play.
- Use `output/releases/1.2.1/khutba-1.2.1.apk` for direct installation/testing.
- Keep `output/releases/1.2.1/mapping.txt` for release crash diagnostics.

The existing release-signing configuration is used. Play Console upload history
has not been checked; version code 5 is newer than the previous local release (4).
A directly installed APK may not update a Play-installed app if Google Play uses
a different app-signing certificate. Use the Play testing track in that case.

Nothing has been uploaded to Google Play. No production translation or publication
was initiated. Full on-device workflow and Play Console validation remain manual.

## Verification

- 11 Android unit tests passed.
- Release lint passed with no errors (six warnings and one hint).
- Signed APK and AAB builds succeeded. APK signature verified with the same
  certificate as version 1.2.0; manifest confirms version 1.2.1 / code 5.
- AAB JAR signature verified. The verifier also reports self-signed certificate,
  missing timestamp, and ZIP/JarInputStream manifest-order warnings, as with 1.2.0.
- Git whitespace check passed. The delivered bundle matches the built bundle.
