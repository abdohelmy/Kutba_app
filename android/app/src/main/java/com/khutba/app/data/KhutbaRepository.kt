package com.khutba.app.data

import android.content.ContentResolver
import android.net.Uri
import android.provider.OpenableColumns
import com.khutba.app.model.LoginRequest
import com.khutba.app.model.RegisterRequest
import com.khutba.app.model.SegmentReviewRequest
import com.khutba.app.model.SermonDetail
import com.khutba.app.model.SermonSummary
import com.khutba.app.model.SourceTextReviewRequest
import com.khutba.app.model.User
import java.net.ConnectException
import java.net.SocketTimeoutException
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
    private var token: String? = null

    private fun authorization(): String =
        token?.let { "Bearer $it" } ?: error("The user is not authenticated")

    suspend fun login(email: String, password: String): User {
        token = api.login(LoginRequest(email.trim(), password)).accessToken
        return api.me(authorization())
    }

    suspend fun register(name: String, email: String, password: String): User {
        api.register(RegisterRequest(email.trim(), name.trim(), password))
        return login(email, password)
    }

    fun logout() {
        token = null
    }

    suspend fun mosques() = api.mosques(authorization())

    suspend fun publishedSermons(mosqueId: String, language: String?) =
        api.publishedSermons(authorization(), mosqueId, language?.ifBlank { null })

    suspend fun publishedSermon(sermonId: String) =
        api.publishedSermon(authorization(), sermonId)

    suspend fun sources() = api.sources(authorization())

    suspend fun adminSermons() = api.adminSermons(authorization())

    suspend fun adminSermon(sermonId: String) = api.adminSermon(authorization(), sermonId)

    suspend fun confirmSourceText(sermonId: String, arabicText: String) =
        api.confirmSourceText(
            authorization(),
            sermonId,
            SourceTextReviewRequest(arabicText.trim()),
        )

    suspend fun uploadSource(
        resolver: ContentResolver,
        uri: Uri,
        title: String,
        authority: String,
        language: String,
    ) = api.uploadSource(
        authorization(),
        title.textBody(),
        authority.textBody(),
        language.textBody(),
        resolver.documentPart(uri),
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

fun Throwable.userMessage(): String = when (this) {
    is HttpException -> serverDetail() ?: "Server rejected the request (${code()}): ${message()}"
    is ConnectException -> "Cannot reach the Khutba API. Start the backend server and try again."
    is SocketTimeoutException -> "The Khutba API took too long to respond. Please try again."
    else -> message ?: "Unexpected error"
}
