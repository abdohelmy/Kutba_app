package com.khutba.app.ui

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.khutba.app.data.KhutbaRepository
import com.khutba.app.data.userMessage
import com.khutba.app.model.Mosque
import com.khutba.app.model.SermonDetail
import com.khutba.app.model.SermonSummary
import com.khutba.app.model.TrustedSource
import com.khutba.app.model.User
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

enum class Screen {
    LOGIN,
    READER_MOSQUES,
    READER_SERMONS,
    SERMON_DETAIL,
    ADMIN_HOME,
    ADMIN_SERMON,
}

enum class LoginType {
    INDIVIDUAL,
    MOSQUE,
}

data class KhutbaUiState(
    val screen: Screen = Screen.LOGIN,
    val loading: Boolean = false,
    val error: String? = null,
    val user: User? = null,
    val mosques: List<Mosque> = emptyList(),
    val selectedMosque: Mosque? = null,
    val sermons: List<SermonSummary> = emptyList(),
    val sources: List<TrustedSource> = emptyList(),
    val selectedSermon: SermonDetail? = null,
)

class MainViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = KhutbaRepository()
    private val mutableState = MutableStateFlow(KhutbaUiState())
    val state: StateFlow<KhutbaUiState> = mutableState.asStateFlow()

    fun login(email: String, password: String, loginType: LoginType) = launchAction {
        val user = repository.login(email, password)
        val isMosqueAccount = user.role == "MOSQUE_ADMIN" || user.role == "SUPER_ADMIN"
        if (loginType == LoginType.MOSQUE && !isMosqueAccount) {
            repository.logout()
            error("This is an individual account. Select Individual to sign in.")
        }
        if (loginType == LoginType.INDIVIDUAL && isMosqueAccount) {
            repository.logout()
            error("This is a mosque account. Select Mosque to sign in.")
        }
        mutableState.value = mutableState.value.copy(user = user)
        routeAfterAuthentication(user)
    }

    fun register(name: String, email: String, password: String) = launchAction {
        val user = repository.register(name, email, password)
        mutableState.value = mutableState.value.copy(user = user)
        routeAfterAuthentication(user)
    }

    private suspend fun routeAfterAuthentication(user: User) {
        if (user.role == "MOSQUE_ADMIN" || user.role == "SUPER_ADMIN") {
            refreshAdminHome()
        } else {
            mutableState.value = mutableState.value.copy(
                screen = Screen.READER_MOSQUES,
                mosques = repository.mosques(),
            )
        }
    }

    fun logout() {
        repository.logout()
        mutableState.value = KhutbaUiState()
    }

    fun selectMosque(mosque: Mosque, language: String?) = launchAction {
        mutableState.value = mutableState.value.copy(
            selectedMosque = mosque,
            sermons = repository.publishedSermons(mosque.id, language),
            screen = Screen.READER_SERMONS,
        )
    }

    fun openPublishedSermon(sermonId: String) = launchAction {
        mutableState.value = mutableState.value.copy(
            selectedSermon = repository.publishedSermon(sermonId),
            screen = Screen.SERMON_DETAIL,
        )
    }

    fun openAdminSermon(sermonId: String) = launchAction {
        mutableState.value = mutableState.value.copy(
            selectedSermon = repository.adminSermon(sermonId),
            screen = Screen.ADMIN_SERMON,
        )
    }

    fun uploadSource(
        uri: Uri,
        title: String,
        authority: String,
        language: String,
    ) = launchAction {
        repository.uploadSource(
            getApplication<Application>().contentResolver,
            uri,
            title,
            authority,
            language,
        )
        refreshAdminHome()
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

    fun translate(sermonId: String) = launchAction {
        repository.startTranslation(sermonId)
        repeat(60) {
            delay(2_000)
            val sermon = repository.adminSermon(sermonId)
            mutableState.value = mutableState.value.copy(selectedSermon = sermon)
            if (sermon.status != "TRANSLATING") return@launchAction
        }
        error("Translation is still running; reopen the sermon to refresh it")
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

    fun back() {
        val state = mutableState.value
        mutableState.value = state.copy(
            screen = when (state.screen) {
                Screen.READER_SERMONS -> Screen.READER_MOSQUES
                Screen.SERMON_DETAIL -> Screen.READER_SERMONS
                Screen.ADMIN_SERMON -> Screen.ADMIN_HOME
                else -> state.screen
            },
            error = null,
        )
    }

    fun dismissError() {
        mutableState.value = mutableState.value.copy(error = null)
    }

    private suspend fun refreshAdminHome() {
        mutableState.value = mutableState.value.copy(
            sources = repository.sources(),
            sermons = repository.adminSermons(),
            selectedSermon = null,
            screen = Screen.ADMIN_HOME,
        )
    }

    private fun launchAction(block: suspend () -> Unit) {
        viewModelScope.launch {
            mutableState.value = mutableState.value.copy(loading = true, error = null)
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
