package com.khutba.app.data

import com.khutba.app.model.GlossaryContribution

import android.content.ContentResolver
import android.net.Uri
import android.provider.OpenableColumns
import com.khutba.app.BuildConfig
import com.khutba.app.model.LoginRequest
import com.khutba.app.model.MosqueProfileUpdateRequest
import com.khutba.app.model.MosqueGlossaryTermRequest
import com.khutba.app.model.MosqueRegisterRequest
import com.khutba.app.model.PasswordChangeRequest
import com.khutba.app.model.RegisterRequest
import com.khutba.app.model.SegmentReviewRequest
import com.khutba.app.model.SermonDetail
import com.khutba.app.model.SermonSummary
import com.khutba.app.model.SourceTextReviewRequest
import com.khutba.app.model.User
import java.net.ConnectException
import java.net.NoRouteToHostException
import java.net.SocketException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import retrofit2.HttpException

class KhutbaRepository(private val api: KhutbaApi = ApiFactory.api) {
    suspend fun sentenceAlignment(sermonId: String, segmentId: String, text: String) =
        api.sentenceAlignment(authorization(), sermonId, segmentId, mapOf("translated_text" to text))

    private var token: String? = null

    private fun authorization(): String =
        token?.let { "Bearer $it" } ?: error("The user is not authenticated")

    suspend fun login(username: String, password: String, accountType: String): User {
        token = api.login(LoginRequest(username.trim(), password, accountType)).accessToken
        return api.me(authorization())
    }

    suspend fun register(name: String, username: String, password: String): User {
        api.register(RegisterRequest(username.trim(), name.trim(), password))
        return login(username, password, "INDIVIDUAL")
    }

    suspend fun registerMosque(
        mosqueName: String,
        city: String,
        country: String,
        adminDisplayName: String,
        username: String,
        password: String,
        contactEmail: String,
    ): User {
        return api.registerMosque(
            MosqueRegisterRequest(
                mosqueName = mosqueName.trim(),
                city = city.trim(),
                country = country.trim().uppercase(),
                adminDisplayName = adminDisplayName.trim(),
                username = username.trim(),
                password = password,
                contactEmail = contactEmail,
            ),
        )
    }

    fun logout() {
        token = null
    }

    suspend fun mosques() = api.mosques()
    suspend fun liveState(sermonId: String) = api.liveState(sermonId)

    suspend fun publishedSermons(mosqueId: String, language: String?) =
        api.publishedSermons(mosqueId, language?.ifBlank { null })

    suspend fun publishedSermon(sermonId: String) =
        api.publishedSermon(sermonId)

    fun publishedSermonPdfUrl(sermonId: String): Uri =
        Uri.parse(BuildConfig.API_BASE_URL)
            .buildUpon()
            .appendEncodedPath("reader/sermons")
            .appendPath(sermonId)
            .appendPath("pdf")
            .build()

    suspend fun adminSermons() = api.adminSermons(authorization())

    suspend fun adminProfile() = api.adminProfile(authorization())

    suspend fun updateMosqueName(mosqueName: String, city: String) = api.updateAdminProfile(
        authorization(),
        MosqueProfileUpdateRequest(mosqueName.trim(), city.trim()),
    )

    suspend fun changePassword(currentPassword: String, newPassword: String) =
        api.changeAdminPassword(
            authorization(),
            PasswordChangeRequest(currentPassword, newPassword),
        )

    suspend fun adminGlossary() = api.adminGlossary(authorization())

    suspend fun saveGlossaryTerm(
        glossaryTermId: String?,
        arabicTerm: String,
        literalTranslation: String,
        meaning: String,
        arabicVariations: String,
        alternativeContextMeanings: String,
    ) = MosqueGlossaryTermRequest(
        arabicTerm = arabicTerm.trim(),
        meaning = meaning.trim(),
        literalTranslation = literalTranslation.trim(),
        arabicVariations = arabicVariations.trim(),
        alternativeContextMeanings = alternativeContextMeanings.trim(),
    ).let { request ->
        if (glossaryTermId == null) {
            api.createGlossaryTerm(authorization(), request)
        } else {
            api.updateGlossaryTerm(authorization(), glossaryTermId, request)
        }
    }

    suspend fun deleteGlossaryTerm(glossaryTermId: String) =
        api.deleteGlossaryTerm(authorization(), glossaryTermId)

    suspend fun adminSermon(sermonId: String) = api.adminSermon(authorization(), sermonId)

    suspend fun previewSermon(sermonId: String) = api.previewSermon(authorization(), sermonId)

    suspend fun deleteAdminSermon(sermonId: String) =
        api.deleteAdminSermon(authorization(), sermonId)

    suspend fun hideAdminSermon(sermonId: String) =
        api.hideAdminSermon(authorization(), sermonId)

    suspend fun showAdminSermon(sermonId: String) =
        api.showAdminSermon(authorization(), sermonId)

    suspend fun confirmSourceText(sermonId: String, arabicText: String) =
        api.confirmSourceText(
            authorization(),
            sermonId,
            SourceTextReviewRequest(arabicText.trim()),
        )

    suspend fun uploadSermon(
        resolver: ContentResolver,
        uri: Uri,
        title: String,
        khutbaDate: String,
        targetLanguage: String,
    ): SermonSummary = api.uploadSermon(
        authorization(),
        title.textBody(),
        khutbaDate.textBody(),
        targetLanguage.textBody(),
        resolver.documentPart(uri),
    )

    suspend fun startTranslation(sermonId: String) {
        api.translate(authorization(), sermonId)
    }

    suspend fun createDanish(sermonId: String): SermonSummary =
        api.createDanish(authorization(), sermonId)

    suspend fun updateSermonTitle(sermonId: String, title: String) =
        api.updateSermonTitle(authorization(), sermonId, mapOf("title" to title.trim()))

    suspend fun reviewSegment(
        sermonId: String,
        segmentId: String,
        translatedText: String,
        approved: Boolean,
        note: String?,
    ) = api.reviewSegment(
        authorization(),
        sermonId,
        segmentId,
        SegmentReviewRequest(translatedText, approved, note?.ifBlank { null }),
    )

    suspend fun publish(sermonId: String) = api.publish(authorization(), sermonId)

    suspend fun glossaryCandidates(sermonId: String) =
        api.glossaryCandidates(authorization(), sermonId)

    suspend fun contributeGlossary(sermonId: String, request: GlossaryContribution) =
        api.contributeGlossary(authorization(), sermonId, request)

    private fun String.textBody() = trim().toRequestBody("text/plain".toMediaType())

    private fun ContentResolver.documentPart(uri: Uri): MultipartBody.Part {
        val queriedName = query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
            ?.use { cursor ->
                if (cursor.moveToFirst()) cursor.getString(0) else null
            }
        val declaredType = getType(uri)?.lowercase()
        val extension = queriedName?.substringAfterLast('.', missingDelimiterValue = "")?.lowercase()
        val mediaType = when {
            extension == "pdf" -> "application/pdf"
            extension == "docx" -> DOCX_MIME_TYPE
            declaredType == "application/pdf" -> "application/pdf"
            declaredType == DOCX_MIME_TYPE -> DOCX_MIME_TYPE
            else -> error("Choose a PDF or DOCX document")
        }
        val displayName = queriedName ?: if (mediaType == "application/pdf") {
            "document.pdf"
        } else {
            "document.docx"
        }
        val bytes = openInputStream(uri)?.use { it.readBytes() }
            ?: error("The selected document cannot be opened")
        if (bytes.size > MAX_DOCUMENT_BYTES) error("The selected document is larger than 15 MB")
        val body = bytes.toRequestBody(mediaType.toMediaType())
        return MultipartBody.Part.createFormData("file", displayName, body)
    }

    private companion object {
        const val DOCX_MIME_TYPE =
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        const val MAX_DOCUMENT_BYTES = 15 * 1024 * 1024
    }
}

private fun HttpException.serverDetail(): String? {
    val body = response()?.errorBody()?.string() ?: return null
    return runCatching {
        when (val detail = Json.parseToJsonElement(body).jsonObject["detail"]) {
            is JsonPrimitive -> detail.content
            is JsonArray -> detail.joinToString("\n") { issue ->
                val item = issue.jsonObject
                val field = item["loc"]
                    ?.let { it as? JsonArray }
                    ?.lastOrNull()
                    ?.jsonPrimitive
                    ?.content
                val message = item["msg"]?.jsonPrimitive?.content ?: "Invalid value"
                if (field == null) message else "$field: $message"
            }
            else -> null
        }
    }.getOrNull()
}

private const val SERVICE_HOURS =
    "Normal service hours are Friday, 10:00 AM–3:00 PM Copenhagen time. " +
        "Outside these hours the server may be switched off."

fun Throwable.userMessage(): String = when (this) {
    is HttpException -> if (code() in 502..504) {
        "The server is temporarily unavailable (${code()}). If it was just started, " +
            "wait a minute and try again. $SERVICE_HOURS"
    } else {
        serverDetail() ?: "Server rejected the request (${code()}): ${message()}"
    }
    is UnknownHostException ->
        "Cannot resolve the API address. Check your internet connection or DNS and try again. $SERVICE_HOURS"
    is SocketTimeoutException ->
        "The API took too long to respond. Check your connection and try again. $SERVICE_HOURS"
    is ConnectException,
    is NoRouteToHostException,
    is SocketException,
    -> "Cannot connect to the API. Check your internet connection and try again. $SERVICE_HOURS"
    else -> message ?: "Unexpected error"
}
