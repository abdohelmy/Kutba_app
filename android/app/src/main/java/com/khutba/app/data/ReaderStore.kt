package com.khutba.app.data

import android.content.Context
import android.util.AtomicFile
import com.khutba.app.model.Mosque
import com.khutba.app.model.SermonDetail
import com.khutba.app.model.SermonSummary
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

/** Only public reader responses go here; admin drafts and credentials are never cached. */
class ReaderStore(context: Context) {
    private val directory = File(context.filesDir, "reader-v1").apply { mkdirs() }
    private val preferences = context.getSharedPreferences("reader-preferences", Context.MODE_PRIVATE)
    private val json = Json { ignoreUnknownKeys = true }

    private fun file(key: String) = AtomicFile(File(directory, "$key.json"))
    private suspend inline fun <reified T> read(key: String): T? = withContext(Dispatchers.IO) {
        runCatching { json.decodeFromString<T>(file(key).openRead().bufferedReader().use { it.readText() }) }.getOrNull()
    }
    private suspend inline fun <reified T> write(key: String, value: T) = withContext(Dispatchers.IO) {
        val target = file(key)
        val stream = target.startWrite()
        try {
            stream.write(json.encodeToString(value).toByteArray())
            target.finishWrite(stream)
        } catch (error: Exception) {
            target.failWrite(stream)
            throw error
        }
    }

    suspend fun mosques(): List<Mosque>? = read("mosques")
    suspend fun saveMosques(value: List<Mosque>) = write("mosques", value)
    suspend fun sermons(mosqueId: String): List<SermonSummary>? = read("list-$mosqueId")
    suspend fun saveSermons(mosqueId: String, value: List<SermonSummary>) {
        // A successful refresh withdraws previously saved copies that are no longer published.
        val removed = sermons(mosqueId).orEmpty().map { it.id }.toSet() - value.map { it.id }.toSet()
        withContext(Dispatchers.IO) { removed.forEach { file("sermon-$it").delete() } }
        write("list-$mosqueId", value)
    }
    suspend fun sermon(id: String): SermonDetail? = read("sermon-$id")
    suspend fun saveSermon(value: SermonDetail) = write("sermon-${value.id}", value)
    suspend fun removeSermon(id: String) = withContext(Dispatchers.IO) { file("sermon-$id").delete() }

    var preferredMosque: Mosque?
        get() = preferences.getString("mosque", null)?.let { runCatching { json.decodeFromString<Mosque>(it) }.getOrNull() }
        set(value) { preferences.edit().putString("mosque", value?.let { json.encodeToString(it) }).apply() }
    var textSize: Float
        get() = preferences.getFloat("text-size", 18f).coerceIn(16f, 28f)
        set(value) { preferences.edit().putFloat("text-size", value.coerceIn(16f, 28f)).apply() }
    fun position(id: String): Pair<Int, Int> = preferences.getInt("$id-index", 0) to preferences.getInt("$id-offset", 0)
    fun savePosition(id: String, index: Int, offset: Int) {
        preferences.edit().putInt("$id-index", index).putInt("$id-offset", offset).apply()
    }
}
