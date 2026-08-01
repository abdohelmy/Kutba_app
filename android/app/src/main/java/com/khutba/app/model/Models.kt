package com.khutba.app.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class LoginRequest(val email: String, val password: String)

@Serializable
data class RegisterRequest(
    val email: String,
    @SerialName("display_name") val displayName: String,
    val password: String,
)

@Serializable
data class TokenResponse(@SerialName("access_token") val accessToken: String)

@Serializable
data class User(
    val id: String,
    val email: String,
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
data class TrustedSource(
    val id: String,
    val title: String,
    val authority: String,
    val language: String,
    val sha256: String,
    @SerialName("created_at") val createdAt: String,
)

@Serializable
data class Citation(
    @SerialName("chunk_id") val chunkId: String,
    @SerialName("source_id") val sourceId: String,
    val title: String,
    val authority: String,
    val excerpt: String,
    @SerialName("source_kind") val sourceKind: String = "mosque",
    val url: String? = null,
)

@Serializable
data class SermonSegment(
    val id: String,
    val ordinal: Int,
    @SerialName("arabic_text") val arabicText: String,
    @SerialName("translated_text") val translatedText: String? = null,
    @SerialName("verification_status") val verificationStatus: String,
    val issues: List<String> = emptyList(),
    val citations: List<Citation> = emptyList(),
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
