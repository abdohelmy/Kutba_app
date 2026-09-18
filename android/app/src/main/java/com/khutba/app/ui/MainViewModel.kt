package com.khutba.app.ui

import android.app.Application
import android.app.DownloadManager
import android.content.Context
import android.net.Uri
import android.os.Environment
import android.widget.Toast
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.khutba.app.data.KhutbaRepository
import com.khutba.app.data.ReaderStore
import com.khutba.app.data.userMessage
import com.khutba.app.model.Mosque
import com.khutba.app.model.MosqueGlossaryTerm
import com.khutba.app.model.SermonDetail
import com.khutba.app.model.SermonSummary
import com.khutba.app.model.User
import kotlinx.coroutines.delay
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.isActive
import retrofit2.HttpException
import java.io.IOException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

enum class Screen {
    START,
    MOSQUE_LOGIN,
    MOSQUE_REGISTER,
    READER_MOSQUES,
    READER_SERMONS,
    SERMON_DETAIL,
    ADMIN_HOME,
    ADMIN_SETTINGS,
    ADMIN_SERMON,
    ADMIN_PREVIEW,
}

data class KhutbaUiState(
    val screen: Screen = Screen.START,
    val loading: Boolean = false,
    val translatingSermonId: String? = null,
    val translatedSegments: Int = 0,
    val translationTotalSegments: Int = 0,
    val error: String? = null,
    val notice: String? = null,
    val user: User? = null,
    val adminMosque: Mosque? = null,
    val adminGlossary: List<MosqueGlossaryTerm> = emptyList(),
    val mosques: List<Mosque> = emptyList(),
    val selectedMosque: Mosque? = null,
    val sermons: List<SermonSummary> = emptyList(),
    val selectedSermon: SermonDetail? = null,
    val readerOffline: Boolean = false,
    val readerTextSize: Float = 18f,
    val previewSermon: SermonDetail? = null,
    val translationReconnecting: Boolean = false,
)

class MainViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = KhutbaRepository()
    private val readerStore = ReaderStore(application)
    private var translationJob: Job? = null
    private var translationMonitor = 0
    private val mutableState = MutableStateFlow(KhutbaUiState())
    val state: StateFlow<KhutbaUiState> = mutableState.asStateFlow()

    fun openMosqueLogin() {
        mutableState.value = mutableState.value.copy(screen = Screen.MOSQUE_LOGIN, error = null)
    }

    fun openMosqueRegistration() {
        mutableState.value = mutableState.value.copy(screen = Screen.MOSQUE_REGISTER, error = null)
    }

    fun continueAsIndividual() = launchAction {
        translationJob?.cancel()
        repository.logout()
        val mosques = loadMosques()
        mutableState.value = mutableState.value.copy(
            user = null,
            mosques = mosques,
            readerTextSize = readerStore.textSize,
            screen = Screen.READER_MOSQUES,
        )
        readerStore.preferredMosque?.let { preferred ->
            mosques.firstOrNull { it.id == preferred.id }?.let { loadMosque(it) }
        }
    }

    fun login(username: String, password: String) = launchAction {
        val user = repository.login(username, password, "MOSQUE")
        val isMosqueAccount = user.role == "MOSQUE_ADMIN" || user.role == "SUPER_ADMIN"
        if (!isMosqueAccount) {
            repository.logout()
            error("This account does not have access to a mosque workspace.")
        }
        mutableState.value = mutableState.value.copy(user = user)
        refreshAdminHome()
    }

    fun registerMosque(
        mosqueName: String,
        city: String,
        country: String,
        adminDisplayName: String,
        username: String,
        password: String,
        permissionPassword: String,
    ) = launchAction {
        val user = repository.registerMosque(
            mosqueName,
            city,
            country,
            adminDisplayName,
            username,
            password,
            permissionPassword,
        )
        mutableState.value = mutableState.value.copy(user = user)
        refreshAdminHome()
    }

    fun logout() {
        translationJob?.cancel()
        repository.logout()
        mutableState.value = KhutbaUiState()
    }

    fun openAdminSettings() = launchAction {
        mutableState.value = mutableState.value.copy(
            adminGlossary = repository.adminGlossary(),
            screen = Screen.ADMIN_SETTINGS,
        )
    }

    fun updateMosqueName(mosqueName: String) = launchAction {
        val mosque = repository.updateMosqueName(mosqueName)
        mutableState.value = mutableState.value.copy(
            adminMosque = mosque,
            notice = "Mosque name updated",
        )
    }

    fun changePassword(currentPassword: String, newPassword: String) = launchAction {
        repository.changePassword(currentPassword, newPassword)
        mutableState.value = mutableState.value.copy(notice = "Password updated")
    }

    fun saveGlossaryTerm(
        glossaryTermId: String?,
        arabicTerm: String,
        literalTranslation: String,
        meaning: String,
        arabicVariations: String,
        alternativeContextMeanings: String,
    ) = launchAction {
        repository.saveGlossaryTerm(
            glossaryTermId,
            arabicTerm,
            literalTranslation,
            meaning,
            arabicVariations,
            alternativeContextMeanings,
        )
        mutableState.value = mutableState.value.copy(
            adminGlossary = repository.adminGlossary(),
            notice = if (glossaryTermId == null) "Glossary term added" else "Glossary term updated",
        )
    }

    fun deleteGlossaryTerm(glossaryTermId: String) = launchAction {
        repository.deleteGlossaryTerm(glossaryTermId)
        mutableState.value = mutableState.value.copy(
            adminGlossary = repository.adminGlossary(),
            notice = "Glossary term removed",
        )
    }

    fun selectMosque(mosque: Mosque, language: String?) = launchAction { loadMosque(mosque) }

    private suspend fun loadMosque(mosque: Mosque) {
        val sermons = readerRequest(
            fetch = { repository.publishedSermons(mosque.id, null) },
            cached = { readerStore.sermons(mosque.id) },
            save = { readerStore.saveSermons(mosque.id, it) },
        )
        readerStore.preferredMosque = mosque
        mutableState.value = mutableState.value.copy(
            selectedMosque = mosque,
            sermons = sermons,
            screen = Screen.READER_SERMONS,
        )
    }

    private suspend fun loadMosques() = readerRequest(
        fetch = { repository.mosques() },
        cached = { readerStore.mosques() },
        save = { readerStore.saveMosques(it) },
    )

    private suspend fun <T> readerRequest(
        fetch: suspend () -> T, cached: suspend () -> T?, save: suspend (T) -> Unit,
    ): T {
        val value = try { fetch() } catch (error: Exception) {
            if (error is CancellationException) throw error
            if (error is IOException || (error is HttpException && error.code() in 500..599)) {
                cached()?.let {
                    mutableState.value = mutableState.value.copy(readerOffline = true)
                    return it
                }
            }
            throw error
        }
        try { save(value) } catch (error: IOException) { /* Online reading still works if storage is full. */ }
        mutableState.value = mutableState.value.copy(readerOffline = false)
        return value
    }

    fun refreshReader() = launchAction {
        when (mutableState.value.screen) {
            Screen.READER_MOSQUES -> {
                val value = loadMosques()
                mutableState.value = mutableState.value.copy(mosques = value)
            }
            Screen.READER_SERMONS -> mutableState.value.selectedMosque?.let { loadMosque(it) }
            else -> Unit
        }
    }

    fun setReaderTextSize(size: Float) {
        readerStore.textSize = size
        mutableState.value = mutableState.value.copy(readerTextSize = readerStore.textSize)
    }
    fun readerPosition(id: String) = readerStore.position(id)
    fun saveReaderPosition(id: String, index: Int, offset: Int) = readerStore.savePosition(id, index, offset)

    fun openPublishedSermon(sermonId: String) = launchAction {
        val sermon = readerRequest(
                fetch = {
                    try { repository.publishedSermon(sermonId) } catch (error: HttpException) {
                        if (error.code() == 404) readerStore.removeSermon(sermonId)
                        throw error
                    }
                },
                cached = { readerStore.sermon(sermonId) },
                save = { readerStore.saveSermon(it) },
            )
        mutableState.value = mutableState.value.copy(
            selectedSermon = sermon,
            screen = Screen.SERMON_DETAIL,
        )
    }

    fun downloadPublishedSermon() {
        val sermon = mutableState.value.selectedSermon ?: return
        try {
            val safeTitle = sermon.title
                .replace(Regex("[^A-Za-z0-9._-]+"), "-")
                .trim('-')
                .ifBlank { "khutba" }
            val fileName = "$safeTitle-${sermon.khutbaDate}.pdf"
            val application = getApplication<Application>()
            val request = DownloadManager.Request(repository.publishedSermonPdfUrl(sermon.id))
                .setTitle(sermon.title)
                .setDescription("Downloading the reviewed English khutba")
                .setMimeType("application/pdf")
                .setAllowedOverMetered(true)
                .setAllowedOverRoaming(true)
                .setNotificationVisibility(
                    DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED
                )
                .setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, fileName)
            val manager = application.getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
            manager.enqueue(request)
            Toast.makeText(application, "PDF download started", Toast.LENGTH_SHORT).show()
        } catch (error: Throwable) {
            mutableState.value = mutableState.value.copy(error = error.userMessage())
        }
    }

    fun openAdminSermon(sermonId: String) = launchAction {
        val sermon = repository.adminSermon(sermonId)
        mutableState.value = mutableState.value.copy(
            selectedSermon = sermon,
            screen = Screen.ADMIN_SERMON,
        )
        if (sermon.status == "TRANSLATING") trackTranslation(sermonId, false)
    }

    fun previewSermon() = launchAction {
        val id = mutableState.value.selectedSermon?.id ?: return@launchAction
        mutableState.value = mutableState.value.copy(
            previewSermon = repository.previewSermon(id), screen = Screen.ADMIN_PREVIEW,
        )
    }

    fun uploadSermon(
        uri: Uri,
        title: String,
        khutbaDate: String,
        targetLanguage: String,
    ) = launchAction {
        val sermon = repository.uploadSermon(
            getApplication<Application>().contentResolver,
            uri,
            title,
            khutbaDate,
            targetLanguage,
        )
        mutableState.value = mutableState.value.copy(
            selectedSermon = repository.adminSermon(sermon.id),
            screen = Screen.ADMIN_SERMON,
        )
    }

    fun confirmSourceText(sermonId: String, arabicText: String) = launchAction {
        mutableState.value = mutableState.value.copy(
            selectedSermon = repository.confirmSourceText(sermonId, arabicText),
        )
    }

    fun translate(sermonId: String) = trackTranslation(sermonId, true)

    private fun trackTranslation(sermonId: String, start: Boolean) {
        if (translationJob?.isActive == true && mutableState.value.translatingSermonId == sermonId) return
        translationJob?.cancel()
        val monitor = ++translationMonitor
        translationJob = viewModelScope.launch {
            val initialSermon = mutableState.value.selectedSermon
            mutableState.value = mutableState.value.copy(
                translatingSermonId = sermonId,
                translatedSegments = initialSermon?.segments?.count { !it.translatedText.isNullOrBlank() } ?: 0,
                translationTotalSegments = initialSermon
                    ?.takeIf { it.id == sermonId }
                    ?.segments
                    ?.size
                    ?: 0,
                error = null,
            )
            try {
                if (start) {
                    try { repository.startTranslation(sermonId) } catch (error: Exception) {
                        if (error is CancellationException) throw error
                        // A lost POST response does not mean the server failed to start.
                        if (error is IOException || (error is HttpException && error.code() in 500..599)) {
                            mutableState.value = mutableState.value.copy(translationReconnecting = true)
                        } else if (error !is HttpException || error.code() != 409) throw error
                    }
                }
                var failures = 0
                while (isActive) {
                    delay(if (failures > 0) 10_000 else 2_000)
                    val sermon = try { repository.adminSermon(sermonId) } catch (error: Exception) {
                        if (error is CancellationException) throw error
                        if (error is IOException || (error is HttpException && error.code() in 500..599)) {
                            failures++
                            mutableState.value = mutableState.value.copy(translationReconnecting = true)
                            continue
                        }
                        throw error
                    }
                    failures = 0
                    mutableState.value = mutableState.value.copy(
                        selectedSermon = if (mutableState.value.selectedSermon?.id == sermonId) sermon else mutableState.value.selectedSermon,
                        translationReconnecting = false,
                        translatedSegments = sermon.segments.count {
                            !it.translatedText.isNullOrBlank()
                        },
                        translationTotalSegments = sermon.segments.size,
                    )
                    if (sermon.status != "TRANSLATING") return@launch
                }
            } catch (error: CancellationException) {
                throw error
            } catch (error: Exception) {
                mutableState.value = mutableState.value.copy(error = error.userMessage())
            } finally {
                if (translationMonitor == monitor) {
                    mutableState.value = mutableState.value.copy(
                        translatingSermonId = null,
                        translatedSegments = 0,
                        translationTotalSegments = 0,
                        translationReconnecting = false,
                    )
                }
            }
        }
    }

    fun reviewSegment(
        sermonId: String,
        segmentId: String,
        translatedText: String,
        approved: Boolean,
        note: String?,
    ) = launchAction {
        repository.reviewSegment(
            sermonId,
            segmentId,
            translatedText,
            approved,
            note,
        )
        mutableState.value = mutableState.value.copy(
            selectedSermon = repository.adminSermon(sermonId)
        )
    }

    fun publish(sermonId: String) = launchAction {
        repository.publish(sermonId)
        refreshAdminHome()
    }

    fun deleteSermon(sermonId: String) = launchAction {
        repository.deleteAdminSermon(sermonId)
        refreshAdminHome()
    }

    fun setSermonHidden(sermonId: String, hidden: Boolean) = launchAction {
        if (hidden) {
            repository.hideAdminSermon(sermonId)
        } else {
            repository.showAdminSermon(sermonId)
        }
        refreshAdminHome()
    }

    fun back() {
        val state = mutableState.value
        mutableState.value = state.copy(
            screen = when (state.screen) {
                Screen.MOSQUE_LOGIN -> Screen.START
                Screen.MOSQUE_REGISTER -> Screen.MOSQUE_LOGIN
                Screen.READER_MOSQUES -> Screen.START
                Screen.READER_SERMONS -> Screen.READER_MOSQUES
                Screen.SERMON_DETAIL -> Screen.READER_SERMONS
                Screen.ADMIN_SERMON -> Screen.ADMIN_HOME
                Screen.ADMIN_SETTINGS -> Screen.ADMIN_HOME
                Screen.ADMIN_PREVIEW -> Screen.ADMIN_SERMON
                else -> state.screen
            },
            error = null,
        )
    }

    fun dismissError() {
        mutableState.value = mutableState.value.copy(error = null)
    }

    fun dismissNotice() {
        mutableState.value = mutableState.value.copy(notice = null)
    }

    private suspend fun refreshAdminHome() {
        val mosque = mutableState.value.user?.mosqueId?.let { repository.adminProfile() }
        mutableState.value = mutableState.value.copy(
            adminMosque = mosque,
            sermons = repository.adminSermons(),
            selectedSermon = null,
            screen = Screen.ADMIN_HOME,
        )
    }

    private fun launchAction(block: suspend () -> Unit) {
        viewModelScope.launch {
            mutableState.value = mutableState.value.copy(
                loading = true,
                error = null,
                notice = null,
            )
            try {
                block()
            } catch (error: Throwable) {
                mutableState.value = mutableState.value.copy(error = error.userMessage())
            } finally {
                mutableState.value = mutableState.value.copy(loading = false)
            }
        }
    }
}
