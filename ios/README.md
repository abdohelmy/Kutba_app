# Khutba for iOS

The iOS client is a native SwiftUI counterpart to the Android app. It supports the public reader
journey and the complete mosque-administrator review workflow against the existing FastAPI API.

## Requirements

- Xcode 16 or newer
- iOS 17 or newer
- A running Khutba API

Open `Khutba.xcodeproj`, choose an iPhone or iPad simulator, and run the `Khutba` scheme. The app is
configured to use the same HTTPS API deployment as Android. To point at another environment, change
`APIClient.baseURL` in `Khutba/APIClient.swift`. Keep OpenAI and source-provider credentials on the
FastAPI server; they must never be added to the Xcode project.

The `KhutbaTests` target covers reader-text sanitization, citation labels, partial reader responses,
and date-section grouping. Select **Product → Test** in Xcode to run it.

## Latest Android parity updates

- Simplified start screen: “Read a khutba” and “Mosque sign in”.
- Arabic-only glossary links, including legacy cached English anchors when an
  adjacent Arabic note exists. English text is never used as the link fallback.
- Definition sheets show English, Arabic, letter transliteration, then meaning.
  Unvocalized Arabic is labeled as potentially missing vowels.
- Optional post-publish definitions screen, also available from a published
  khutba via “Add missing definitions”. Entries are shared globally using the
  existing backend; publishing remains successful if candidate loading fails.

The backend is already deployed. This update needs a new iOS app build; it does
not change or upload an App Store/TestFlight release automatically.
