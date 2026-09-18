package com.khutba.app.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class LoginRequest(
    val username: String,
    val password: String,
    @SerialName("account_type") val accountType: String,
)

@Serializable
data class RegisterRequest(
    val username: String,
    @SerialName("display_name") val displayName: String,
    val password: String,
)

@Serializable
data class MosqueRegisterRequest(
    @SerialName("mosque_name") val mosqueName: String,
    val city: String,
    val country: String,
    @SerialName("admin_display_name") val adminDisplayName: String,
    val username: String,
    val password: String,
    @SerialName("permission_password") val permissionPassword: String,
)

@Serializable
data class MosqueProfileUpdateRequest(
    @SerialName("mosque_name") val mosqueName: String,
)

@Serializable
data class PasswordChangeRequest(
    @SerialName("current_password") val currentPassword: String,
    @SerialName("new_password") val newPassword: String,
)

@Serializable
data class MosqueGlossaryTermRequest(
    @SerialName("arabic_term") val arabicTerm: String,
    val meaning: String,
    @SerialName("literal_translation") val literalTranslation: String,
    @SerialName("arabic_variations") val arabicVariations: String = "",
    @SerialName("alternative_context_meanings")
    val alternativeContextMeanings: String = "",
)

@Serializable
data class MosqueGlossaryTerm(
    val id: String,
    @SerialName("arabic_term") val arabicTerm: String,
    val meaning: String,
    @SerialName("literal_translation") val literalTranslation: String,
    @SerialName("arabic_variations") val arabicVariations: String = "",
    @SerialName("alternative_context_meanings")
    val alternativeContextMeanings: String = "",
)

@Serializable
data class TokenResponse(@SerialName("access_token") val accessToken: String)

@Serializable
data class User(
    val id: String,
    val username: String,
    @SerialName("display_name") val displayName: String,
    val role: String,
    @SerialName("mosque_id") val mosqueId: String? = null,
)

@Serializable
data class Mosque(
    val id: String,
    val name: String,
    val city: String,
    val country: String,
)

@Serializable
data class Citation(
    @SerialName("chunk_id") val chunkId: String,
    @SerialName("source_id") val sourceId: String,
    val title: String,
    val authority: String,
    val excerpt: String,
    @SerialName("arabic_excerpt") val arabicExcerpt: String? = null,
    val transliteration: String? = null,
    @SerialName("display_reference") val displayReference: String? = null,
    @SerialName("source_kind") val sourceKind: String = "canonical",
    val url: String? = null,
    @SerialName("translation_start") val translationStart: Int? = null,
    @SerialName("translation_end") val translationEnd: Int? = null,
    @SerialName("arabic_start") val arabicStart: Int? = null,
    @SerialName("arabic_end") val arabicEnd: Int? = null,
    @SerialName("anchor_valid") val anchorValid: Boolean = true,
)

@Serializable
data class GlossaryTerm(
    @SerialName("arabic_term") val arabicTerm: String,
    val meaning: String,
    @SerialName("literal_translation") val literalTranslation: String,
    @SerialName("display_term") val displayTerm: String,
    @SerialName("alternative_context_meanings")
    val alternativeContextMeanings: String = "",
    @SerialName("translation_start") val translationStart: Int? = null,
    @SerialName("translation_end") val translationEnd: Int? = null,
)

@Serializable
data class SermonSegment(
    val id: String,
    val ordinal: Int,
    @SerialName("arabic_text") val arabicText: String = "",
    @SerialName("translated_text") val translatedText: String? = null,
    @SerialName("verification_status") val verificationStatus: String = "",
    val issues: List<String> = emptyList(),
    val citations: List<Citation> = emptyList(),
    @SerialName("glossary_terms") val glossaryTerms: List<GlossaryTerm> = emptyList(),
    @SerialName("reviewer_note") val reviewerNote: String? = null,
)

@Serializable
data class SermonSummary(
    val id: String,
    @SerialName("mosque_id") val mosqueId: String,
    val title: String,
    @SerialName("khutba_date") val khutbaDate: String,
    @SerialName("target_language") val targetLanguage: String,
    val status: String,
    @SerialName("provider_name") val providerName: String? = null,
    @SerialName("model_name") val modelName: String? = null,
    @SerialName("failure_reason") val failureReason: String? = null,
    @SerialName("published_at") val publishedAt: String? = null,
)

@Serializable
data class SermonDetail(
    val id: String,
    @SerialName("mosque_id") val mosqueId: String,
    val title: String,
    @SerialName("khutba_date") val khutbaDate: String,
    @SerialName("target_language") val targetLanguage: String,
    val status: String,
    @SerialName("provider_name") val providerName: String? = null,
    @SerialName("model_name") val modelName: String? = null,
    @SerialName("failure_reason") val failureReason: String? = null,
    @SerialName("published_at") val publishedAt: String? = null,
    val segments: List<SermonSegment> = emptyList(),
)

@Serializable
data class SegmentReviewRequest(
    @SerialName("translated_text") val translatedText: String,
    val approved: Boolean,
    @SerialName("reviewer_note") val reviewerNote: String? = null,
)

@Serializable
data class SourceTextReviewRequest(@SerialName("arabic_text") val arabicText: String)

@Serializable
data class TranslationQueued(
    val id: String,
    val status: String,
)
