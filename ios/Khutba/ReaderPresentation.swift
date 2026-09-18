import Foundation

// Cache only public reader responses, never admin drafts or credentials.
actor ReaderCache {
    private let directory: URL

    init(directory: URL? = nil) {
        self.directory = directory ?? FileManager.default.urls(
            for: .applicationSupportDirectory, in: .userDomainMask
        )[0].appendingPathComponent("Reader-v1", isDirectory: true)
    }

    func read<T: Decodable>(_ key: String, as type: T.Type = T.self) -> T? {
        guard let data = try? Data(contentsOf: file(key)) else { return nil }
        return try? JSONDecoder().decode(type, from: data)
    }

    func write<T: Encodable>(_ value: T, key: String) {
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try JSONEncoder().encode(value).write(to: file(key), options: .atomic)
        } catch { /* Reading online still works if local storage is full. */ }
    }

    func remove(_ key: String) { try? FileManager.default.removeItem(at: file(key)) }

    private func file(_ key: String) -> URL { directory.appendingPathComponent(key + ".json") }
}

func isTemporaryConnectionFailure(_ error: Error) -> Bool {
    if case let APIError.http(status, _) = error { return (500...599).contains(status) }
    if let error = error as? URLError { return error.code != .cancelled }
    return false
}

// API offsets are Python Unicode code points, not UTF-16 or Swift graphemes.
func codePointRange(_ text: String, start: Int?, end: Int?) -> NSRange? {
    guard let start, let end, start >= 0, end > start, end <= text.unicodeScalars.count else { return nil }
    let lower = text.unicodeScalars.index(text.unicodeScalars.startIndex, offsetBy: start)
    let upper = text.unicodeScalars.index(text.unicodeScalars.startIndex, offsetBy: end)
    return NSRange(lower..<upper, in: text)
}

enum DateFormatters {
    static let apiDate: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()

    static let fullDate: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .full
        return formatter
    }()

    static let monthYear: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "LLLL yyyy"
        return formatter
    }()

    static let shortDate: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "d MMM"
        return formatter
    }()
}

struct SermonDateSections {
    struct ArchiveSection {
        let title: String
        let sermons: [SermonSummary]
    }

    let thisWeek: [SermonSummary]
    let upcoming: [SermonSummary]
    let archive: [ArchiveSection]
    let weekRange: String

    init(sermons: [SermonSummary], now: Date = Date(), calendar suppliedCalendar: Calendar = .current) {
        var calendar = suppliedCalendar
        calendar.firstWeekday = 2
        calendar.minimumDaysInFirstWeek = 4
        let start = calendar.dateInterval(of: .weekOfYear, for: now)?.start ?? calendar.startOfDay(for: now)
        let end = calendar.date(byAdding: .day, value: 7, to: start) ?? start
        let dated = sermons.compactMap { sermon -> (Date, SermonSummary)? in
            guard let date = DateFormatters.apiDate.date(from: sermon.khutbaDate) else { return nil }
            return (date, sermon)
        }
        thisWeek = dated
            .filter { $0.0 >= start && $0.0 < end }
            .sorted { $0.0 > $1.0 }
            .map(\.1)
        upcoming = dated
            .filter { $0.0 >= end }
            .sorted { $0.0 < $1.0 }
            .map(\.1)

        let older = dated.filter { $0.0 < start }.sorted { $0.0 > $1.0 }
        let grouped = Dictionary(grouping: older) { pair in
            calendar.dateComponents([.year, .month], from: pair.0)
        }
        archive = grouped.compactMap { components, values -> (Date, ArchiveSection)? in
            guard let month = calendar.date(from: components) else { return nil }
            return (
                month,
                ArchiveSection(
                    title: DateFormatters.monthYear.string(from: month),
                    sermons: values.sorted { $0.0 > $1.0 }.map(\.1)
                )
            )
        }
        .sorted { $0.0 > $1.0 }
        .map(\.1)

        let displayedEnd = calendar.date(byAdding: .day, value: 6, to: start) ?? end
        weekRange = "\(DateFormatters.shortDate.string(from: start)) – \(DateFormatters.shortDate.string(from: displayedEnd))"
    }
}

func friendlyDate(_ value: String) -> String {
    guard let date = DateFormatters.apiDate.date(from: value) else { return value }
    return DateFormatters.fullDate.string(from: date)
}

func sanitizedReaderText(_ value: String) -> String {
    value
        .replacingOccurrences(of: #"\s*\[S:[^\]\r\n]+\]"#, with: "", options: .regularExpression)
        .replacingOccurrences(of: #"[ \t]+([,.;:!?])"#, with: "$1", options: .regularExpression)
        .replacingOccurrences(of: #"[ \t]{2,}"#, with: " ", options: .regularExpression)
        .trimmingCharacters(in: .whitespacesAndNewlines)
}

func citationReference(_ citation: Citation) -> String {
    if let display = citation.displayReference, !display.isEmpty { return display }
    if citation.sourceKind == "quran",
       let separator = citation.sourceId.range(of: "quran.com:") {
        let key = String(citation.sourceId[separator.upperBound...])
        if !key.isEmpty { return "Qur’an \(key)" }
    }
    let title = citation.title.components(separatedBy: " —").first ?? "Source"
    return title.isEmpty ? "Source" : title
}
