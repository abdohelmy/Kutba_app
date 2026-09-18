package com.khutba.app.data

import com.khutba.app.BuildConfig
import com.khutba.app.model.LoginRequest
import com.khutba.app.model.Mosque
import com.khutba.app.model.MosqueGlossaryTerm
import com.khutba.app.model.MosqueGlossaryTermRequest
import com.khutba.app.model.MosqueProfileUpdateRequest
import com.khutba.app.model.MosqueRegisterRequest
import com.khutba.app.model.PasswordChangeRequest
import com.khutba.app.model.RegisterRequest
import com.khutba.app.model.SegmentReviewRequest
import com.khutba.app.model.SermonDetail
import com.khutba.app.model.SermonSegment
import com.khutba.app.model.SermonSummary
import com.khutba.app.model.SourceTextReviewRequest
import com.khutba.app.model.TokenResponse
import com.khutba.app.model.TranslationQueued
import com.khutba.app.model.User
import kotlinx.serialization.json.Json
import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.Multipart
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query
import retrofit2.http.PUT
import okhttp3.MediaType.Companion.toMediaType

interface KhutbaApi {
    @POST("auth/login")
    suspend fun login(@Body request: LoginRequest): TokenResponse

    @POST("auth/register")
    suspend fun register(@Body request: RegisterRequest): User

    @POST("auth/register-mosque")
    suspend fun registerMosque(@Body request: MosqueRegisterRequest): User

    @GET("auth/me")
    suspend fun me(@Header("Authorization") authorization: String): User

    @GET("reader/mosques")
    suspend fun mosques(): List<Mosque>

    @GET("reader/mosques/{mosqueId}/sermons")
    suspend fun publishedSermons(
        @Path("mosqueId") mosqueId: String,
        @Query("language") language: String? = null,
    ): List<SermonSummary>

    @GET("reader/sermons/{sermonId}")
    suspend fun publishedSermon(
        @Path("sermonId") sermonId: String,
    ): SermonDetail

    @GET("admin/sermons")
    suspend fun adminSermons(@Header("Authorization") authorization: String): List<SermonSummary>

    @GET("admin/profile")
    suspend fun adminProfile(@Header("Authorization") authorization: String): Mosque

    @PATCH("admin/profile")
    suspend fun updateAdminProfile(
        @Header("Authorization") authorization: String,
        @Body request: MosqueProfileUpdateRequest,
    ): Mosque

    @PUT("admin/password")
    suspend fun changeAdminPassword(
        @Header("Authorization") authorization: String,
        @Body request: PasswordChangeRequest,
    )

    @GET("admin/glossary")
    suspend fun adminGlossary(
        @Header("Authorization") authorization: String,
    ): List<MosqueGlossaryTerm>

    @POST("admin/glossary")
    suspend fun createGlossaryTerm(
        @Header("Authorization") authorization: String,
        @Body request: MosqueGlossaryTermRequest,
    ): MosqueGlossaryTerm

    @PUT("admin/glossary/{glossaryTermId}")
    suspend fun updateGlossaryTerm(
        @Header("Authorization") authorization: String,
        @Path("glossaryTermId") glossaryTermId: String,
        @Body request: MosqueGlossaryTermRequest,
    ): MosqueGlossaryTerm

    @DELETE("admin/glossary/{glossaryTermId}")
    suspend fun deleteGlossaryTerm(
        @Header("Authorization") authorization: String,
        @Path("glossaryTermId") glossaryTermId: String,
    )

    @Multipart
    @POST("admin/sermons")
    suspend fun uploadSermon(
        @Header("Authorization") authorization: String,
        @Part("title") title: RequestBody,
        @Part("khutba_date") khutbaDate: RequestBody,
        @Part("target_language") targetLanguage: RequestBody,
        @Part file: MultipartBody.Part,
    ): SermonSummary

    @GET("admin/sermons/{sermonId}")
    suspend fun adminSermon(
        @Header("Authorization") authorization: String,
        @Path("sermonId") sermonId: String,
    ): SermonDetail

    @GET("admin/sermons/{sermonId}/preview")
    suspend fun previewSermon(
        @Header("Authorization") authorization: String,
        @Path("sermonId") sermonId: String,
    ): SermonDetail

    @DELETE("admin/sermons/{sermonId}")
    suspend fun deleteAdminSermon(
        @Header("Authorization") authorization: String,
        @Path("sermonId") sermonId: String,
    )

    @POST("admin/sermons/{sermonId}/hide")
    suspend fun hideAdminSermon(
        @Header("Authorization") authorization: String,
        @Path("sermonId") sermonId: String,
    ): SermonSummary

    @POST("admin/sermons/{sermonId}/show")
    suspend fun showAdminSermon(
        @Header("Authorization") authorization: String,
        @Path("sermonId") sermonId: String,
    ): SermonSummary

    @PUT("admin/sermons/{sermonId}/source-text")
    suspend fun confirmSourceText(
        @Header("Authorization") authorization: String,
        @Path("sermonId") sermonId: String,
        @Body request: SourceTextReviewRequest,
    ): SermonDetail

    @POST("admin/sermons/{sermonId}/translate")
    suspend fun translate(
        @Header("Authorization") authorization: String,
        @Path("sermonId") sermonId: String,
    ): TranslationQueued

    @PATCH("admin/sermons/{sermonId}/segments/{segmentId}")
    suspend fun reviewSegment(
        @Header("Authorization") authorization: String,
        @Path("sermonId") sermonId: String,
        @Path("segmentId") segmentId: String,
        @Body request: SegmentReviewRequest,
    ): SermonSegment

    @POST("admin/sermons/{sermonId}/publish")
    suspend fun publish(
        @Header("Authorization") authorization: String,
        @Path("sermonId") sermonId: String,
    )
}

object ApiFactory {
    private val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
    }

    val api: KhutbaApi by lazy {
        Retrofit.Builder()
            .baseUrl(BuildConfig.API_BASE_URL)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(KhutbaApi::class.java)
    }
}
