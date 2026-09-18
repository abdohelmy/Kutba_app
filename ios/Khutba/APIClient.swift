import Foundation

enum APIError: LocalizedError {
    case invalidResponse
    case http(status: Int, detail: String)
    case invalidDocument
    case documentTooLarge

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "The server returned an invalid response."
        case let .http(_, detail):
            return detail
        case .invalidDocument:
            return "Choose a PDF or DOCX document."
        case .documentTooLarge:
            return "The selected document is larger than 15 MB."
        }
    }
}

final class APIClient {
    static let shared = APIClient()

    // Keep this aligned with the Android BuildConfig release URL.
    let baseURL = URL(string: "https://35.207.58.39.sslip.io/api/v1/")!

    private let session: URLSession
    private var token: String?

    init(session: URLSession = .shared) {
        self.session = session
    }

    func logout() {
        token = nil
    }

    func login(username: String, password: String) async throws -> User {
        let response: TokenResponse = try await send(
            path: "auth/login",
            method: "POST",
            body: LoginRequest(
                username: username.trimmingCharacters(in: .whitespacesAndNewlines),
                password: password,
                accountType: "MOSQUE"
            )
        )
        token = response.accessToken
        do {
            return try await authorized(path: "auth/me")
        } catch {
            token = nil
            throw error
        }
    }

    func registerMosque(_ request: MosqueRegistrationRequest) async throws -> User {
        let _: User = try await send(path: "auth/register-mosque", method: "POST", body: request)
        return try await login(username: request.username, password: request.password)
    }

    func mosques() async throws -> [Mosque] {
        try await send(path: "reader/mosques")
    }

    func publishedSermons(mosqueID: String, language: String?) async throws -> [SermonSummary] {
        var components = URLComponents(
            url: url(for: "reader/mosques/\(mosqueID)/sermons"),
            resolvingAgainstBaseURL: false
        )!
        if let language, !language.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            components.queryItems = [URLQueryItem(name: "language", value: language.lowercased())]
        }
        return try await send(url: components.url!)
    }

    func publishedSermon(id: String) async throws -> SermonDetail {
        try await send(path: "reader/sermons/\(id)")
    }

    func downloadPublishedSermonPDF(id: String) async throws -> URL {
        let (temporaryURL, response) = try await session.download(
            from: url(for: "reader/sermons/\(id)/pdf")
        )
        try validate(response: response, data: nil)
        let destination = FileManager.default.temporaryDirectory
            .appendingPathComponent("khutba-\(id).pdf")
        if FileManager.default.fileExists(atPath: destination.path) {
            try FileManager.default.removeItem(at: destination)
        }
        try FileManager.default.moveItem(at: temporaryURL, to: destination)
        return destination
    }

    func adminSermons() async throws -> [SermonSummary] {
        try await authorized(path: "admin/sermons")
    }

    func adminProfile() async throws -> Mosque {
        try await authorized(path: "admin/profile")
    }

    func updateMosqueName(_ name: String) async throws -> Mosque {
        try await authorized(
            path: "admin/profile",
            method: "PATCH",
            body: MosqueProfileUpdateRequest(mosqueName: name.trimmingCharacters(in: .whitespacesAndNewlines))
        )
    }

    func changePassword(current: String, new: String) async throws {
        try await authorizedNoContent(
            path: "admin/password",
            method: "PUT",
            body: PasswordChangeRequest(currentPassword: current, newPassword: new)
        )
    }

    func glossary() async throws -> [MosqueGlossaryTerm] {
        try await authorized(path: "admin/glossary")
    }

    func saveGlossaryTerm(id: String?, request: GlossaryTermRequest) async throws -> MosqueGlossaryTerm {
        if let id {
            return try await authorized(path: "admin/glossary/\(id)", method: "PUT", body: request)
        }
        return try await authorized(path: "admin/glossary", method: "POST", body: request)
    }

    func deleteGlossaryTerm(id: String) async throws {
        try await authorizedNoContent(path: "admin/glossary/\(id)", method: "DELETE")
    }

    func adminSermon(id: String) async throws -> SermonDetail {
        try await authorized(path: "admin/sermons/\(id)")
    }

    func previewSermon(id: String) async throws -> SermonDetail {
        try await authorized(path: "admin/sermons/\(id)/preview")
    }

    func uploadSermon(
        fileURL: URL,
        title: String,
        date: String,
        targetLanguage: String
    ) async throws -> SermonSummary {
        let didAccess = fileURL.startAccessingSecurityScopedResource()
        defer { if didAccess { fileURL.stopAccessingSecurityScopedResource() } }

        let fileData = try Data(contentsOf: fileURL)
        guard fileData.count <= 15 * 1024 * 1024 else { throw APIError.documentTooLarge }
        let fileExtension = fileURL.pathExtension.lowercased()
        let mimeType: String
        switch fileExtension {
        case "pdf":
            mimeType = "application/pdf"
        case "docx":
            mimeType = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        default:
            throw APIError.invalidDocument
        }

        let boundary = "Khutba-\(UUID().uuidString)"
        var body = Data()
        body.appendMultipartField(name: "title", value: title, boundary: boundary)
        body.appendMultipartField(name: "khutba_date", value: date, boundary: boundary)
        body.appendMultipartField(name: "target_language", value: targetLanguage, boundary: boundary)
        body.appendMultipartFile(
            name: "file",
            filename: fileURL.lastPathComponent,
            mimeType: mimeType,
            data: fileData,
            boundary: boundary
        )
        body.append("--\(boundary)--\r\n")

        var request = URLRequest(url: url(for: "admin/sermons"))
        request.httpMethod = "POST"
        request.httpBody = body
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        addAuthorization(to: &request)
        return try await execute(request)
    }

    func deleteSermon(id: String) async throws {
        try await authorizedNoContent(path: "admin/sermons/\(id)", method: "DELETE")
    }

    func setSermonHidden(id: String, hidden: Bool) async throws -> SermonSummary {
        try await authorized(path: "admin/sermons/\(id)/\(hidden ? "hide" : "show")", method: "POST")
    }

    func confirmSourceText(sermonID: String, arabicText: String) async throws -> SermonDetail {
        try await authorized(
            path: "admin/sermons/\(sermonID)/source-text",
            method: "PUT",
            body: SourceTextReviewRequest(arabicText: arabicText.trimmingCharacters(in: .whitespacesAndNewlines))
        )
    }

    func startTranslation(sermonID: String) async throws -> TranslationQueued {
        try await authorized(path: "admin/sermons/\(sermonID)/translate", method: "POST")
    }

    func reviewSegment(
        sermonID: String,
        segmentID: String,
        translation: String,
        approved: Bool,
        note: String?
    ) async throws -> SermonSegment {
        try await authorized(
            path: "admin/sermons/\(sermonID)/segments/\(segmentID)",
            method: "PATCH",
            body: SegmentReviewRequest(
                translatedText: translation,
                approved: approved,
                reviewerNote: note?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
            )
        )
    }

    func publish(sermonID: String) async throws {
        let _: TranslationQueued = try await authorized(
            path: "admin/sermons/\(sermonID)/publish",
            method: "POST"
        )
    }

    private func url(for path: String) -> URL {
        baseURL.appendingPathComponent(path)
    }

    private func send<Response: Decodable>(path: String, method: String = "GET") async throws -> Response {
        try await send(url: url(for: path), method: method)
    }

    private func send<Response: Decodable>(url: URL, method: String = "GET") async throws -> Response {
        var request = URLRequest(url: url)
        request.httpMethod = method
        return try await execute(request)
    }

    private func send<Body: Encodable, Response: Decodable>(
        path: String,
        method: String,
        body: Body
    ) async throws -> Response {
        var request = URLRequest(url: url(for: path))
        request.httpMethod = method
        request.httpBody = try JSONEncoder.khutba.encode(body)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        return try await execute(request)
    }

    private func authorized<Response: Decodable>(
        path: String,
        method: String = "GET"
    ) async throws -> Response {
        var request = URLRequest(url: url(for: path))
        request.httpMethod = method
        addAuthorization(to: &request)
        return try await execute(request)
    }

    private func authorized<Body: Encodable, Response: Decodable>(
        path: String,
        method: String,
        body: Body
    ) async throws -> Response {
        var request = URLRequest(url: url(for: path))
        request.httpMethod = method
        request.httpBody = try JSONEncoder.khutba.encode(body)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAuthorization(to: &request)
        return try await execute(request)
    }

    private func authorizedNoContent(path: String, method: String) async throws {
        var request = URLRequest(url: url(for: path))
        request.httpMethod = method
        addAuthorization(to: &request)
        try await executeNoContent(request)
    }

    private func authorizedNoContent<Body: Encodable>(
        path: String,
        method: String,
        body: Body
    ) async throws {
        var request = URLRequest(url: url(for: path))
        request.httpMethod = method
        request.httpBody = try JSONEncoder.khutba.encode(body)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAuthorization(to: &request)
        try await executeNoContent(request)
    }

    private func addAuthorization(to request: inout URLRequest) {
        guard let token else { return }
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    }

    private func execute<Response: Decodable>(_ request: URLRequest) async throws -> Response {
        do {
            let (data, response) = try await session.data(for: request)
            try validate(response: response, data: data)
            return try JSONDecoder.khutba.decode(Response.self, from: data)
        } catch let error as APIError {
            throw error
        } catch is DecodingError {
            throw APIError.invalidResponse
        } catch {
            throw mapTransportError(error)
        }
    }

    private func executeNoContent(_ request: URLRequest) async throws {
        do {
            let (data, response) = try await session.data(for: request)
            try validate(response: response, data: data)
        } catch let error as APIError {
            throw error
        } catch {
            throw mapTransportError(error)
        }
    }

    private func validate(response: URLResponse, data: Data?) throws {
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard (200...299).contains(http.statusCode) else {
            let detail = if (502...504).contains(http.statusCode) {
                Self.scheduledServiceMessage
            } else {
                data.flatMap(Self.serverDetail(from:))
                    ?? HTTPURLResponse.localizedString(forStatusCode: http.statusCode)
            }
            throw APIError.http(status: http.statusCode, detail: detail)
        }
    }

    private static func serverDetail(from data: Data) -> String? {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let detail = object["detail"] else { return nil }
        if let message = detail as? String { return message }
        if let issues = detail as? [[String: Any]] {
            let messages = issues.compactMap { issue -> String? in
                guard let message = issue["msg"] as? String else { return nil }
                let field = (issue["loc"] as? [Any])?.last.map(String.init(describing:))
                return field.map { "\($0): \(message)" } ?? message
            }
            return messages.isEmpty ? nil : messages.joined(separator: "\n")
        }
        return nil
    }

    private func mapTransportError(_ error: Error) -> Error {
        if let urlError = error as? URLError,
           [.cannotConnectToHost, .cannotFindHost, .networkConnectionLost, .notConnectedToInternet, .timedOut]
            .contains(urlError.code) {
            return APIError.http(status: 503, detail: Self.scheduledServiceMessage)
        }
        return error
    }

    private static let scheduledServiceMessage =
        "The Khutba app is available every Friday from 10:00 AM to 3:00 PM Copenhagen time. " +
        "The service is currently offline; please try again during this window."
}

private extension Data {
    mutating func append(_ string: String) {
        append(string.data(using: .utf8)!)
    }

    mutating func appendMultipartField(name: String, value: String, boundary: String) {
        append("--\(boundary)\r\n")
        append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n")
        append("\(value)\r\n")
    }

    mutating func appendMultipartFile(
        name: String,
        filename: String,
        mimeType: String,
        data: Data,
        boundary: String
    ) {
        append("--\(boundary)\r\n")
        append("Content-Disposition: form-data; name=\"\(name)\"; filename=\"\(filename)\"\r\n")
        append("Content-Type: \(mimeType)\r\n\r\n")
        append(data)
        append("\r\n")
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}
