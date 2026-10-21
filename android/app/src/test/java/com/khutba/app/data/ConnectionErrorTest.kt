package com.khutba.app.data

import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response

class ConnectionErrorTest {
    @Test fun dnsFailureIsNotReportedAsScheduledShutdown() {
        val message = UnknownHostException().userMessage()
        assertTrue(message.startsWith("Cannot resolve the API address"))
        assertTrue(message.contains("Copenhagen time"))
    }

    @Test fun connectionFailureOffersConnectionAdvice() {
        assertTrue(ConnectException().userMessage().startsWith("Cannot connect to the API"))
    }

    @Test fun timeoutIsIdentified() {
        assertTrue(SocketTimeoutException().userMessage().contains("too long to respond"))
    }

    @Test fun gatewayFailureSuggestsRetryAfterStartup() {
        val response = Response.error<Unit>(502, "".toResponseBody("text/plain".toMediaType()))
        val message = HttpException(response).userMessage()
        assertTrue(message.contains("(502)"))
        assertTrue(message.contains("wait a minute"))
    }
}
