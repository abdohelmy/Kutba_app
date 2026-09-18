import Foundation

struct LoginRequest: Encodable {
    let username: String
    let password: String
    let accountType: String
}

struct MosqueRegistrationRequest: Encodable {
    let mosqueName: String
    let city: String
    let country: String
    let adminDisplayName: String
    let username: String
    let password: String
    let permissionPassword: String
}

struct MosqueProfileUpdateRequest: Encodable {
    let mosqueName: String
}

struct PasswordChangeRequest: Encodable {
    let currentPassword: String
    let newPassword: String
}

struct GlossaryTermRequest: Encodable {
    let arabicTerm: String
    let meaning: String
    let literalTranslation: String
    let arabicVariations: String
    let alternativeContextMeanings: String
}

struct SegmentReviewRequest: Encodable {
    let translatedText: String
    let approved: Bool
    let reviewerNote: String?
}

struct SourceTextReviewRequest: Encodable {
    let arabicText: String
}

struct TokenResponse: Decodable {
    let accessToken: String
}

struct User: Codable, Identifiable, Equatable {
    let id: String
    let username: String
    let displayName: String
    let role: String
    let mosqueId: String?
}

struct Mosque: Codable, Identifiable, Equatable {
    let id: String
    let name: String
    let city: String
    let country: String
}

struct Citation: Codable, Identifiable, Equatable {
    var id: String { "\(chunkId)-\(sourceId)-\(arabicStart ?? -1)-\(translationStart ?? -1)" }

    let chunkId: String
    let sourceId: String
    let title: String
    let authority: String
    let excerpt: String
    let arabicExcerpt: String?
    let transliteration: String?
    let displayReference: String?
    let sourceKind: String
    let url: String?
    let translationStart: Int?
    let translationEnd: Int?
    let arabicStart: Int?
    let arabicEnd: Int?
    var anchorValid: Bool? = nil
}

struct GlossaryTerm: Codable, Identifiable, Equatable {
    var id: String { "\(arabicTerm)-\(displayTerm)" }

    let arabicTerm: String
    let meaning: String
    let literalTranslation: String
    let displayTerm: String
    let alternativeContextMeanings: String
    let translationStart: Int?
    let translationEnd: Int?
}

struct MosqueGlossaryTerm: Codable, Identifiable, Equatable {
    let id: String
    let arabicTerm: String
    let meaning: String
    let literalTranslation: String
    let arabicVariations: String
    let alternativeContextMeanings: String
}

struct SermonSegment: Codable, Identifiable, Equatable {
    let id: String
    let ordinal: Int
    let arabicText: String?
    let translatedText: String?
    let verificationStatus: String?
    let issues: [String]?
    let citations: [Citation]
    let glossaryTerms: [GlossaryTerm]?
    let reviewerNote: String?
}

struct SermonSummary: Codable, Identifiable, Equatable {
    let id: String
    let mosqueId: String
    let title: String
    let khutbaDate: String
    let targetLanguage: String
    let status: String
    let providerName: String?
    let modelName: String?
    let failureReason: String?
    let publishedAt: String?
}

struct SermonDetail: Codable, Identifiable, Equatable {
    let id: String
    let mosqueId: String
    let title: String
    let khutbaDate: String
    let targetLanguage: String
    let status: String
    let providerName: String?
    let modelName: String?
    let failureReason: String?
    let publishedAt: String?
    let segments: [SermonSegment]
}

struct TranslationQueued: Decodable {
    let id: String
    let status: String
}

struct EmptyResponse: Decodable {}

enum SermonStatus {
    static let sourceReviewRequired = "SOURCE_REVIEW_REQUIRED"
    static let draft = "DRAFT"
    static let translating = "TRANSLATING"
    static let reviewRequired = "REVIEW_REQUIRED"
    static let published = "PUBLISHED"
    static let hidden = "HIDDEN"
    static let failed = "FAILED"
}

extension JSONDecoder {
    static let khutba: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()
}

extension JSONEncoder {
    static let khutba: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }()
}
