import SwiftUI
import UniformTypeIdentifiers

struct AdminHomeView: View {
    @EnvironmentObject private var model: AppModel
    @State private var sermonTitle = ""
    @State private var sermonDate = Self.upcomingFriday()
    @State private var showDocumentPicker = false
    @State private var pendingDeletion: SermonSummary?
    @State private var needsAttention = false

    private var docxType: UTType {
        UTType(filenameExtension: "docx") ?? .data
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(spacing: 16) {
                    VStack(alignment: .leading, spacing: 14) {
                        Text("Your mosque workspace")
                            .font(.title3.bold())
                        Text("Documents are converted to text on your API before any translation provider is called.")
                            .foregroundStyle(.secondary)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("\(model.sermons.count)")
                                .font(.title2.bold())
                                .foregroundStyle(KhutbaTheme.green)
                            Text("Khutbas")
                                .font(.caption)
                        }
                        .padding(14)
                        .background(.background.opacity(0.75), in: RoundedRectangle(cornerRadius: 14))
                    }
                    .padding(20)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(KhutbaTheme.mint.opacity(0.7), in: RoundedRectangle(cornerRadius: 20))

                    SectionHeading(title: "Khutbas", subtitle: "Upload, translate, review, then publish")

                    VStack(alignment: .leading, spacing: 12) {
                        Text("Upload Arabic khutba")
                            .font(.headline)
                        Text("PDF and DOCX are supported. Only extracted Arabic text is sent for translation.")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                        TextField("Khutba title (optional)", text: $sermonTitle)
                            .textFieldStyle(.roundedBorder)
                        Text("Leave the title empty and it will be inferred from the khutba.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        DatePicker("Friday date", selection: $sermonDate, displayedComponents: .date)
                            .datePickerStyle(.compact)
                        Label("Translation output: English", systemImage: "character.book.closed")
                            .font(.subheadline.bold())
                            .foregroundStyle(KhutbaTheme.deepGreen)
                            .padding(13)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(KhutbaTheme.mint.opacity(0.6), in: RoundedRectangle(cornerRadius: 12))
                        Button {
                            showDocumentPicker = true
                        } label: {
                            Label("Choose PDF or DOCX khutba", systemImage: "doc.badge.plus")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.large)
                    }
                    .khutbaCard()

                    Toggle("Needs attention only", isOn: $needsAttention)
                    ForEach(model.sermons.filter {
                        !needsAttention || [SermonStatus.sourceReviewRequired, SermonStatus.draft, SermonStatus.failed, SermonStatus.reviewRequired].contains($0.status)
                    }) { sermon in
                        AdminSermonRow(
                            sermon: sermon,
                            onOpen: { model.openAdminSermon(id: sermon.id) },
                            onVisibilityChange: {
                                model.setSermonHidden(
                                    id: sermon.id,
                                    hidden: sermon.status == SermonStatus.published
                                )
                            },
                            onDelete: { pendingDeletion = sermon }
                        )
                    }
                }
                .padding(18)
            }
            .khutbaBackground()
            .navigationTitle(model.adminMosque?.name ?? "Mosque administration")
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    if model.adminMosque != nil {
                        Button("Settings", systemImage: "gearshape", action: model.openAdminSettings)
                    }
                    Button("Sign out", systemImage: "rectangle.portrait.and.arrow.right", action: model.logout)
                }
            }
        }
        .fileImporter(
            isPresented: $showDocumentPicker,
            allowedContentTypes: [.pdf, docxType],
            allowsMultipleSelection: false
        ) { result in
            switch result {
            case let .success(urls):
                if let url = urls.first {
                    model.uploadSermon(fileURL: url, title: sermonTitle, date: sermonDate)
                }
            case let .failure(error):
                model.errorMessage = error.localizedDescription
            }
        }
        .alert("Remove khutba?", isPresented: Binding(
            get: { pendingDeletion != nil },
            set: { if !$0 { pendingDeletion = nil } }
        )) {
            Button("Cancel", role: .cancel) { pendingDeletion = nil }
            Button("Remove", role: .destructive) {
                if let sermon = pendingDeletion { model.deleteSermon(id: sermon.id) }
                pendingDeletion = nil
            }
        } message: {
            Text("\(pendingDeletion?.title ?? "This khutba") and its translation will be permanently removed.")
        }
    }

    private static func upcomingFriday() -> Date {
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: Date())
        let weekday = calendar.component(.weekday, from: today)
        let daysUntilFriday = (6 - weekday + 7) % 7
        return calendar.date(byAdding: .day, value: daysUntilFriday, to: today) ?? today
    }
}

private struct AdminSermonRow: View {
    let sermon: SermonSummary
    let onOpen: () -> Void
    let onVisibilityChange: () -> Void
    let onDelete: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            Button(action: onOpen) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 7) {
                        Text(sermon.title)
                            .font(.headline)
                            .foregroundStyle(.primary)
                            .multilineTextAlignment(.leading)
                        HStack {
                            Text(sermon.khutbaDate)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            StatusPill(status: sermon.status)
                        }
                    }
                    Spacer()
                    Image(systemName: "chevron.right")
                        .foregroundStyle(.tertiary)
                }
                .padding(16)
            }
            .buttonStyle(.plain)
            Divider()
            HStack {
                Spacer()
                if sermon.status == SermonStatus.published || sermon.status == SermonStatus.hidden {
                    Button(
                        sermon.status == SermonStatus.hidden ? "Show" : "Hide",
                        systemImage: sermon.status == SermonStatus.hidden ? "eye" : "eye.slash",
                        action: onVisibilityChange
                    )
                }
                Button("Remove", systemImage: "trash", role: .destructive, action: onDelete)
            }
            .font(.subheadline)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
        }
        .background(KhutbaTheme.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 20))
    }
}

struct AdminSettingsView: View {
    @EnvironmentObject private var model: AppModel
    @State private var mosqueName = ""
    @State private var currentPassword = ""
    @State private var newPassword = ""
    @State private var confirmPassword = ""
    @State private var glossaryEditor: GlossaryEditorState?
    @State private var pendingGlossaryDeletion: MosqueGlossaryTerm?

    private var trimmedMosqueName: String {
        mosqueName.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var canSaveName: Bool {
        trimmedMosqueName.count >= 2 && trimmedMosqueName != model.adminMosque?.name
    }

    private var canChangePassword: Bool {
        !currentPassword.isEmpty && newPassword.count >= 6 && newPassword == confirmPassword
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(spacing: 18) {
                    SectionHeading(
                        title: "Mosque profile",
                        subtitle: "This name is shown to readers when they choose a mosque."
                    )
                    VStack(alignment: .leading, spacing: 13) {
                        TextField("Mosque name", text: $mosqueName)
                            .textFieldStyle(.roundedBorder)
                        if let mosque = model.adminMosque {
                            Text("\(mosque.city), \(mosque.country)")
                                .foregroundStyle(.secondary)
                        }
                        Button("Save mosque name") { model.updateMosqueName(trimmedMosqueName) }
                            .buttonStyle(.borderedProminent)
                            .controlSize(.large)
                            .frame(maxWidth: .infinity)
                            .disabled(!canSaveName)
                    }
                    .khutbaCard()

                    SectionHeading(
                        title: "Mosque glossary",
                        subtitle: "Your entries override the built-in glossary for this mosque's future translations."
                    )
                    Button {
                        glossaryEditor = GlossaryEditorState(term: nil)
                    } label: {
                        Label("Add glossary term", systemImage: "plus")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)

                    if model.adminGlossary.isEmpty {
                        Text("No mosque-specific terms yet. The verified built-in glossary is still active.")
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    ForEach(model.adminGlossary) { term in
                        HStack(spacing: 10) {
                            VStack(alignment: .leading, spacing: 5) {
                                Text(term.arabicTerm)
                                    .font(.title3)
                                    .frame(maxWidth: .infinity, alignment: .trailing)
                                    .environment(\.layoutDirection, .rightToLeft)
                                Text(term.literalTranslation)
                                    .font(.headline)
                                Text(term.meaning)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Button("Edit", systemImage: "pencil") {
                                glossaryEditor = GlossaryEditorState(term: term)
                            }
                            .labelStyle(.iconOnly)
                            Button("Remove", systemImage: "trash", role: .destructive) {
                                pendingGlossaryDeletion = term
                            }
                            .labelStyle(.iconOnly)
                        }
                        .khutbaCard()
                    }

                    SectionHeading(
                        title: "Change password",
                        subtitle: "Enter your current password before choosing a new one."
                    )
                    VStack(spacing: 13) {
                        SecureField("Current password", text: $currentPassword)
                            .textFieldStyle(.roundedBorder)
                        SecureField("New password", text: $newPassword)
                            .textFieldStyle(.roundedBorder)
                        SecureField("Confirm new password", text: $confirmPassword)
                            .textFieldStyle(.roundedBorder)
                        if !confirmPassword.isEmpty && newPassword != confirmPassword {
                            Text("Passwords do not match")
                                .font(.caption)
                                .foregroundStyle(.red)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        Button("Update password") {
                            model.changePassword(current: currentPassword, new: newPassword)
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.large)
                        .frame(maxWidth: .infinity)
                        .disabled(!canChangePassword)
                    }
                    .khutbaCard()
                }
                .padding(20)
            }
            .khutbaBackground()
            .navigationBarBackButtonHidden()
            .toolbar { ScreenHeader(title: "Mosque settings", backAction: model.back) }
            .onAppear { mosqueName = model.adminMosque?.name ?? "" }
        }
        .sheet(item: $glossaryEditor) { editor in
            GlossaryEditorView(term: editor.term) { arabic, literal, meaning, variations, alternatives in
                model.saveGlossaryTerm(
                    id: editor.term?.id,
                    arabic: arabic,
                    literal: literal,
                    meaning: meaning,
                    variations: variations,
                    alternatives: alternatives
                )
            }
        }
        .alert("Remove glossary term?", isPresented: Binding(
            get: { pendingGlossaryDeletion != nil },
            set: { if !$0 { pendingGlossaryDeletion = nil } }
        )) {
            Button("Cancel", role: .cancel) { pendingGlossaryDeletion = nil }
            Button("Remove", role: .destructive) {
                if let term = pendingGlossaryDeletion { model.deleteGlossaryTerm(id: term.id) }
                pendingGlossaryDeletion = nil
            }
        } message: {
            Text("\(pendingGlossaryDeletion?.arabicTerm ?? "This term") will return to the built-in glossary meaning.")
        }
    }
}

private struct GlossaryEditorState: Identifiable {
    let id = UUID()
    let term: MosqueGlossaryTerm?
}

private struct VariationRow: Identifiable {
    let id = UUID()
    var arabic = ""
    var english = ""

    static func parse(_ value: String) -> [VariationRow] {
        value.components(separatedBy: "|").compactMap { item in
            let item = item.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !item.isEmpty else { return nil }
            guard let separator = item.range(of: #"\s+[—–-]\s+"#, options: .regularExpression) else {
                return VariationRow(arabic: item)
            }
            return VariationRow(arabic: String(item[..<separator.lowerBound]), english: String(item[separator.upperBound...]))
        }
    }
}

private struct GlossaryEditorView: View {
    @Environment(\.dismiss) private var dismiss
    let term: MosqueGlossaryTerm?
    let onSave: (String, String, String, String, String) -> Void

    @State private var arabic: String
    @State private var literal: String
    @State private var meaning: String
    @State private var variations: [VariationRow]
    @State private var alternatives: String

    init(term: MosqueGlossaryTerm?, onSave: @escaping (String, String, String, String, String) -> Void) {
        self.term = term
        self.onSave = onSave
        _arabic = State(initialValue: term?.arabicTerm ?? "")
        _literal = State(initialValue: term?.literalTranslation ?? "")
        _meaning = State(initialValue: term?.meaning ?? "")
        _variations = State(initialValue: VariationRow.parse(term?.arabicVariations ?? ""))
        _alternatives = State(initialValue: term?.alternativeContextMeanings ?? "")
    }

    private var isValid: Bool {
        !arabic.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        !literal.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        meaning.trimmingCharacters(in: .whitespacesAndNewlines).count >= 3 &&
        variations.allSatisfy { !$0.arabic.trimmingCharacters(in: .whitespaces).isEmpty && !$0.english.trimmingCharacters(in: .whitespaces).isEmpty && !$0.arabic.contains("|") && !$0.english.contains("|") }
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Use the exact Arabic word or expression. It is highlighted only when the verifier confirms that this sense fits the context.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Section("Term") {
                    TextField("Arabic word or expression", text: $arabic, axis: .vertical)
                        .multilineTextAlignment(.trailing)
                        .environment(\.layoutDirection, .rightToLeft)
                    TextField("Concise English translation", text: $literal, axis: .vertical)
                    TextField("Explanation shown when tapped", text: $meaning, axis: .vertical)
                        .lineLimit(3...8)
                }
                Section("Variations (optional)") {
                    ForEach($variations) { $variation in
                        VStack(alignment: .leading, spacing: 10) {
                            TextField("Arabic variation", text: $variation.arabic)
                                .multilineTextAlignment(.trailing)
                            TextField("English translation", text: $variation.english)
                            Button("Remove variation", role: .destructive) { variations.removeAll { $0.id == variation.id } }
                        }
                    }
                    Button("Add variation", systemImage: "plus") { variations.append(VariationRow()) }
                }
                Section("Optional context") {
                    TextField("Other contextual meanings", text: $alternatives, axis: .vertical)
                        .lineLimit(2...6)
                }
            }
            .navigationTitle(term == nil ? "Add glossary term" : "Edit glossary term")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        let encoded = variations.map { "\($0.arabic.trimmingCharacters(in: .whitespaces)) — \($0.english.trimmingCharacters(in: .whitespaces))" }.joined(separator: " | ")
                        onSave(arabic, literal, meaning, encoded, alternatives)
                        dismiss()
                    }
                    .disabled(!isValid)
                }
            }
        }
    }
}

struct AdminSermonView: View {
    @EnvironmentObject private var model: AppModel
    @State private var needsAttention = false

    var body: some View {
        NavigationStack {
            ScrollView {
                if let sermon = model.selectedSermon {
                    LazyVStack(spacing: 16) {
                        SermonStatusView(sermon: sermon)
                        if model.translatingSermonID == sermon.id {
                            TranslationProgressView(
                                completed: model.translatedSegments,
                                total: model.translationTotalSegments,
                                reconnecting: model.translationReconnecting
                            )
                        } else if sermon.status == SermonStatus.draft || sermon.status == SermonStatus.failed {
                            Button(sermon.status == SermonStatus.failed ? "Retry unfinished sections" : "Create translation draft") { model.translate(sermonID: sermon.id) }
                                .buttonStyle(.borderedProminent)
                                .controlSize(.large)
                                .frame(maxWidth: .infinity)
                        }

                        if model.translatingSermonID != sermon.id {
                            if sermon.status == SermonStatus.sourceReviewRequired {
                                SourceTextReviewView(sermon: sermon)
                            } else {
                                if sermon.segments.contains(where: { !($0.translatedText ?? "").isEmpty }) {
                                    Button("Preview saved edits as a reader", systemImage: "eye") { model.openReaderPreview(id: sermon.id) }
                                        .buttonStyle(.bordered)
                                }
                                Toggle("Needs attention only", isOn: $needsAttention)
                                ForEach(sermon.segments.filter { !needsAttention || $0.verificationStatus != "HUMAN_APPROVED" }) { segment in
                                    SegmentReviewView(sermonID: sermon.id, segment: segment)
                                }
                            }
                        }

                        if sermon.status == SermonStatus.reviewRequired,
                           !sermon.segments.isEmpty,
                           sermon.segments.allSatisfy({ $0.verificationStatus == "HUMAN_APPROVED" }) {
                            Button("Publish reviewed khutba") { model.publish(sermonID: sermon.id) }
                                .buttonStyle(.borderedProminent)
                                .controlSize(.large)
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .padding(16)
                }
            }
            .khutbaBackground()
            .navigationBarBackButtonHidden()
            .toolbar {
                ScreenHeader(title: model.selectedSermon?.title ?? "Review", backAction: model.back)
            }
        }
    }
}

private struct SermonStatusView: View {
    let sermon: SermonDetail
    private var stage: Int {
        switch sermon.status {
        case SermonStatus.sourceReviewRequired: return 1
        case SermonStatus.draft, SermonStatus.translating, SermonStatus.failed: return 2
        case SermonStatus.reviewRequired: return 3
        default: return 4
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Step \(stage + 1) of 5")
                    .font(.headline)
                Spacer()
                StatusPill(status: sermon.status)
            }
            Text("\(sermon.khutbaDate) · \(sermon.targetLanguage.uppercased())")
            Text("Upload → Check Arabic → Translate → Review → Publish")
                .font(.caption).foregroundStyle(.secondary)
            ProgressView(value: Double(stage), total: 4)
            if !sermon.segments.isEmpty {
                Text("\(sermon.segments.filter { $0.verificationStatus == "HUMAN_APPROVED" }.count) of \(sermon.segments.count) sections approved")
                    .font(.subheadline.bold())
            }
            if let reason = sermon.failureReason {
                Text(reason).foregroundStyle(.red)
            }
            if sermon.status == SermonStatus.sourceReviewRequired {
                Text("Translation is locked until a mosque reviewer checks and confirms the extracted Arabic text.")
                    .foregroundStyle(.secondary)
            } else if sermon.status == SermonStatus.reviewRequired {
                Text("Publication is locked until every segment is approved by a human reviewer.")
                    .foregroundStyle(.secondary)
            }
        }
        .padding(17)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 18))
    }
}

private struct TranslationProgressView: View {
    let completed: Int
    let total: Int
    let reconnecting: Bool

    private var progress: Double {
        guard total > 0 else { return 0 }
        return Double(min(max(completed, 0), total)) / Double(total)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(reconnecting ? "Reconnecting to translation" : "Creating grounded translation")
                .font(.headline)
            Text(total > 0
                 ? "Checking sources and translating section \(min(completed + 1, total)) of \(total)"
                 : "Preparing the khutba for translation")
                .foregroundStyle(.secondary)
            if completed == 0 {
                ProgressView()
            } else {
                ProgressView(value: progress)
                Text("\(completed) of \(total) sections completed · \(Int(progress * 100))%")
                    .font(.caption.bold())
            }
            Text(reconnecting ? "Progress will refresh when the connection returns. Do not start another translation." : "You can leave this screen. Reopen the khutba to resume watching progress; completed sections are saved on the server.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(KhutbaTheme.mint.opacity(0.7), in: RoundedRectangle(cornerRadius: 18))
    }
}

private struct SourceTextReviewView: View {
    @EnvironmentObject private var model: AppModel
    let sermon: SermonDetail
    @State private var arabicText: String

    init(sermon: SermonDetail) {
        self.sermon = sermon
        _arabicText = State(initialValue: sermon.segments.compactMap(\.arabicText).joined(separator: "\n\n"))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Step 1 · Verify extracted Arabic")
                .font(.title3.bold())
            Text("Compare this text with every page of the original document. OCR can confuse letters, names, numbers, Qur’anic verses, and hadith wording.")
                .foregroundStyle(.secondary)
            TextEditor(text: $arabicText)
                .font(.body)
                .multilineTextAlignment(.trailing)
                .environment(\.layoutDirection, .rightToLeft)
                .frame(minHeight: 280)
                .padding(8)
                .background(.background, in: RoundedRectangle(cornerRadius: 12))
                .overlay { RoundedRectangle(cornerRadius: 12).stroke(.quaternary) }
            Button {
                model.confirmSourceText(sermonID: sermon.id, arabicText: arabicText)
            } label: {
                Label("Confirm Arabic and continue", systemImage: "checkmark.seal")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(arabicText.count < 40)
        }
        .khutbaCard()
    }
}

private struct SegmentReviewView: View {
    @EnvironmentObject private var model: AppModel
    let sermonID: String
    let segment: SermonSegment
    @State private var translation: String
    @State private var note: String

    init(sermonID: String, segment: SermonSegment) {
        self.sermonID = sermonID
        self.segment = segment
        _translation = State(initialValue: segment.translatedText ?? "")
        _note = State(initialValue: segment.reviewerNote ?? "")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                if segment.verificationStatus == "HUMAN_APPROVED" {
                    Image(systemName: "checkmark.circle.fill").foregroundStyle(KhutbaTheme.green)
                } else if !(segment.issues ?? []).isEmpty {
                    Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.red)
                }
                Text("Segment \(segment.ordinal + 1)")
                    .font(.headline)
            }
            if let arabic = segment.arabicText, !arabic.isEmpty {
                Text(arabic)
                    .frame(maxWidth: .infinity, alignment: .trailing)
                    .multilineTextAlignment(.trailing)
                    .environment(\.layoutDirection, .rightToLeft)
            }
            VStack(alignment: .leading, spacing: 5) {
                Text("Translation").font(.caption.bold()).foregroundStyle(.secondary)
                TextEditor(text: $translation)
                    .frame(minHeight: 130)
                    .padding(6)
                    .background(.background, in: RoundedRectangle(cornerRadius: 10))
                    .overlay { RoundedRectangle(cornerRadius: 10).stroke(.quaternary) }
            }
            if let issues = segment.issues, !issues.isEmpty {
                Text("Model/verifier warnings")
                    .font(.headline)
                    .foregroundStyle(.red)
                ForEach(issues, id: \.self) { Text("• \($0)").font(.caption) }
            }
            ForEach(segment.citations) { citation in
                ReviewerCitationView(citation: citation)
            }
            TextField("Reviewer note (optional)", text: $note, axis: .vertical)
                .textFieldStyle(.roundedBorder)
            HStack {
                Button("Needs work") {
                    model.reviewSegment(
                        sermonID: sermonID,
                        segmentID: segment.id,
                        translation: translation,
                        approved: false,
                        note: note
                    )
                }
                .buttonStyle(.bordered)
                .frame(maxWidth: .infinity)
                Button("Approve") {
                    model.reviewSegment(
                        sermonID: sermonID,
                        segmentID: segment.id,
                        translation: translation,
                        approved: true,
                        note: note
                    )
                }
                .buttonStyle(.borderedProminent)
                .frame(maxWidth: .infinity)
            }
            .controlSize(.large)
            .disabled(translation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .khutbaCard()
        .onChange(of: segment.translatedText) { _, value in translation = value ?? "" }
        .onChange(of: segment.reviewerNote) { _, value in note = value ?? "" }
    }
}

private struct ReviewerCitationView: View {
    let citation: Citation

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Verified \(citation.sourceKind.capitalized) · \(citation.title)")
                .font(.caption.bold())
            Text(citation.authority)
                .font(.caption)
                .foregroundStyle(KhutbaTheme.green)
            Text(citation.excerpt)
                .font(.caption)
            if let rawURL = citation.url, let url = URL(string: rawURL) {
                Link("Open source", destination: url)
                    .font(.caption.bold())
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(KhutbaTheme.insetBackground, in: RoundedRectangle(cornerRadius: 12))
    }
}
