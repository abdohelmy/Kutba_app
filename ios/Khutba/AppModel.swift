import Foundation
import SwiftUI

@MainActor
final class AppModel: ObservableObject {
    enum Screen: Equatable {
        case start
        case mosqueLogin
        case mosqueRegistration
        case readerMosques
        case readerSermons
        case readerSermon
        case adminHome
        case adminSettings
        case adminSermon
        case adminPreview
        case adminDefinitions
    }

    @Published var screen: Screen = .start
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var noticeMessage: String?
    @Published var user: User?
    @Published var adminMosque: Mosque?
    @Published var adminGlossary: [MosqueGlossaryTerm] = []
    @Published var definitionSermonID: String?
    @Published var glossaryCandidates: [GlossaryCandidate] = []
    @Published var mosques: [Mosque] = []
    @Published var selectedMosque: Mosque?
    @Published var sermons: [SermonSummary] = []
    @Published var selectedSermon: SermonDetail?
    @Published var translatingSermonID: String?
    @Published var translatedSegments = 0
    @Published var translationTotalSegments = 0
    @Published var downloadedPDF: SharedFile?
    @Published var readerOffline = false
    @Published var previewSermon: SermonDetail?
    @Published var translationReconnecting = false

    private let api: APIClient
    func sentenceAlignment(sermonID: String, segmentID: String, text: String) async throws -> [SentenceAlignment] {
        try await api.sentenceAlignment(sermonID: sermonID, segmentID: segmentID, text: text)
    }
    private let readerCache = ReaderCache()
    private var translationTask: Task<Void, Never>?
    private var translationMonitorID = UUID()

    init(api: APIClient = .shared) {
        self.api = api
    }

    func openMosqueLogin() {
        errorMessage = nil
        screen = .mosqueLogin
    }

    func openMosqueRegistration() {
        errorMessage = nil
        screen = .mosqueRegistration
    }

    func continueAsIndividual() {
        perform {
            self.translationTask?.cancel()
            self.api.logout()
            self.user = nil
            self.mosques = try await self.readerRequest(key: "mosques") { try await self.api.mosques() }
            self.screen = .readerMosques
            if let data = UserDefaults.standard.data(forKey: "preferred-mosque"),
               let preferred = try? JSONDecoder().decode(Mosque.self, from: data),
               let mosque = self.mosques.first(where: { $0.id == preferred.id }) {
                try await self.loadMosque(mosque)
            }
        }
    }

    func login(username: String, password: String) {
        perform {
            let user = try await self.api.login(username: username, password: password)
            if user.role == "SUPER_ADMIN" {
                self.api.logout()
                throw APIError.http(status: 403, detail: "Use the web app for the owner dashboard: khutba-reader.abdohelmy1995.chatgpt.site")
            }
            guard user.role == "MOSQUE_ADMIN" || user.role == "SUPER_ADMIN" else {
                self.api.logout()
                throw APIError.http(
                    status: 403,
                    detail: "This account does not have access to a mosque workspace."
                )
            }
            self.user = user
            try await self.refreshAdminHome()
        }
    }

    func registerMosque(
        mosqueName: String,
        city: String,
        country: String,
        adminName: String,
        username: String,
        password: String,
        contactEmail: String
    ) {
        perform {
            let _ = try await self.api.registerMosque(
                MosqueRegistrationRequest(
                    mosqueName: mosqueName.trimmingCharacters(in: .whitespacesAndNewlines),
                    city: city.trimmingCharacters(in: .whitespacesAndNewlines),
                    country: country.trimmingCharacters(in: .whitespacesAndNewlines).uppercased(),
                    adminDisplayName: adminName.trimmingCharacters(in: .whitespacesAndNewlines),
                    username: username.trimmingCharacters(in: .whitespacesAndNewlines),
                    password: password,
                    contactEmail: contactEmail.trimmingCharacters(in: .whitespacesAndNewlines)
                )
            )
            self.screen = .mosqueLogin
            self.noticeMessage = "Request submitted. Sign in after your mosque is approved."
        }
    }

    func logout() {
        translationTask?.cancel()
        translationTask = nil
        api.logout()
        screen = .start
        isLoading = false
        errorMessage = nil
        noticeMessage = nil
        user = nil
        adminMosque = nil
        adminGlossary = []
        mosques = []
        selectedMosque = nil
        sermons = []
        selectedSermon = nil
        translatingSermonID = nil
    }

    func selectMosque(_ mosque: Mosque, language: String?) {
        perform { try await self.loadMosque(mosque) }
    }

    private func loadMosque(_ mosque: Mosque) async throws {
        let previous: [SermonSummary] = await readerCache.read("list-\(mosque.id)") ?? []
        let sermons: [SermonSummary] = try await readerRequest(key: "list-\(mosque.id)") {
            try await self.api.publishedSermons(mosqueID: mosque.id, language: nil)
        }
        if !readerOffline {
            let published = Set(sermons.map(\.id))
            for withdrawn in previous where !published.contains(withdrawn.id) {
                await readerCache.remove("sermon-\(withdrawn.id)")
            }
        }
        selectedMosque = mosque
        self.sermons = sermons
        UserDefaults.standard.set(try? JSONEncoder().encode(mosque), forKey: "preferred-mosque")
        screen = .readerSermons
    }

    private func readerRequest<T: Codable>(key: String, fetch: () async throws -> T) async throws -> T {
        do {
            let value = try await fetch()
            await readerCache.write(value, key: key)
            readerOffline = false
            return value
        } catch {
            guard isTemporaryConnectionFailure(error), let value: T = await readerCache.read(key) else {
                throw error
            }
            readerOffline = true
            return value
        }
    }

    func refreshReader() async {
        do {
            if screen == .readerMosques {
                mosques = try await readerRequest(key: "mosques") { try await self.api.mosques() }
            } else if let mosque = selectedMosque {
                try await loadMosque(mosque)
            }
        } catch { errorMessage = userMessage(for: error) }
    }

    func openPublishedSermon(id: String) {
        perform {
            do {
                self.selectedSermon = try await self.readerRequest(key: "sermon-\(id)") {
                    try await self.api.publishedSermon(id: id)
                }
            } catch {
                if case APIError.http(404, _) = error { await self.readerCache.remove("sermon-\(id)") }
                throw error
            }
            self.screen = .readerSermon
        }
    }

    func downloadPublishedSermon() {
        guard let sermon = selectedSermon else { return }
        perform {
            self.downloadedPDF = SharedFile(url: try await self.api.downloadPublishedSermonPDF(id: sermon.id))
        }
    }

    func openAdminSettings() {
        perform {
            self.adminGlossary = try await self.api.glossary()
            self.screen = .adminSettings
        }
    }

    func updateMosqueName(_ name: String, city: String) {
        perform {
            self.adminMosque = try await self.api.updateMosqueName(name, city: city)
            self.noticeMessage = "Mosque profile updated"
        }
    }

    func changePassword(current: String, new: String) {
        perform {
            try await self.api.changePassword(current: current, new: new)
            self.noticeMessage = "Password updated"
        }
    }

    func saveGlossaryTerm(
        id: String?,
        arabic: String,
        literal: String,
        meaning: String,
        variations: String,
        alternatives: String
    ) {
        perform {
            let request = GlossaryTermRequest(
                arabicTerm: arabic.trimmingCharacters(in: .whitespacesAndNewlines),
                meaning: meaning.trimmingCharacters(in: .whitespacesAndNewlines),
                literalTranslation: literal.trimmingCharacters(in: .whitespacesAndNewlines),
                arabicVariations: variations.trimmingCharacters(in: .whitespacesAndNewlines),
                alternativeContextMeanings: alternatives.trimmingCharacters(in: .whitespacesAndNewlines)
            )
            let _: MosqueGlossaryTerm = try await self.api.saveGlossaryTerm(id: id, request: request)
            self.adminGlossary = try await self.api.glossary()
            self.noticeMessage = "Glossary submitted for owner approval"
        }
    }

    func deleteGlossaryTerm(id: String) {
        perform {
            try await self.api.deleteGlossaryTerm(id: id)
            self.adminGlossary = try await self.api.glossary()
            self.noticeMessage = "Glossary term removed"
        }
    }

    func uploadSermon(fileURL: URL, title: String, date: Date) {
        perform {
            let summary = try await self.api.uploadSermon(
                fileURL: fileURL,
                title: title.trimmingCharacters(in: .whitespacesAndNewlines),
                date: DateFormatters.apiDate.string(from: date),
                targetLanguage: "en"
            )
            self.selectedSermon = try await self.api.adminSermon(id: summary.id)
            self.screen = .adminSermon
        }
    }

    func openAdminSermon(id: String) {
        perform {
            self.selectedSermon = try await self.api.adminSermon(id: id)
            self.screen = .adminSermon
            if self.selectedSermon?.status == SermonStatus.translating {
                self.trackTranslation(sermonID: id, start: false)
            }
        }
    }

    func createDanish(sermonID: String) {
        perform {
            let child = try await self.api.createDanish(sermonID: sermonID)
            self.selectedSermon = try await self.api.adminSermon(id: child.id)
            self.screen = .adminSermon
            if self.selectedSermon?.status == SermonStatus.translating {
                self.trackTranslation(sermonID: child.id, start: false)
            }
        }
    }

    func updateSermonTitle(sermonID: String, title: String) {
        perform {
            let _ = try await self.api.updateSermonTitle(id: sermonID, title: title.trimmingCharacters(in: .whitespacesAndNewlines))
            self.selectedSermon = try await self.api.adminSermon(id: sermonID)
            self.noticeMessage = "Title updated."
        }
    }

    func openReaderPreview(id: String) {
        perform {
            self.previewSermon = try await self.api.previewSermon(id: id)
            self.screen = .adminPreview
        }
    }

    func deleteSermon(id: String) {
        perform {
            try await self.api.deleteSermon(id: id)
            try await self.refreshAdminHome()
        }
    }

    func setSermonHidden(id: String, hidden: Bool) {
        perform {
            let _: SermonSummary = try await self.api.setSermonHidden(id: id, hidden: hidden)
            try await self.refreshAdminHome()
        }
    }

    func confirmSourceText(sermonID: String, arabicText: String) {
        perform {
            self.selectedSermon = try await self.api.confirmSourceText(
                sermonID: sermonID,
                arabicText: arabicText
            )
        }
    }

    func translate(sermonID: String) {
        trackTranslation(sermonID: sermonID, start: true)
    }

    private func trackTranslation(sermonID: String, start: Bool) {
        if translatingSermonID == sermonID, translationTask?.isCancelled == false { return }
        translationTask?.cancel()
        let monitorID = UUID()
        translationMonitorID = monitorID
        translationTask = Task { @MainActor in
            translatingSermonID = sermonID
            translatedSegments = selectedSermon?.segments.filter { !($0.translatedText ?? "").isEmpty }.count ?? 0
            translationTotalSegments = selectedSermon?.segments.count ?? 0
            translationReconnecting = false
            errorMessage = nil
            defer {
                if translationMonitorID == monitorID {
                    translatingSermonID = nil
                    translationReconnecting = false
                }
            }
            do {
                if start {
                    do {
                        let _: TranslationQueued = try await api.startTranslation(sermonID: sermonID)
                    } catch {
                        // The POST may have succeeded even when its response was lost.
                        if case APIError.http(409, _) = error { /* Check the existing job. */ }
                        else if isTemporaryConnectionFailure(error) { translationReconnecting = true }
                        else { throw error }
                    }
                }
                while !Task.isCancelled {
                    try Task.checkCancellation()
                    try await Task.sleep(for: .seconds(translationReconnecting ? 10 : 2))
                    let sermon: SermonDetail
                    do { sermon = try await api.adminSermon(id: sermonID) }
                    catch {
                        if isTemporaryConnectionFailure(error) { translationReconnecting = true; continue }
                        throw error
                    }
                    translationReconnecting = false
                    if selectedSermon?.id == sermonID { selectedSermon = sermon }
                    translatedSegments = sermon.segments.filter {
                        !($0.translatedText ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    }.count
                    translationTotalSegments = sermon.segments.count
                    if sermon.status != SermonStatus.translating { return }
                }
            } catch is CancellationError {
                return
            } catch {
                errorMessage = userMessage(for: error)
            }
        }
    }

    func reviewSegment(
        sermonID: String,
        segmentID: String,
        translation: String,
        approved: Bool,
        note: String
    ) {
        perform {
            let _: SermonSegment = try await self.api.reviewSegment(
                sermonID: sermonID,
                segmentID: segmentID,
                translation: translation.trimmingCharacters(in: .whitespacesAndNewlines),
                approved: approved,
                note: note
            )
            self.selectedSermon = try await self.api.adminSermon(id: sermonID)
        }
    }

    func publish(sermonID: String) {
        perform {
            try await self.api.publish(sermonID: sermonID)
            if self.selectedSermon?.targetLanguage == "da" {
                try await self.refreshAdminHome()
                return
            }
            self.definitionSermonID = sermonID
            self.glossaryCandidates = []
            self.screen = .adminDefinitions
            await self.loadDefinitions(sermonID: sermonID)
        }
    }

    private func loadDefinitions(sermonID: String) async {
        do {
            glossaryCandidates = try await api.glossaryCandidates(sermonID: sermonID)
        } catch {
            errorMessage = "Your khutba is published. Definitions could not be loaded. You can refresh or skip."
        }
    }

    func openDefinitions(sermonID: String) {
        perform {
            self.definitionSermonID = sermonID
            self.glossaryCandidates = []
            self.screen = .adminDefinitions
            await self.loadDefinitions(sermonID: sermonID)
        }
    }

    func saveDefinition(_ candidate: GlossaryCandidate, phrase: String, meaning: String) {
        perform {
            guard let id = self.definitionSermonID else { return }
            try await self.api.contributeGlossary(sermonID: id, request: GlossaryContribution(
                segmentId: candidate.segmentId, arabicTerm: candidate.arabicTerm,
                literalTranslation: phrase.trimmingCharacters(in: .whitespacesAndNewlines),
                meaning: meaning.trimmingCharacters(in: .whitespacesAndNewlines)
            ))
            self.glossaryCandidates.removeAll { $0.id == candidate.id }
            self.noticeMessage = "Definition submitted for owner approval."
        }
    }

    func finishDefinitions() {
        perform { try await self.refreshAdminHome() }
    }

    func back() {
        errorMessage = nil
        switch screen {
        case .mosqueLogin:
            screen = .start
        case .mosqueRegistration:
            screen = .mosqueLogin
        case .readerMosques:
            screen = .start
        case .readerSermons:
            screen = .readerMosques
        case .readerSermon:
            screen = .readerSermons
        case .adminHome:
            break
        case .adminSettings, .adminSermon:
            screen = .adminHome
        case .adminPreview:
            screen = .adminSermon
        case .adminDefinitions:
            finishDefinitions()
        case .start:
            break
        }
    }

    private func refreshAdminHome() async throws {
        async let sermons = api.adminSermons()
        if user?.mosqueId != nil {
            async let mosque = api.adminProfile()
            self.adminMosque = try await mosque
        }
        self.sermons = try await sermons
        selectedSermon = nil
        screen = .adminHome
    }

    private func perform(_ operation: @escaping @MainActor () async throws -> Void) {
        Task { @MainActor in
            isLoading = true
            errorMessage = nil
            noticeMessage = nil
            defer { isLoading = false }
            do {
                try await operation()
            } catch {
                errorMessage = userMessage(for: error)
            }
        }
    }

    private func userMessage(for error: Error) -> String {
        (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
    }
}

struct SharedFile: Identifiable {
    let id = UUID()
    let url: URL
}
