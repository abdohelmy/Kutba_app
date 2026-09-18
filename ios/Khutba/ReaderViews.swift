import SwiftUI

struct MosqueListView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(spacing: 14) {
                    SectionHeading(
                        title: "Find your community",
                        subtitle: "Choose a mosque to read its reviewed Friday khutbas."
                    )
                    if model.readerOffline { OfflineReaderNote() }
                    ForEach(model.mosques) { mosque in
                        Button {
                            model.selectMosque(mosque, language: nil)
                        } label: {
                            HStack(spacing: 14) {
                                Image(systemName: "building.columns.fill")
                                    .font(.title3)
                                    .foregroundStyle(KhutbaTheme.green)
                                    .frame(width: 48, height: 48)
                                    .background(KhutbaTheme.mint, in: Circle())
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(mosque.name)
                                        .font(.title3.bold())
                                        .foregroundStyle(.primary)
                                    Text("\(mosque.city), \(mosque.country)")
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .foregroundStyle(.tertiary)
                            }
                            .khutbaCard()
                        }
                        .buttonStyle(.plain)
                    }
                    if model.mosques.isEmpty {
                        ContentUnavailableView(
                            "No mosques available",
                            systemImage: "building.columns",
                            description: Text("No active mosque profiles are available yet.")
                        )
                        .padding(.top, 30)
                    }
                }
                .padding(18)
            }
            .khutbaBackground()
            .navigationTitle("Choose your mosque")
            .refreshable { await model.refreshReader() }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Exit", systemImage: "rectangle.portrait.and.arrow.right", action: model.logout)
                }
            }
        }
    }
}

struct SermonListView: View {
    @EnvironmentObject private var model: AppModel

    private var sections: SermonDateSections {
        SermonDateSections(sermons: model.sermons)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(spacing: 13) {
                    if model.readerOffline { OfflineReaderNote() }
                    SectionHeading(title: "This week's khutba", subtitle: sections.weekRange)
                    if sections.thisWeek.isEmpty {
                        Text("No khutba has been published for this week yet.")
                            .foregroundStyle(KhutbaTheme.deepGreen)
                            .khutbaCard()
                            .background(KhutbaTheme.mint, in: RoundedRectangle(cornerRadius: 20))
                    }
                    ForEach(sections.thisWeek) { sermon in
                        SermonRow(sermon: sermon) { model.openPublishedSermon(id: sermon.id) }
                    }
                    if !sections.upcoming.isEmpty {
                        SectionHeading(title: "Upcoming khutbas")
                            .padding(.top, 8)
                        ForEach(sections.upcoming) { sermon in
                            SermonRow(sermon: sermon) { model.openPublishedSermon(id: sermon.id) }
                        }
                    }
                    ForEach(sections.archive, id: \.title) { section in
                        SectionHeading(title: section.title)
                            .padding(.top, 8)
                        ForEach(section.sermons) { sermon in
                            SermonRow(sermon: sermon) { model.openPublishedSermon(id: sermon.id) }
                        }
                    }
                }
                .padding(16)
            }
            .khutbaBackground()
            .navigationBarBackButtonHidden()
            .refreshable { await model.refreshReader() }
            .toolbar {
                ScreenHeader(title: model.selectedMosque?.name ?? "Khutbas", backAction: model.back)
            }
        }
    }
}

private struct SermonRow: View {
    let sermon: SermonSummary
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 13) {
                Image(systemName: "doc.text.fill")
                    .foregroundStyle(KhutbaTheme.green)
                    .frame(width: 44, height: 44)
                    .background(KhutbaTheme.mint, in: Circle())
                VStack(alignment: .leading, spacing: 4) {
                    Text(sermon.title)
                        .font(.headline)
                        .foregroundStyle(.primary)
                        .multilineTextAlignment(.leading)
                    Text("\(friendlyDate(sermon.khutbaDate)) · \(sermon.targetLanguage.uppercased())")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .foregroundStyle(.tertiary)
            }
            .khutbaCard()
        }
        .buttonStyle(.plain)
    }
}

struct ReaderSermonView: View {
    @EnvironmentObject private var model: AppModel
    var preview = false
    @State private var selectedCitation: Citation?
    @State private var selectedGlossaryTerm: GlossaryTerm?
    @AppStorage("reader-text-size") private var textSize = 18.0
    @State private var query = ""
    @State private var matchIndex = 0
    @State private var visibleSection: String?

    private var sermon: SermonDetail? { preview ? model.previewSermon : model.selectedSermon }
    private var matches: [String] {
        guard !query.trimmingCharacters(in: .whitespaces).isEmpty else { return [] }
        return sermon?.segments.filter { ($0.translatedText ?? "").localizedCaseInsensitiveContains(query) }.map(\.id) ?? []
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                HStack {
                    TextField("Find in this khutba", text: $query)
                        .textFieldStyle(.roundedBorder)
                    if !query.isEmpty {
                        Text(matches.isEmpty ? "No matches" : "\(min(matchIndex + 1, matches.count))/\(matches.count)")
                            .font(.caption).accessibilityLabel("Matching section")
                        Button("Previous", systemImage: "chevron.up") { moveMatch(-1) }
                            .labelStyle(.iconOnly).disabled(matches.isEmpty)
                        Button("Next", systemImage: "chevron.down") { moveMatch(1) }
                            .labelStyle(.iconOnly).disabled(matches.isEmpty)
                    }
                }.padding(.horizontal, 18).padding(.vertical, 10)
                ScrollView {
                    if let sermon {
                        LazyVStack(alignment: .leading, spacing: 26) {
                            VStack(alignment: .leading, spacing: 14) {
                                Text(sermon.title).font(.title2.bold())
                                Text(friendlyDate(sermon.khutbaDate)).foregroundStyle(.secondary)
                                Text(preview ? "Reader preview · Saved edits" : "Reviewed by your mosque · Saved for offline reading")
                                    .font(.caption).foregroundStyle(KhutbaTheme.green)
                                if model.readerOffline && !preview { OfflineReaderNote() }
                                HStack {
                                    Text("Aa").font(.system(size: 16))
                                    Slider(value: $textSize, in: 16...28, step: 2)
                                        .accessibilityLabel("Reading text size")
                                    Text("Aa").font(.system(size: 26))
                                }
                                if !preview {
                                    Button(model.readerOffline ? "PDF download needs internet" : "Download PDF", systemImage: "arrow.down.doc") {
                                        model.downloadPublishedSermon()
                                    }.buttonStyle(.bordered).disabled(model.readerOffline)
                                }
                                Text("Tap a highlighted term or source reference to see its explanation.")
                                    .font(.caption).foregroundStyle(.secondary)
                                Divider()
                            }
                            .id("reader-header")
                            ForEach(sermon.segments) { segment in
                                VStack(alignment: .leading, spacing: 12) {
                                    Text("SECTION \(segment.ordinal + 1)")
                                        .font(.caption2.bold()).foregroundStyle(KhutbaTheme.green)
                                    ReaderSegmentView(
                                        segment: segment, textSize: textSize, searchQuery: query,
                                        onCitation: { selectedCitation = $0 },
                                        onGlossary: { selectedGlossaryTerm = $0 }
                                    )
                                }.id(segment.id)
                            }
                        }
                        .scrollTargetLayout()
                        .padding(22)
                    }
                }
                .scrollPosition(id: $visibleSection, anchor: .top)
            }
            .khutbaBackground()
            .navigationBarBackButtonHidden()
            .toolbar {
                ScreenHeader(title: preview ? "Reader preview" : "Khutba", backAction: model.back)
            }
        }
        .onAppear {
            if !preview, let sermon {
                visibleSection = UserDefaults.standard.string(forKey: "reader-section-\(sermon.id)")
            }
        }
        .onChange(of: visibleSection) { _, value in
            if !preview, query.isEmpty, let sermon, let value {
                UserDefaults.standard.set(value, forKey: "reader-section-\(sermon.id)")
            }
        }
        .onChange(of: query) { _, _ in
            matchIndex = 0
            if let first = matches.first { visibleSection = first }
        }
        .sheet(item: $selectedCitation) { citation in
            CitationDetailView(citation: citation)
                .presentationDetents([.medium, .large])
        }
        .sheet(item: $selectedGlossaryTerm) { term in
            GlossaryDetailView(term: term)
                .presentationDetents([.medium, .large])
        }
    }

    private func moveMatch(_ direction: Int) {
        guard !matches.isEmpty else { return }
        matchIndex = (matchIndex + matches.count + direction) % matches.count
        visibleSection = matches[matchIndex]
    }
}

private struct OfflineReaderNote: View {
    var body: some View {
        Label("Offline · Showing saved content. Pull to refresh when connected.", systemImage: "wifi.slash")
            .font(.caption).foregroundStyle(.secondary)
    }
}

private struct ReaderSegmentView: View {
    let segment: SermonSegment
    let textSize: Double
    let searchQuery: String
    let onCitation: (Citation) -> Void
    let onGlossary: (GlossaryTerm) -> Void

    private var canonicalCitations: [Citation] {
        segment.citations.filter { $0.sourceKind == "quran" || $0.sourceKind == "hadith" }
    }

    var body: some View {
        let terms = segment.glossaryTerms ?? []
        VStack(alignment: .leading, spacing: 12) {
            Text(readerAttributedText(
            text: segment.translatedText ?? "",
            citations: canonicalCitations,
            glossaryTerms: terms,
            textSize: textSize, searchQuery: searchQuery
        ))
        .font(.system(size: textSize)).lineSpacing(textSize * 0.35)
        .frame(maxWidth: .infinity, alignment: .leading)
        .environment(\.openURL, OpenURLAction { url in
            if url.scheme == "khutba", url.host == "citation",
               let index = Int(url.path.dropFirst()), canonicalCitations.indices.contains(index) {
                onCitation(canonicalCitations[index])
                return .handled
            }
            if url.scheme == "khutba", url.host == "glossary",
               let index = Int(url.path.dropFirst()), terms.indices.contains(index) {
                onGlossary(terms[index])
                return .handled
            }
            return .systemAction
        })
            ForEach(canonicalCitations.filter {
                citationRange(sanitizedReaderText(segment.translatedText ?? ""), citation: $0) == nil
            }) { citation in
                Button("\(citation.anchorValid == false ? "Quotation needs review" : "Section source"): \(citationReference(citation))") {
                    onCitation(citation)
                }.font(.caption)
            }
        }
    }
}

struct CitationDetailView: View {
    @Environment(\.dismiss) private var dismiss
    let citation: Citation

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 15) {
                    Text("Original Arabic")
                        .font(.headline)
                    if let arabic = citation.arabicExcerpt, !arabic.isEmpty {
                        Text(arabic)
                            .font(.title3)
                            .multilineTextAlignment(.trailing)
                            .frame(maxWidth: .infinity, alignment: .trailing)
                            .environment(\.layoutDirection, .rightToLeft)
                        if let transliteration = citation.transliteration, !transliteration.isEmpty {
                            Text(transliteration)
                                .foregroundStyle(.secondary)
                        } else {
                            Text("Latin transliteration is unavailable for this older translation.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    } else {
                        Text("Arabic source text is unavailable for this older translation.")
                            .foregroundStyle(.secondary)
                    }
                    Divider()
                    Text("Source")
                        .font(.headline)
                    Text(citation.title)
                        .font(.title3.bold())
                    Text(citation.authority)
                        .foregroundStyle(KhutbaTheme.green)
                    if let rawURL = citation.url, let url = URL(string: rawURL) {
                        Link(destination: url) {
                            Label("Open source", systemImage: "arrow.up.right.square")
                        }
                        .buttonStyle(.borderedProminent)
                    }
                }
                .padding(20)
            }
            .navigationTitle(citation.sourceKind == "quran" ? "Qur’an citation" : "Hadith citation")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Close") { dismiss() }
                }
            }
        }
    }
}

struct GlossaryDetailView: View {
    @Environment(\.dismiss) private var dismiss
    let term: GlossaryTerm

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text(term.arabicTerm)
                        .font(.title2)
                        .multilineTextAlignment(.trailing)
                        .frame(maxWidth: .infinity, alignment: .trailing)
                        .environment(\.layoutDirection, .rightToLeft)
                    Divider()
                    Text("Meaning")
                        .font(.headline)
                    Text(term.meaning)
                    if !term.literalTranslation.isEmpty {
                        Text("Literal wording: \(term.literalTranslation)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if !term.alternativeContextMeanings.isEmpty {
                        Divider()
                        Text("Other context")
                            .font(.headline)
                        Text(term.alternativeContextMeanings)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(20)
            }
            .navigationTitle(term.displayTerm)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Close") { dismiss() }
                }
            }
        }
    }
}

private struct TextRange {
    let start: Int
    let end: Int
    let glossaryIndex: Int
}

func citationRange(_ text: String, citation: Citation) -> NSRange? {
    guard citation.anchorValid != false, !citation.excerpt.isEmpty else { return nil }
    let source = text as NSString
    if let range = codePointRange(text, start: citation.translationStart, end: citation.translationEnd),
       source.substring(with: range).caseInsensitiveCompare(citation.excerpt) == .orderedSame {
        return range
    }
    let found = source.range(of: citation.excerpt, options: .caseInsensitive)
    guard found.location != NSNotFound else { return nil }
    let rest = NSRange(location: found.location + 1, length: source.length - found.location - 1)
    guard source.range(of: citation.excerpt, options: .caseInsensitive, range: rest).location == NSNotFound else { return nil }
    return found
}

func readerAttributedText(
    text: String,
    citations: [Citation],
    glossaryTerms: [GlossaryTerm],
    textSize: Double = 18,
    searchQuery: String = ""
) -> AttributedString {
    let cleaned = sanitizedReaderText(text)
    let source = cleaned as NSString
    var occupiedEnd = 0
    let glossaryRanges = glossaryTerms.enumerated().compactMap { index, term -> TextRange? in
        let stored: NSRange? = {
            guard let range = codePointRange(cleaned, start: term.translationStart, end: term.translationEnd),
                  source.substring(with: range)
                    .caseInsensitiveCompare(term.displayTerm) == .orderedSame else { return nil }
            return range
        }()
        let range = stored ?? source.range(of: term.displayTerm, options: .caseInsensitive)
        guard range.location != NSNotFound else { return nil }
        return TextRange(start: range.location, end: NSMaxRange(range), glossaryIndex: index)
    }
    .sorted { $0.start == $1.start ? $0.end > $1.end : $0.start < $1.start }
    .filter { range in
        guard range.start >= occupiedEnd else { return false }
        occupiedEnd = range.end
        return true
    }

    let citationPositions: [(position: Int, index: Int)] = citations.enumerated().compactMap { index, citation in
        guard let range = citationRange(cleaned, citation: citation) else { return nil }
        var position = NSMaxRange(range)
        if let covering = glossaryRanges.first(where: { position > $0.start && position < $0.end }) {
            position = covering.end
        }
        return (position, index)
    }

    let citationsByPosition = Dictionary(grouping: citationPositions, by: \.position)
    let glossaryByStart = Dictionary(uniqueKeysWithValues: glossaryRanges.map { ($0.start, $0) })
    let eventPositions = Set(glossaryRanges.map(\.start) + citationPositions.map(\.position) + [source.length])
    var result = AttributedString()
    var cursor = 0

    func sourceLinks(at position: Int) -> AttributedString {
        var links = AttributedString()
        for item in citationsByPosition[position] ?? [] {
            var link = AttributedString(" (\(citationReference(citations[item.index]))) ↗")
            link.link = URL(string: "khutba://citation/\(item.index)")
            link.foregroundColor = KhutbaTheme.green
            link.font = .caption.bold()
            links.append(link)
        }
        return links
    }

    while cursor < source.length {
        result.append(sourceLinks(at: cursor))
        if let glossary = glossaryByStart[cursor] {
            var linked = AttributedString(
                source.substring(with: NSRange(location: glossary.start, length: glossary.end - glossary.start))
            )
            linked.link = URL(string: "khutba://glossary/\(glossary.glossaryIndex)")
            linked.foregroundColor = KhutbaTheme.terracotta
            linked.backgroundColor = KhutbaTheme.gold.opacity(0.18)
            linked.font = .system(size: textSize, weight: .semibold)
            result.append(linked)
            cursor = glossary.end
        } else {
            let next = eventPositions.filter { $0 > cursor }.min() ?? source.length
            result.append(AttributedString(source.substring(with: NSRange(location: cursor, length: next - cursor))))
            cursor = next
        }
    }
    result.append(sourceLinks(at: source.length))
    if !searchQuery.trimmingCharacters(in: .whitespaces).isEmpty {
        let plain = String(result.characters)
        var remaining = plain.startIndex..<plain.endIndex
        while let found = plain.range(of: searchQuery, options: .caseInsensitive, range: remaining) {
            if let lower = AttributedString.Index(found.lowerBound, within: result),
               let upper = AttributedString.Index(found.upperBound, within: result) {
                result[lower..<upper].backgroundColor = KhutbaTheme.gold.opacity(0.45)
            }
            remaining = found.upperBound..<plain.endIndex
        }
    }
    return result
}
