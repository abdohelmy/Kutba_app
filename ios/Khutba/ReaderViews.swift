import SwiftUI
import UIKit

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
    @State private var language = "all"

    private var sections: SermonDateSections {
        SermonDateSections(sermons: model.sermons.filter { language == "all" || $0.targetLanguage == language })
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(spacing: 13) {
                    Picker("Translation language", selection: $language) {
                        Text("All").tag("all")
                        Text("English").tag("en")
                        Text("Dansk").tag("da")
                    }.pickerStyle(.segmented)
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
    @State private var live: LiveState?
    @State private var followLive = false
    @State private var autoFollow = true

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
                                if !preview, !model.readerOffline, live?.active == true {
                                    Text(live?.status == "matched" ? "Following the imam · approximate position" : live?.status == "paused" ? "Live session paused" : "Waiting for a clear match")
                                        .font(.subheadline)
                                    HStack {
                                        Button(followLive ? "Stop following" : "Follow imam") { followLive.toggle(); autoFollow = true }
                                        if followLive && !autoFollow { Button("Return to live") { autoFollow = true } }
                                    }.buttonStyle(.bordered)
                                }
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
                                        liveHighlights: followLive && live?.active == true ? (live?.highlights.filter { $0.segmentId == segment.id } ?? []) : [],
                                        autoFollow: followLive && autoFollow,
                                        onCitation: { selectedCitation = $0 },
                                        onGlossary: { term in
                                            var current = term
                                            current.popupPhrase = glossaryHeading(segment.translatedText ?? "", term: term, language: sermon.targetLanguage)
                                            current.popupLanguage = sermon.targetLanguage
                                            selectedGlossaryTerm = current
                                        }
                                    )
                                }.id(segment.id)
                            }
                        }
                        .scrollTargetLayout()
                        .padding(22)
                    }
                }
                .scrollPosition(id: $visibleSection, anchor: .top)
                .simultaneousGesture(DragGesture().onChanged { _ in if followLive { autoFollow = false } })
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
        .task(id: "\(sermon?.id ?? "")-\(model.readerOffline)-\(preview)") {
            guard !preview, !model.readerOffline, let sermon else { return }
            while !Task.isCancelled {
                do { live = try await APIClient.shared.liveState(sermonID: sermon.id) }
                catch { if Task.isCancelled { return }; live?.status = "worker_offline" }
                try? await Task.sleep(for: .seconds(followLive ? 2 : 6))
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
        .onChange(of: live?.highlights ?? []) { _, ranges in
            if followLive && autoFollow, let target=ranges.first?.segmentId, target != visibleSection {
                withAnimation { visibleSection=target }
            }
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
    var liveHighlights: [LiveHighlight] = []
    var autoFollow: Bool = false
    let onCitation: (Citation) -> Void
    let onGlossary: (GlossaryTerm) -> Void

    private var canonicalCitations: [Citation] {
        segment.citations.filter { $0.sourceKind == "quran" || $0.sourceKind == "hadith" }
    }

    var body: some View {
        let terms = segment.glossaryTerms ?? []
        VStack(alignment: .leading, spacing: 12) {
            LiveReaderText(attributed: readerAttributedText(
            text: segment.translatedText ?? "",
            citations: canonicalCitations,
            glossaryTerms: terms,
            textSize: textSize, searchQuery: searchQuery, liveHighlights: liveHighlights
        ), textSize: textSize, liveActive: !liveHighlights.isEmpty, autoFollow: autoFollow,
            scrollKey: liveHighlights.map { "\($0.start)-\($0.end)" }.joined(separator: ",") + "-\(autoFollow)") { url in
            if url.scheme == "khutba", url.host == "citation",
               let index = Int(url.path.dropFirst()), canonicalCitations.indices.contains(index) {
                onCitation(canonicalCitations[index])
                return
            }
            if url.scheme == "khutba", url.host == "glossary",
               let index = Int(url.path.dropFirst()), terms.indices.contains(index) {
                onGlossary(terms[index])
                return
            }
        }
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

private struct LiveReaderText: View {
    let attributed: AttributedString
    let textSize: Double
    let liveActive: Bool
    let autoFollow: Bool
    let scrollKey: String
    let onURL: (URL) -> Void
    var body: some View {
        if liveActive {
            LiveUIText(attributed: attributed, textSize: textSize, autoFollow: autoFollow,
                       scrollKey: scrollKey, onURL: onURL)
        } else {
            Text(attributed).font(.system(size:textSize)).lineSpacing(textSize*0.35)
                .frame(maxWidth:.infinity,alignment:.leading)
                .environment(\.openURL,OpenURLAction { url in onURL(url); return .handled })
        }
    }
}

private struct LiveUIText: UIViewRepresentable {
    let attributed: AttributedString
    let textSize: Double
    let autoFollow: Bool
    let scrollKey: String
    let onURL: (URL) -> Void
    class Coordinator: NSObject, UITextViewDelegate {
        var parent: LiveUIText
        var lastScrollKey = ""
        init(_ parent:LiveUIText){self.parent=parent}
        func textView(_ textView:UITextView,shouldInteractWith URL:URL,in characterRange:NSRange,interaction:UITextItemInteraction)->Bool {
            parent.onURL(URL);return false
        }
    }
    func makeCoordinator()->Coordinator { Coordinator(self) }
    func makeUIView(context:Context)->UITextView {
        let view=UITextView();view.isEditable=false;view.isScrollEnabled=false
        view.backgroundColor = .clear;view.textContainerInset = .zero
        view.textContainer.lineFragmentPadding=0;view.delegate=context.coordinator
        view.linkTextAttributes=[:];view.adjustsFontForContentSizeCategory=true
        return view
    }
    func sizeThatFits(_ proposal:ProposedViewSize,uiView:UITextView,context:Context)->CGSize? {
        guard let width=proposal.width else{return nil}
        return uiView.sizeThatFits(CGSize(width:width,height:CGFloat.greatestFiniteMagnitude))
    }
    func updateUIView(_ view:UITextView,context:Context) {
        context.coordinator.parent=self
        let value=NSMutableAttributedString(attributedString:NSAttributedString(attributed))
        let entire=NSRange(location:0,length:value.length)
        value.enumerateAttribute(.font,in:entire) { font,range,_ in
            if font == nil {value.addAttribute(.font,value:UIFont.systemFont(ofSize:textSize),range:range)}
        }
        let paragraph=NSMutableParagraphStyle();paragraph.lineSpacing=textSize*0.35
        value.addAttribute(.paragraphStyle,value:paragraph,range:entire)
        if !view.attributedText.isEqual(to:value){view.attributedText=value}
        guard autoFollow,context.coordinator.lastScrollKey != scrollKey else{return}
        context.coordinator.lastScrollKey=scrollKey
        DispatchQueue.main.async {
            var range:NSRange?
            value.enumerateAttribute(.backgroundColor,in:entire) { color,span,stop in
                if let color=color as? UIColor,abs(color.cgColor.alpha-0.35)<0.01 {
                    range=span;stop.pointee=true
                }
            }
            guard let range else{return}
            var container=view.superview
            while let parent=container,!(parent is UIScrollView){container=parent.superview}
            guard let scroll=container as? UIScrollView else{return}
            view.layoutManager.ensureLayout(for:view.textContainer)
            let glyph=view.layoutManager.glyphRange(forCharacterRange:range,actualCharacterRange:nil)
            let rect=view.layoutManager.boundingRect(forGlyphRange:glyph,in:view.textContainer)
            let target=view.convert(rect,to:scroll).insetBy(dx:0,dy:-50)
            scroll.scrollRectToVisible(target,animated:!UIAccessibility.isReduceMotionEnabled)
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

func glossaryHeading(_ text: String, term: GlossaryTerm, language: String) -> String {
    let neutral = language == "da" ? "Ordforklaring" : "Word meaning"
    guard let start = term.translationStart, start >= 0, start <= text.unicodeScalars.count else { return neutral }
    let preceding = String(String.UnicodeScalarView(text.unicodeScalars.prefix(start)))
        .replacingOccurrences(of: "[(（]\\s*$", with: "", options: .regularExpression)
        .trimmingCharacters(in: .whitespacesAndNewlines)
    let candidates = [term.popupLanguage == nil || term.popupLanguage == "" || term.popupLanguage == language ? term.popupPhrase : nil,
                      language == "da" ? term.localizedPhrase : term.englishPhrase]
    for candidate in candidates.compactMap({ $0 }) where !candidate.isEmpty {
        let escaped = candidate.split(whereSeparator: { $0.isWhitespace })
            .map { NSRegularExpression.escapedPattern(for: String($0)) }.joined(separator: "\\s+")
        if let range = preceding.range(of: "(?<![\\p{L}\\p{N}_])\(escaped)\\s*$", options: [.regularExpression, .caseInsensitive]) {
            return String(preceding[range]).trimmingCharacters(in: .whitespacesAndNewlines)
        }
    }
    let last = preceding.components(separatedBy: CharacterSet(charactersIn: "\r\n.!?;:…,)"))
        .last?.trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(CharacterSet(charactersIn: "‘’\"“”"))) ?? ""
    return last.isEmpty ? neutral : last
}

struct GlossaryDetailView: View {
    @Environment(\.dismiss) private var dismiss
    let term: GlossaryTerm

    private var englishTitle: String {
        if let phrase = term.popupPhrase, !phrase.isEmpty { return phrase }
        return term.popupLanguage == "da" ? "Ordforklaring" : "Word meaning"
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text(englishTitle)
                        .font(.title2.bold())
                    Text(term.arabicTerm)
                        .font(.title2)
                        .multilineTextAlignment(.trailing)
                        .frame(maxWidth: .infinity, alignment: .trailing)
                        .environment(\.layoutDirection, .rightToLeft)
                    if let transliteration = term.transliteration, !transliteration.isEmpty {
                        Text(transliteration)
                        Text("Letter transliteration · vowels may be incomplete")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Divider()
                    Text("Meaning")
                        .font(.headline)
                    Text(term.meaning)
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
            .navigationTitle("Definition")
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

func glossaryArabicRange(text: String, term: GlossaryTerm) -> NSRange? {
    let source = text as NSString
    let stored = codePointRange(text, start: term.translationStart, end: term.translationEnd)
    if let stored, source.substring(with: stored) == term.arabicTerm { return stored }
    guard !term.arabicTerm.isEmpty,
          let pattern = try? NSRegularExpression(pattern:
            "\\(\\s*(" + NSRegularExpression.escapedPattern(for: term.arabicTerm) + ")\\s*\\)")
    else { return nil }
    let notes = pattern.matches(in: text, range: NSRange(location: 0, length: source.length))
    if let stored, let note = notes.first(where: { $0.range.location >= NSMaxRange(stored) }),
       source.substring(with: NSRange(location: NSMaxRange(stored),
           length: note.range.location - NSMaxRange(stored)))
            .trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        return note.range(at: 1)
    }
    return notes.count == 1 ? notes[0].range(at: 1) : nil
}

func readerAttributedText(
    text: String,
    citations: [Citation],
    glossaryTerms: [GlossaryTerm],
    textSize: Double = 18,
    searchQuery: String = "",
    liveHighlights: [LiveHighlight] = []
) -> AttributedString {
    let cleaned = sanitizedReaderText(text)
    let source = cleaned as NSString
    let raw = text as NSString
    let liveRanges = liveHighlights.compactMap { value -> NSRange? in
        guard value.start >= 0, value.end > value.start, value.end <= raw.length,
              raw.substring(with: NSRange(location:value.start,length:value.end-value.start)) == value.excerpt else { return nil }
        func offset(_ position:Int) -> Int {
            // Add a sentinel so sanitization preserves spaces at the end of the prefix.
            let prefix = raw.substring(to:position)
            return max(0, (sanitizedReaderText(prefix + "§") as NSString).length - 1)
        }
        let a = min(source.length,offset(value.start)), b = min(source.length,offset(value.end))
        return b > a ? NSRange(location:a,length:b-a) : nil
    }
    var occupiedEnd = 0
    let glossaryRanges = glossaryTerms.enumerated().compactMap { index, term -> TextRange? in
        guard let range = glossaryArabicRange(text: cleaned, term: term) else { return nil }
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
    func sourceText(_ start: Int, _ end: Int) -> AttributedString {
        var value = AttributedString(source.substring(with:NSRange(location:start,length:end-start)))
        let plain = String(value.characters)
        for range in liveRanges {
            let a = max(start,range.location)-start, b = min(end,NSMaxRange(range))-start
            if a < b, let swift = Range(NSRange(location:a,length:b-a), in:plain),
               let lower = AttributedString.Index(swift.lowerBound,within:value),
               let upper = AttributedString.Index(swift.upperBound,within:value) {
                value[lower..<upper].backgroundColor = KhutbaTheme.gold.opacity(0.35)
                value[lower..<upper].uiKit.backgroundColor = UIColor(KhutbaTheme.gold.opacity(0.35))
            }
        }
        return value
    }

    func sourceLinks(at position: Int) -> AttributedString {
        var links = AttributedString()
        for item in citationsByPosition[position] ?? [] {
            var link = AttributedString(" (\(citationReference(citations[item.index]))) ↗")
            link.link = URL(string: "khutba://citation/\(item.index)")
            link.foregroundColor = KhutbaTheme.green
            link.uiKit.foregroundColor = UIColor(KhutbaTheme.green)
            link.font = .caption.bold()
            links.append(link)
        }
        return links
    }

    while cursor < source.length {
        result.append(sourceLinks(at: cursor))
        if let glossary = glossaryByStart[cursor] {
            var linked = sourceText(glossary.start,glossary.end)
            linked.link = URL(string: "khutba://glossary/\(glossary.glossaryIndex)")
            linked.foregroundColor = KhutbaTheme.terracotta
            linked.uiKit.foregroundColor = UIColor(KhutbaTheme.terracotta)
            linked.backgroundColor = KhutbaTheme.gold.opacity(0.18)
            linked.font = .system(size: textSize, weight: .semibold)
            result.append(linked)
            cursor = glossary.end
        } else {
            let next = eventPositions.filter { $0 > cursor }.min() ?? source.length
            result.append(sourceText(cursor,next))
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
                result[lower..<upper].uiKit.backgroundColor = UIColor(KhutbaTheme.gold.opacity(0.45))
            }
            remaining = found.upperBound..<plain.endIndex
        }
    }
    return result
}
