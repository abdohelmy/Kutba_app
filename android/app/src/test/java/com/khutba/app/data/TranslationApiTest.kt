package com.khutba.app.data

import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory

class TranslationApiTest {
    @Test
    fun translationStartSendsRequestAndDecodesAcknowledgement() = runBlocking {
        var requests = 0
        val client = OkHttpClient.Builder().addInterceptor { chain ->
            val request = chain.request()
            requests++
            assertEquals("POST", request.method)
            assertEquals("/api/v1/admin/sermons/sermon-id/translate", request.url.encodedPath)
            assertEquals("Bearer test-token", request.header("Authorization"))
            Response.Builder()
                .request(request)
                .protocol(Protocol.HTTP_1_1)
                .code(200)
                .message("OK")
                .body("""{"id":"sermon-id","status":"TRANSLATING"}"""
                    .toResponseBody("application/json".toMediaType()))
                .build()
        }.build()
        val api = Retrofit.Builder()
            .baseUrl("https://example.test/api/v1/")
            .client(client)
            .addConverterFactory(Json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(KhutbaApi::class.java)

        val queued = api.translate("Bearer test-token", "sermon-id")
        assertEquals("sermon-id", queued.id)
        assertEquals("TRANSLATING", queued.status)
        assertEquals(1, requests)
    }
}
