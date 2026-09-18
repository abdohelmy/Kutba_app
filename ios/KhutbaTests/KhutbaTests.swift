import XCTest
@testable import Khutba

final class KhutbaTests: XCTestCase {
    func testReaderTextRemovesInternalSourceMarkers() {
        XCTAssertEqual(
            sanitizedReaderText("Remember God [S:quran-2-152] , always."),
            "Remember God, always."
        )
    }

    func testQuranReferenceFallsBackToSourceIdentifier() {
        let citation = Citation(
            chunkId: "quran-2-152",
            sourceId: "quran.com:2:152",
            title: "Al-Baqarah",
            authority: "Quran.com",
            excerpt: "Remember Me; I will remember you.",
            arabicExcerpt: nil,
            transliteration: nil,
            displayReference: nil,
            sourceKind: "quran",
            url: nil,
            translationStart: nil,
            translationEnd: nil,
            arabicStart: nil,
            arabicEnd: nil
        )

        XCTAssertEqual(citationReference(citation), "Qur’an 2:152")
    }

    func testReaderSegmentDecodesWithoutAdminOnlyFields() throws {
        let data = Data(#"""
        {
            "id":"segment-1",
            "ordinal":0,
            "translated_text":"A reviewed translation.",
            "citations":[],
            "glossary_terms":[]
        }
        """#.utf8)

        let segment = try JSONDecoder.khutba.decode(SermonSegment.self, from: data)

        XCTAssertNil(segment.arabicText)
        XCTAssertNil(segment.verificationStatus)
        XCTAssertEqual(segment.translatedText, "A reviewed translation.")
    }

    func testLoginPayloadUsesBackendSnakeCaseContract() throws {
        let data = try JSONEncoder.khutba.encode(
            LoginRequest(username: "mosque-admin", password: "secret", accountType: "MOSQUE")
        )
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: String])

        XCTAssertEqual(object["account_type"], "MOSQUE")
        XCTAssertNil(object["accountType"])
    }

    func testDateSectionsSeparateCurrentAndUpcomingKhutbas() {
        let calendar = Calendar(identifier: .gregorian)
        let now = DateFormatters.apiDate.date(from: "2026-08-19")!
        let thisWeek = summary(id: "week", date: "2026-08-21")
        let upcoming = summary(id: "future", date: "2026-08-28")
        let old = summary(id: "old", date: "2026-07-31")

        let sections = SermonDateSections(
            sermons: [upcoming, old, thisWeek],
            now: now,
            calendar: calendar
        )

        XCTAssertEqual(sections.thisWeek.map(\.id), ["week"])
        XCTAssertEqual(sections.upcoming.map(\.id), ["future"])
        XCTAssertEqual(sections.archive.first?.sermons.map(\.id), ["old"])
    }

    private func summary(id: String, date: String) -> SermonSummary {
        SermonSummary(
            id: id,
            mosqueId: "mosque",
            title: "Khutba \(id)",
            khutbaDate: date,
            targetLanguage: "en",
            status: SermonStatus.published,
            providerName: nil,
            modelName: nil,
            failureReason: nil,
            publishedAt: nil
        )
    }

    func testUnicodeOffsetsAndRepeatedCitationOccurrences() throws {
        let text = "🌙 Remember Me. Again: Remember Me."
        let range = try XCTUnwrap(citationRange(text, citation: source(start: 22, end: 34)))
        XCTAssertEqual(NSMaxRange(range), (text as NSString).length)
        XCTAssertEqual((text as NSString).substring(with: range), "Remember Me.")
        XCTAssertNil(citationRange(text, citation: source()))
        XCTAssertNil(codePointRange("🌙", start: 0, end: 2))
    }

    func testChangedQuotationsDoNotReceiveInlineSourceLinks() {
        var citation = source(start: 0, end: 12)
        citation.anchorValid = false
        let rendered = readerAttributedText(text: "Remember Me.", citations: [citation], glossaryTerms: [])
        XCTAssertEqual(String(rendered.characters), "Remember Me.")
        XCTAssertNil(citationRange("Remember Me.", citation: citation))
    }

    func testGlossaryLinksPreserveWholePhraseAndSearchHighlight() {
        let phrase = "god-consciousness"
        let term = GlossaryTerm(
            arabicTerm: "التقوى", meaning: "Mindfulness of Allah", literalTranslation: phrase,
            displayTerm: phrase, alternativeContextMeanings: "", translationStart: 2,
            translationEnd: 2 + phrase.count
        )
        let rendered = readerAttributedText(text: "🌙 \(phrase) (التقوى)", citations: [], glossaryTerms: [term], textSize: 24, searchQuery: phrase)
        let linked = rendered.runs.filter { $0.link?.host == "glossary" }
        XCTAssertEqual(linked.count, 1)
        XCTAssertEqual(String(rendered[linked[0].range].characters), phrase)
        XCTAssertNotNil(linked[0].backgroundColor)
    }

    func testOfflineCachePersistsSourcePopupsAndRemovesWithdrawnCopies() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let cache = ReaderCache(directory: directory)
        let item = source(start: 0, end: 12)
        await cache.write([item], key: "sermon-test")
        let reopened = ReaderCache(directory: directory)
        let restored: [Citation]? = await reopened.read("sermon-test")
        XCTAssertEqual(restored, [item])
        await reopened.remove("sermon-test")
        let missing: [Citation]? = await reopened.read("sermon-test")
        XCTAssertNil(missing)
    }

    func testCacheFallbackDoesNotMaskAuthenticationOrMissingSermons() {
        XCTAssertTrue(isTemporaryConnectionFailure(APIError.http(status: 503, detail: "Offline")))
        XCTAssertFalse(isTemporaryConnectionFailure(APIError.http(status: 401, detail: "Unauthorized")))
        XCTAssertFalse(isTemporaryConnectionFailure(APIError.http(status: 404, detail: "Removed")))
        XCTAssertFalse(isTemporaryConnectionFailure(URLError(.cancelled)))
    }

    private func source(start: Int? = nil, end: Int? = nil) -> Citation {
        Citation(chunkId: "quran:2:152", sourceId: "quran.com:2:152", title: "Al-Baqarah 2:152",
                 authority: "Quran.com", excerpt: "Remember Me.", arabicExcerpt: "فَاذْكُرُونِي",
                 transliteration: "Fadhkuruni", displayReference: "Al-Baqarah 2:152", sourceKind: "quran",
                 url: "https://quran.com/2/152", translationStart: start, translationEnd: end,
                 arabicStart: nil, arabicEnd: nil)
    }
}
