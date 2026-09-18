package com.khutba.app.ui

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.BackHandler
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.InlineTextContent
import androidx.compose.foundation.text.appendInlineContent
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.automirrored.filled.MenuBook
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.automirrored.filled.OpenInNew
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.UploadFile
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Slider
import androidx.compose.material3.FilterChip
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.snapshotFlow
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.Placeholder
import androidx.compose.ui.text.PlaceholderVerticalAlign
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.flow.distinctUntilChanged
import com.khutba.app.model.Citation
import com.khutba.app.model.GlossaryTerm
import com.khutba.app.model.Mosque
import com.khutba.app.model.MosqueGlossaryTerm
import com.khutba.app.model.SermonDetail
import com.khutba.app.model.SermonSegment
import com.khutba.app.model.SermonSummary
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.time.temporal.TemporalAdjusters
import java.util.Locale

private val SupportedDocumentMimeTypes = arrayOf(
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun KhutbaApp(state: KhutbaUiState, viewModel: MainViewModel) {
    BackHandler(enabled = state.screen !in listOf(Screen.START, Screen.ADMIN_HOME) && !state.loading) { viewModel.back() }
    Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        when (state.screen) {
            Screen.START -> StartScreen(
                onIndividual = viewModel::continueAsIndividual,
                onMosque = viewModel::openMosqueLogin,
            )
            Screen.MOSQUE_LOGIN -> MosqueLoginScreen(
                onLogin = viewModel::login,
                onCreateProfile = viewModel::openMosqueRegistration,
                onBack = viewModel::back,
            )
            Screen.MOSQUE_REGISTER -> MosqueRegisterScreen(
                onRegister = viewModel::registerMosque,
                onBack = viewModel::back,
            )
            Screen.READER_MOSQUES -> PullToRefreshBox(isRefreshing = state.loading, onRefresh = viewModel::refreshReader) { MosqueListScreen(
                mosques = state.mosques,
                onSelect = viewModel::selectMosque,
                onExit = viewModel::logout,
                offline = state.readerOffline,
            ) }
            Screen.READER_SERMONS -> PullToRefreshBox(isRefreshing = state.loading, onRefresh = viewModel::refreshReader) { SermonListScreen(
                mosque = state.selectedMosque,
                sermons = state.sermons,
                onSelect = viewModel::openPublishedSermon,
                onBack = viewModel::back,
                offline = state.readerOffline,
            ) }
            Screen.SERMON_DETAIL -> ReaderSermonScreen(
                sermon = state.selectedSermon,
                onDownload = viewModel::downloadPublishedSermon,
                onBack = viewModel::back,
                viewModel = viewModel,
                offline = state.readerOffline,
                textSize = state.readerTextSize,
            )
            Screen.ADMIN_PREVIEW -> ReaderSermonScreen(
                sermon = state.previewSermon, onDownload = {}, onBack = viewModel::back,
                viewModel = viewModel, textSize = state.readerTextSize, preview = true,
            )
            Screen.ADMIN_HOME -> AdminHomeScreen(state, viewModel)
            Screen.ADMIN_SETTINGS -> AdminSettingsScreen(state, viewModel)
            Screen.ADMIN_SERMON -> AdminSermonScreen(state, viewModel)
        }
        if (state.loading && state.screen !in listOf(Screen.READER_MOSQUES, Screen.READER_SERMONS)) {
            Box(
                Modifier.fillMaxSize().background(MaterialTheme.colorScheme.scrim.copy(alpha = 0.25f)),
                contentAlignment = Alignment.Center,
            ) {
                CircularProgressIndicator()
            }
        }
    }
    state.error?.let { message ->
        val scheduledOffline = message.startsWith("The Khutba app is available every Friday")
        AlertDialog(
            onDismissRequest = viewModel::dismissError,
            confirmButton = {
                TextButton(onClick = viewModel::dismissError) { Text("OK") }
            },
            title = { Text(if (scheduledOffline) "Service currently offline" else "Request failed") },
            text = { Text(message) },
        )
    }
    state.notice?.let { message ->
        AlertDialog(
            onDismissRequest = viewModel::dismissNotice,
            confirmButton = {
                TextButton(onClick = viewModel::dismissNotice) { Text("OK") }
            },
            title = { Text("Saved") },
            text = { Text(message) },
        )
    }
}

@Composable
private fun StartScreen(onIndividual: () -> Unit, onMosque: () -> Unit) {
    val gradient = if (isSystemInDarkTheme()) {
        listOf(Color(0xFF063D2E), Color(0xFF101512))
    } else {
        listOf(Color(0xFF064C38), Color(0xFF0B7454), MaterialTheme.colorScheme.background)
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize().background(Brush.verticalGradient(gradient)),
        contentPadding = PaddingValues(start = 22.dp, top = 54.dp, end = 22.dp, bottom = 30.dp),
    ) {
        item {
            Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.fillMaxWidth()) {
                Box(
                    modifier = Modifier
                        .size(72.dp)
                        .background(Color.White.copy(alpha = 0.16f), CircleShape),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        Icons.AutoMirrored.Filled.MenuBook,
                        contentDescription = null,
                        tint = Color.White,
                        modifier = Modifier.size(38.dp),
                    )
                }
                Spacer(Modifier.height(18.dp))
                Text("Khutba", style = MaterialTheme.typography.displaySmall, color = Color.White)
                Text(
                    "Faithful translations. Reviewed by your mosque.",
                    style = MaterialTheme.typography.bodyLarge,
                    color = Color.White.copy(alpha = 0.82f),
                    textAlign = TextAlign.Center,
                )
            }
        }
        item { Spacer(Modifier.height(34.dp)) }
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(30.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                elevation = CardDefaults.cardElevation(defaultElevation = 8.dp),
            ) {
                Column(
                    Modifier.padding(horizontal = 20.dp, vertical = 24.dp),
                    verticalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    Text("How would you like to continue?", style = MaterialTheme.typography.headlineSmall)
                    Text(
                        "Readers can enter immediately. Mosque teams sign in to manage khutbas.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    StartRoleOption(
                        title = "Individual",
                        description = "Choose a mosque and read reviewed khutbas",
                        icon = Icons.Default.Person,
                        onClick = onIndividual,
                    )
                    StartRoleOption(
                        title = "Mosque",
                        description = "Upload, review, publish, and remove khutbas",
                        icon = Icons.Default.Home,
                        onClick = onMosque,
                    )
                }
            }
        }
    }
}

@Composable
private fun StartRoleOption(
    title: String,
    description: String,
    icon: ImageVector,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.clickable(onClick = onClick),
        shape = RoundedCornerShape(18.dp),
        color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.65f),
        border = BorderStroke(1.5.dp, MaterialTheme.colorScheme.primary),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(18.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Surface(shape = CircleShape, color = MaterialTheme.colorScheme.primary) {
                Icon(
                    icon,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onPrimary,
                    modifier = Modifier.padding(12.dp).size(28.dp),
                )
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Text(title, style = MaterialTheme.typography.titleLarge)
                Text(
                    description,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MosqueLoginScreen(
    onLogin: (String, String) -> Unit,
    onCreateProfile: () -> Unit,
    onBack: () -> Unit,
) {
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    val usernameIsValid = username.trim().matches(Regex("[A-Za-z0-9._-]{3,64}"))
    AppScaffold(title = "Mosque sign in", onBack = onBack) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).padding(22.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("Manage your mosque’s khutbas", style = MaterialTheme.typography.headlineSmall)
            Text(
                "Sign in to an existing account or create a new mosque profile.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            OutlinedTextField(
                value = username,
                onValueChange = { username = it },
                label = { Text("Username") },
                isError = username.isNotBlank() && !usernameIsValid,
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = password,
                onValueChange = { password = it },
                label = { Text("Password") },
                visualTransformation = PasswordVisualTransformation(),
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            Button(
                onClick = { onLogin(username, password) },
                enabled = usernameIsValid && password.isNotEmpty(),
                modifier = Modifier.fillMaxWidth().height(54.dp),
            ) {
                Text("Sign in to mosque workspace", fontWeight = FontWeight.SemiBold)
            }
            HorizontalDivider()
            OutlinedButton(
                onClick = onCreateProfile,
                modifier = Modifier.fillMaxWidth().height(54.dp),
            ) {
                Text("Create a mosque profile")
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MosqueRegisterScreen(
    onRegister: (String, String, String, String, String, String, String) -> Unit,
    onBack: () -> Unit,
) {
    var mosqueName by remember { mutableStateOf("") }
    var city by remember { mutableStateOf("") }
    var country by remember { mutableStateOf("DK") }
    var adminDisplayName by remember { mutableStateOf("") }
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var permissionPassword by remember { mutableStateOf("") }
    val usernameIsValid = username.trim().matches(Regex("[A-Za-z0-9._-]{3,64}"))
    val countryIsValid = country.trim().matches(Regex("[A-Za-z]{2}"))
    val formIsValid = mosqueName.trim().length >= 2 &&
        city.trim().length >= 2 &&
        countryIsValid &&
        adminDisplayName.trim().length >= 2 &&
        usernameIsValid &&
        password.length >= 6 &&
        permissionPassword.isNotEmpty()

    AppScaffold(title = "Create mosque profile", onBack = onBack) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(22.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            item {
                SectionTitle(
                    "Set up your mosque workspace",
                    "The permission password is required before the profile can be created.",
                )
            }
            item {
                OutlinedTextField(
                    value = mosqueName,
                    onValueChange = { mosqueName = it },
                    label = { Text("Mosque name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            item {
                OutlinedTextField(
                    value = city,
                    onValueChange = { city = it },
                    label = { Text("City") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            item {
                OutlinedTextField(
                    value = country,
                    onValueChange = { country = it.take(2) },
                    label = { Text("Country code") },
                    supportingText = { Text("Two letters, for example DK") },
                    isError = country.isNotBlank() && !countryIsValid,
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            item {
                OutlinedTextField(
                    value = adminDisplayName,
                    onValueChange = { adminDisplayName = it },
                    label = { Text("Administrator name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            item {
                OutlinedTextField(
                    value = username,
                    onValueChange = { username = it },
                    label = { Text("Username") },
                    supportingText = { Text("3–64 letters, numbers, dots, dashes, or underscores") },
                    isError = username.isNotBlank() && !usernameIsValid,
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            item {
                OutlinedTextField(
                    value = password,
                    onValueChange = { password = it },
                    label = { Text("Account password") },
                    supportingText = { Text("At least 6 characters") },
                    visualTransformation = PasswordVisualTransformation(),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            item {
                OutlinedTextField(
                    value = permissionPassword,
                    onValueChange = { permissionPassword = it },
                    label = { Text("Permission password") },
                    visualTransformation = PasswordVisualTransformation(),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            item {
                Button(
                    onClick = {
                        onRegister(
                            mosqueName,
                            city,
                            country,
                            adminDisplayName,
                            username,
                            password,
                            permissionPassword,
                        )
                    },
                    enabled = formIsValid,
                    modifier = Modifier.fillMaxWidth().height(54.dp),
                ) {
                    Text("Create mosque profile", fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MosqueListScreen(
    mosques: List<Mosque>,
    onSelect: (Mosque, String?) -> Unit,
    onExit: () -> Unit,
    offline: Boolean = false,
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Choose your mosque") },
                actions = {
                    IconButton(onClick = onExit) {
                        Icon(Icons.AutoMirrored.Filled.Logout, contentDescription = "Return to start")
                    }
                },
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(18.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Find your community", style = MaterialTheme.typography.headlineSmall)
                    Text(
                        "Choose a mosque to read its reviewed Friday khutbas.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            if (offline) item { OfflineReaderNote() }
            items(mosques, key = { it.id }) { mosque ->
                Card(
                    onClick = { onSelect(mosque, null) },
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                ) {
                    Row(
                        Modifier.padding(18.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(14.dp),
                    ) {
                        Box(
                            Modifier.size(48.dp).background(
                                MaterialTheme.colorScheme.primaryContainer,
                                CircleShape,
                            ),
                            contentAlignment = Alignment.Center,
                        ) {
                            Icon(
                                Icons.Default.Home,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.primary,
                            )
                        }
                        Column {
                            Text(mosque.name, style = MaterialTheme.typography.titleLarge)
                            Text(
                                "${mosque.city}, ${mosque.country}",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SermonListScreen(
    mosque: Mosque?,
    sermons: List<SermonSummary>,
    onSelect: (String) -> Unit,
    onBack: () -> Unit,
    offline: Boolean = false,
) {
    val today = LocalDate.now()
    val sections = remember(sermons, today) { sermonDateSections(sermons, today) }
    val weekStart = today.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))
    val weekEnd = weekStart.plusDays(6)
    AppScaffold(title = mosque?.name ?: "Sermons", onBack = onBack) { padding ->
        LazyColumn(
            Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (offline) item { OfflineReaderNote() }
            item {
                SectionTitle(
                    "This week's khutba",
                    "${shortDate(weekStart)} – ${shortDate(weekEnd)}",
                )
            }
            if (sections.thisWeek.isEmpty()) item {
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.primaryContainer,
                    ),
                ) {
                    Text(
                        "No khutba has been published for this week yet.",
                        modifier = Modifier.padding(20.dp),
                        color = MaterialTheme.colorScheme.onPrimaryContainer,
                    )
                }
            }
            items(sections.thisWeek, key = { "week-${it.id}" }) { sermon ->
                SermonCard(sermon, onClick = { onSelect(sermon.id) })
            }
            if (sections.upcoming.isNotEmpty()) {
                item { SectionTitle("Upcoming khutbas") }
                items(sections.upcoming, key = { "upcoming-${it.id}" }) { sermon ->
                    SermonCard(sermon, onClick = { onSelect(sermon.id) })
                }
            }
            sections.archive.forEach { (heading, sectionSermons) ->
                item(key = "heading-$heading") { SectionTitle(heading) }
                items(sectionSermons, key = { "archive-${it.id}" }) { sermon ->
                    SermonCard(sermon, onClick = { onSelect(sermon.id) })
                }
            }
        }
    }
}

@Composable
private fun OfflineReaderNote() {
    Text(
        "Offline · Saved copies. Connect and pull down to refresh. Source websites require internet.",
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        style = MaterialTheme.typography.bodySmall,
        modifier = Modifier.padding(vertical = 8.dp),
    )
}

@Composable
private fun ReaderSermonScreen(
    sermon: SermonDetail?,
    onDownload: () -> Unit,
    onBack: () -> Unit,
    viewModel: MainViewModel,
    offline: Boolean = false,
    textSize: Float = 18f,
    preview: Boolean = false,
) {
    if (sermon == null) return
    var selectedCitation by remember(sermon.id) { mutableStateOf<Citation?>(null) }
    var selectedGlossaryTerm by remember(sermon.id) { mutableStateOf<GlossaryTerm?>(null) }
    var query by rememberSaveable(sermon.id) { mutableStateOf("") }
    var matchIndex by rememberSaveable(sermon.id) { mutableStateOf(0) }
    val savedPosition = remember(sermon.id) { if (preview) 0 to 0 else viewModel.readerPosition(sermon.id) }
    val listState = rememberLazyListState(savedPosition.first.coerceIn(0, sermon.segments.size), savedPosition.second.coerceAtLeast(0))
    val matches = remember(query, sermon.segments) {
        if (query.isBlank()) emptyList() else sermon.segments.mapIndexedNotNull { index, segment ->
            if (sanitizedReaderText(segment.translatedText.orEmpty()).contains(query.trim(), ignoreCase = true)) index else null
        }
    }
    LaunchedEffect(query) { matchIndex = 0 }
    LaunchedEffect(matches, matchIndex) {
        matches.getOrNull(matchIndex)?.let { listState.animateScrollToItem(it + 1) }
    }
    LaunchedEffect(sermon.id, listState, query) {
        if (!preview && query.isBlank()) {
            snapshotFlow { listState.firstVisibleItemIndex to listState.firstVisibleItemScrollOffset }
                .distinctUntilChanged().collect { (index, offset) ->
                    viewModel.saveReaderPosition(sermon.id, index, offset)
                }
        }
    }
    AppScaffold(title = if (preview) "Reader preview" else sermon.title, onBack = onBack) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            Row(Modifier.padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(
                    value = query, onValueChange = { query = it },
                    label = { Text("Find in khutba") }, singleLine = true,
                    modifier = Modifier.weight(1f),
                )
                if (query.isNotBlank()) {
                    TextButton(onClick = { query = "" }) { Text("Clear") }
                }
            }
            if (query.isNotBlank()) Row(
                Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(if (matches.isEmpty()) "No matches" else "Section ${matchIndex + 1} of ${matches.size} with matches", Modifier.weight(1f))
                TextButton(enabled = matches.isNotEmpty(), onClick = { matchIndex = (matchIndex + matches.size - 1) % matches.size }) { Text("Previous") }
                TextButton(enabled = matches.isNotEmpty(), onClick = { matchIndex = (matchIndex + 1) % matches.size }) { Text("Next") }
            }
            LazyColumn(
                state = listState, modifier = Modifier.weight(1f),
                contentPadding = PaddingValues(22.dp),
                verticalArrangement = Arrangement.spacedBy(24.dp),
            ) {
                item(key = "reader-header") {
                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text(sermon.title, style = MaterialTheme.typography.headlineSmall)
                        Text(friendlySermonDate(sermon.khutbaDate), color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(
                            if (preview) "Preview of saved edits · Not yet published"
                            else "Reviewed by your mosque · Saved for offline reading",
                            style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary,
                        )
                        if (offline) OfflineReaderNote()
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("Aa", fontSize = 16.sp)
                            Slider(value = textSize, onValueChange = viewModel::setReaderTextSize,
                                valueRange = 16f..28f, steps = 5, modifier = Modifier.weight(1f).padding(horizontal = 12.dp))
                            Text("Aa", fontSize = 26.sp)
                        }
                        if (!preview) OutlinedButton(onClick = onDownload, enabled = !offline, modifier = Modifier.fillMaxWidth()) {
                            Icon(Icons.Default.Download, contentDescription = null)
                            Spacer(Modifier.width(8.dp))
                            Text(if (offline) "PDF download needs internet" else "Download PDF")
                        }
                        Text("Tap a highlighted term or source icon to see its explanation.",
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        HorizontalDivider()
                    }
                }
                itemsIndexed(sermon.segments, key = { _, it -> it.id }) { index, segment ->
                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text("SECTION ${index + 1}", style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.primary)
                        TranslatedTextWithCitationIcons(
                            text = segment.translatedText.orEmpty(),
                            citations = segment.citations.filter { it.anchorValid && (it.sourceKind == "quran" || it.sourceKind == "hadith") },
                            glossaryTerms = segment.glossaryTerms,
                            onCitationClick = { selectedCitation = it },
                            onGlossaryClick = { selectedGlossaryTerm = it },
                            textSize = textSize, searchQuery = query.trim(),
                        )
                        segment.citations.filter { !it.anchorValid || citationInsertionPoint(sanitizedReaderText(segment.translatedText.orEmpty()), it) == null }.forEach { citation ->
                            TextButton(onClick = { selectedCitation = citation }) {
                                Text("${if (!citation.anchorValid) "Quotation needs review" else "Section source"}: ${citationReference(citation)}")
                            }
                        }
                    }
                }
            }
        }
    }
    selectedCitation?.let { ReaderCitationDialog(it) { selectedCitation = null } }
    selectedGlossaryTerm?.let { ReaderGlossaryDialog(it) { selectedGlossaryTerm = null } }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AdminHomeScreen(state: KhutbaUiState, viewModel: MainViewModel) {
    var needsAttention by rememberSaveable { mutableStateOf(false) }
    var sermonTitle by remember { mutableStateOf("") }
    var sermonDate by remember { mutableStateOf(upcomingFridayDate()) }
    var sermonPendingDeletion by remember { mutableStateOf<SermonSummary?>(null) }
    val targetLanguage = "en"

    val sermonPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
        uri?.let { viewModel.uploadSermon(it, sermonTitle, sermonDate, targetLanguage) }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(state.adminMosque?.name ?: "Mosque administration") },
                actions = {
                    if (state.adminMosque != null) {
                        IconButton(onClick = viewModel::openAdminSettings) {
                            Icon(Icons.Default.Settings, contentDescription = "Mosque settings")
                        }
                    }
                    IconButton(onClick = viewModel::logout) {
                        Icon(Icons.AutoMirrored.Filled.Logout, contentDescription = "Sign out")
                    }
                },
            )
        },
    ) { padding ->
        LazyColumn(
            Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(18.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            item {
                AdminOverviewCard(
                    sermonCount = state.sermons.size,
                )
            }
            item { SectionTitle("Khutbas", "Upload, translate, review, then publish") }
            item {
                AdminUploadCard(
                    title = "Upload Arabic khutba",
                    subtitle = "PDF and DOCX are supported. Only extracted Arabic text is sent for translation.",
                ) {
                    FormField("Khutba title (optional)", sermonTitle) { sermonTitle = it }
                    Text(
                        "Leave the title empty and it will be inferred from the khutba.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    FormField("Friday date (YYYY-MM-DD)", sermonDate) { sermonDate = it }
                    Surface(
                        color = MaterialTheme.colorScheme.primaryContainer,
                        shape = MaterialTheme.shapes.small,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(
                            "Translation output: English",
                            modifier = Modifier.padding(14.dp),
                            color = MaterialTheme.colorScheme.onPrimaryContainer,
                            style = MaterialTheme.typography.labelLarge,
                        )
                    }
                    Button(
                        onClick = { sermonPicker.launch(SupportedDocumentMimeTypes) },
                        enabled = sermonDate.matches(Regex("\\d{4}-\\d{2}-\\d{2}")) && targetLanguage.isNotBlank(),
                        modifier = Modifier.fillMaxWidth().height(52.dp),
                    ) {
                        Icon(Icons.Default.UploadFile, contentDescription = null)
                        Spacer(Modifier.width(8.dp))
                        Text("Choose PDF or DOCX khutba")
                    }
                }
            }
            item {
                FilterChip(selected = needsAttention, onClick = { needsAttention = !needsAttention },
                    label = { Text("Needs attention") })
            }
            items(state.sermons.filter { !needsAttention || it.status in listOf("SOURCE_REVIEW_REQUIRED", "DRAFT", "FAILED", "REVIEW_REQUIRED") }, key = { it.id }) { sermon ->
                AdminSermonCard(
                    sermon = sermon,
                    onOpen = { viewModel.openAdminSermon(sermon.id) },
                    onVisibilityChange = {
                        viewModel.setSermonHidden(sermon.id, sermon.status == "PUBLISHED")
                    },
                    onDelete = { sermonPendingDeletion = sermon },
                )
            }
        }
    }
    sermonPendingDeletion?.let { sermon ->
        AlertDialog(
            onDismissRequest = { sermonPendingDeletion = null },
            title = { Text("Remove khutba?") },
            text = {
                Text("${sermon.title} and its translation will be permanently removed.")
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        sermonPendingDeletion = null
                        viewModel.deleteSermon(sermon.id)
                    }
                ) {
                    Text("Remove", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { sermonPendingDeletion = null }) { Text("Cancel") }
            },
        )
    }
}

@Composable
private fun AdminSettingsScreen(state: KhutbaUiState, viewModel: MainViewModel) {
    val mosque = state.adminMosque
    var mosqueName by remember(mosque?.name) { mutableStateOf(mosque?.name.orEmpty()) }
    var currentPassword by remember { mutableStateOf("") }
    var newPassword by remember { mutableStateOf("") }
    var confirmPassword by remember { mutableStateOf("") }
    var glossaryEditorOpen by remember { mutableStateOf(false) }
    var editingGlossaryTerm by remember { mutableStateOf<MosqueGlossaryTerm?>(null) }
    var glossaryTermPendingDeletion by remember { mutableStateOf<MosqueGlossaryTerm?>(null) }
    val trimmedMosqueName = mosqueName.trim()
    val mosqueNameChanged = mosque != null &&
        trimmedMosqueName.length >= 2 &&
        trimmedMosqueName != mosque.name
    val passwordsMatch = newPassword == confirmPassword
    val passwordIsValid = currentPassword.isNotEmpty() &&
        newPassword.length >= 6 &&
        passwordsMatch

    AppScaffold(title = "Mosque settings", onBack = viewModel::back) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(22.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp),
        ) {
            item {
                SectionTitle(
                    "Mosque profile",
                    "This name is shown to readers when they choose a mosque.",
                )
            }
            item {
                Card(Modifier.fillMaxWidth()) {
                    Column(
                        Modifier.padding(18.dp),
                        verticalArrangement = Arrangement.spacedBy(14.dp),
                    ) {
                        OutlinedTextField(
                            value = mosqueName,
                            onValueChange = { mosqueName = it },
                            label = { Text("Mosque name") },
                            supportingText = { Text("At least 2 characters") },
                            isError = mosqueName.isNotBlank() && trimmedMosqueName.length < 2,
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                        mosque?.let {
                            Text(
                                "${it.city}, ${it.country}",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        Button(
                            onClick = { viewModel.updateMosqueName(trimmedMosqueName) },
                            enabled = mosqueNameChanged,
                            modifier = Modifier.fillMaxWidth().height(52.dp),
                        ) {
                            Text("Save mosque name")
                        }
                    }
                }
            }
            item {
                SectionTitle(
                    "Mosque glossary",
                    "Your entries override the built-in glossary for this mosque's future translations.",
                )
            }
            item {
                Button(
                    onClick = {
                        editingGlossaryTerm = null
                        glossaryEditorOpen = true
                    },
                    modifier = Modifier.fillMaxWidth().height(52.dp),
                ) {
                    Icon(Icons.Default.Add, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text("Add glossary term")
                }
            }
            if (state.adminGlossary.isEmpty()) {
                item {
                    Text(
                        "No mosque-specific terms yet. The verified built-in glossary is still active.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            } else {
                items(state.adminGlossary, key = { it.id }) { term ->
                    Card(Modifier.fillMaxWidth()) {
                        Row(
                            Modifier.fillMaxWidth().padding(16.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(
                                Modifier.weight(1f),
                                verticalArrangement = Arrangement.spacedBy(4.dp),
                            ) {
                                ArabicText(term.arabicTerm)
                                Text(
                                    term.literalTranslation,
                                    style = MaterialTheme.typography.titleSmall,
                                )
                                Text(
                                    term.meaning,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                            IconButton(
                                onClick = {
                                    editingGlossaryTerm = term
                                    glossaryEditorOpen = true
                                }
                            ) {
                                Icon(Icons.Default.Edit, contentDescription = "Edit glossary term")
                            }
                            IconButton(onClick = { glossaryTermPendingDeletion = term }) {
                                Icon(
                                    Icons.Default.Delete,
                                    contentDescription = "Remove glossary term",
                                    tint = MaterialTheme.colorScheme.error,
                                )
                            }
                        }
                    }
                }
            }
            item {
                SectionTitle(
                    "Change password",
                    "Enter your current password before choosing a new one.",
                )
            }
            item {
                Card(Modifier.fillMaxWidth()) {
                    Column(
                        Modifier.padding(18.dp),
                        verticalArrangement = Arrangement.spacedBy(14.dp),
                    ) {
                        OutlinedTextField(
                            value = currentPassword,
                            onValueChange = { currentPassword = it },
                            label = { Text("Current password") },
                            visualTransformation = PasswordVisualTransformation(),
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                        OutlinedTextField(
                            value = newPassword,
                            onValueChange = { newPassword = it },
                            label = { Text("New password") },
                            supportingText = { Text("At least 6 characters") },
                            isError = newPassword.isNotBlank() && newPassword.length < 6,
                            visualTransformation = PasswordVisualTransformation(),
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                        OutlinedTextField(
                            value = confirmPassword,
                            onValueChange = { confirmPassword = it },
                            label = { Text("Confirm new password") },
                            supportingText = {
                                if (confirmPassword.isNotBlank() && !passwordsMatch) {
                                    Text("Passwords do not match")
                                }
                            },
                            isError = confirmPassword.isNotBlank() && !passwordsMatch,
                            visualTransformation = PasswordVisualTransformation(),
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                        Button(
                            onClick = {
                                viewModel.changePassword(currentPassword, newPassword)
                            },
                            enabled = passwordIsValid,
                            modifier = Modifier.fillMaxWidth().height(52.dp),
                        ) {
                            Text("Update password")
                        }
                    }
                }
            }
        }
    }
    if (glossaryEditorOpen) {
        GlossaryTermEditorDialog(
            term = editingGlossaryTerm,
            onDismiss = { glossaryEditorOpen = false },
            onSave = { arabic, english, meaning, variations, alternatives ->
                glossaryEditorOpen = false
                viewModel.saveGlossaryTerm(
                    editingGlossaryTerm?.id,
                    arabic,
                    english,
                    meaning,
                    variations,
                    alternatives,
                )
            },
        )
    }
    glossaryTermPendingDeletion?.let { term ->
        AlertDialog(
            onDismissRequest = { glossaryTermPendingDeletion = null },
            title = { Text("Remove glossary term?") },
            text = { Text("${term.arabicTerm} will return to the built-in glossary meaning.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        glossaryTermPendingDeletion = null
                        viewModel.deleteGlossaryTerm(term.id)
                    }
                ) {
                    Text("Remove", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { glossaryTermPendingDeletion = null }) { Text("Cancel") }
            },
        )
    }
}

@Composable
private fun GlossaryTermEditorDialog(
    term: MosqueGlossaryTerm?,
    onDismiss: () -> Unit,
    onSave: (String, String, String, String, String) -> Unit,
) {
    var arabicTerm by remember(term?.id) { mutableStateOf(term?.arabicTerm.orEmpty()) }
    var englishTranslation by remember(term?.id) {
        mutableStateOf(term?.literalTranslation.orEmpty())
    }
    var meaning by remember(term?.id) { mutableStateOf(term?.meaning.orEmpty()) }
    var variations by remember(term?.id) {
        mutableStateOf(term?.arabicVariations.orEmpty().split('|').filter { it.isNotBlank() }.map {
            val parts = it.trim().split(Regex("\\s+[—–-]\\s+"), limit = 2)
            parts.first() to parts.getOrElse(1) { "" }
        })
    }
    var alternatives by remember(term?.id) {
        mutableStateOf(term?.alternativeContextMeanings.orEmpty())
    }
    val valid = arabicTerm.trim().isNotEmpty() &&
        englishTranslation.trim().isNotEmpty() && meaning.trim().length >= 3 &&
        variations.all { (arabic, english) -> arabic.isNotBlank() && english.isNotBlank() && '|' !in arabic && '|' !in english }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (term == null) "Add glossary term" else "Edit glossary term") },
        text = {
            Column(
                Modifier.heightIn(max = 520.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Text(
                    "Use the exact Arabic word or expression. It will be highlighted only when the translation verifier confirms that this sense fits the context.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                OutlinedTextField(
                    value = arabicTerm,
                    onValueChange = { arabicTerm = it },
                    label = { Text("Arabic word or expression") },
                    textStyle = TextStyle(textDirection = TextDirection.Rtl),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = englishTranslation,
                    onValueChange = { englishTranslation = it },
                    label = { Text("Concise English translation") },
                    supportingText = { Text("The complete phrase that should be highlighted") },
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = meaning,
                    onValueChange = { meaning = it },
                    label = { Text("Explanation shown when tapped") },
                    minLines = 3,
                    modifier = Modifier.fillMaxWidth(),
                )
                Text("Variations (optional)", style = MaterialTheme.typography.titleSmall)
                variations.forEachIndexed { index, variation ->
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedTextField(value = variation.first, onValueChange = { value ->
                            variations = variations.mapIndexed { i, row -> if (i == index) value to row.second else row }
                        }, label = { Text("Arabic variation ${index + 1}") }, modifier = Modifier.fillMaxWidth())
                        OutlinedTextField(value = variation.second, onValueChange = { value ->
                            variations = variations.mapIndexed { i, row -> if (i == index) row.first to value else row }
                        }, label = { Text("English translation") }, modifier = Modifier.fillMaxWidth())
                        TextButton(onClick = { variations = variations.filterIndexed { i, _ -> i != index } }) { Text("Remove variation ${index + 1}") }
                    }
                }
                TextButton(onClick = { variations = variations + ("" to "") }) { Text("+ Add variation") }
                OutlinedTextField(
                    value = alternatives,
                    onValueChange = { alternatives = it },
                    label = { Text("Other contextual meanings (optional)") },
                    minLines = 2,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    onSave(
                        arabicTerm,
                        englishTranslation,
                        meaning,
                        variations.joinToString(" | ") { "${it.first.trim()} — ${it.second.trim()}" },
                        alternatives,
                    )
                },
                enabled = valid,
            ) {
                Text("Save")
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun AdminSermonScreen(state: KhutbaUiState, viewModel: MainViewModel) {
    var needsAttention by rememberSaveable(state.selectedSermon?.id) { mutableStateOf(false) }
    val sermon = state.selectedSermon
    AppScaffold(title = sermon?.title ?: "Review", onBack = viewModel::back) { padding ->
        if (sermon == null) return@AppScaffold
        val translating = state.translatingSermonId == sermon.id
        LazyColumn(
            Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            item {
                StatusBlock(sermon)
                if (translating) {
                    Spacer(Modifier.height(12.dp))
                    TranslationProgressCard(
                        completed = state.translatedSegments,
                        total = state.translationTotalSegments,
                        reconnecting = state.translationReconnecting,
                    )
                } else if (sermon.status == "DRAFT" || sermon.status == "FAILED") {
                    Spacer(Modifier.height(12.dp))
                    Button(
                        onClick = { viewModel.translate(sermon.id) },
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text(if (sermon.status == "FAILED") "Retry unfinished sections" else "Create translation draft") }
                }
            }
            if (!translating) {
                if (sermon.status == "SOURCE_REVIEW_REQUIRED") {
                    item { SourceTextReviewCard(sermon, viewModel) }
                } else {
                    item {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                            FilterChip(selected = needsAttention, onClick = { needsAttention = !needsAttention }, label = { Text("Needs attention") })
                            TextButton(onClick = viewModel::previewSermon,
                                enabled = sermon.segments.any { !it.translatedText.isNullOrBlank() }) { Text("Reader preview") }
                        }
                        Text("Preview includes saved edits.", style = MaterialTheme.typography.bodySmall)
                    }
                    items(sermon.segments.filter { !needsAttention || it.verificationStatus != "HUMAN_APPROVED" }, key = { it.id }) { segment ->
                        ReviewSegmentCard(sermon.id, segment, viewModel)
                    }
                }
            }
            if (
                sermon.status == "REVIEW_REQUIRED" &&
                sermon.segments.isNotEmpty() &&
                sermon.segments.all { it.verificationStatus == "HUMAN_APPROVED" }
            ) {
                item {
                    Button(
                        onClick = { viewModel.publish(sermon.id) },
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("Publish reviewed khutba") }
                }
            }
        }
    }
}

@Composable
private fun TranslationProgressCard(completed: Int, total: Int, reconnecting: Boolean = false) {
    val safeCompleted = completed.coerceIn(0, total.coerceAtLeast(0))
    val progress = if (total > 0) safeCompleted.toFloat() / total else 0f
    val currentSection = (safeCompleted + 1).coerceAtMost(total.coerceAtLeast(1))

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer,
        ),
    ) {
        Column(
            Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(
                "Creating grounded translation",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                if (total > 0) {
                    "Checking sources and translating section $currentSection of $total"
                } else {
                    "Preparing the khutba for translation"
                },
                color = MaterialTheme.colorScheme.onPrimaryContainer,
            )
            if (safeCompleted == 0) {
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
            } else {
                LinearProgressIndicator(
                    progress = { progress },
                    modifier = Modifier.fillMaxWidth(),
                )
                Text(
                    "$safeCompleted of $total sections completed · ${(progress * 100).toInt()}%",
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onPrimaryContainer,
                )
            }
            Text(
                if (reconnecting) "Connection interrupted. Reconnecting to the translation…"
                else "You can leave this screen. Progress reconnects when you return.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onPrimaryContainer,
            )
        }
    }
}

@Composable
private fun StatusBlock(sermon: SermonDetail) {
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(16.dp)) {
            val stage = when (sermon.status) {
                "SOURCE_REVIEW_REQUIRED" -> 1
                "DRAFT", "FAILED", "TRANSLATING" -> 2
                "REVIEW_REQUIRED" -> 3
                else -> 4
            }
            Text("${stage + 1} / 5 · ${listOf("Upload", "Check Arabic", "Translate", "Review", "Publish")[stage]}", style = MaterialTheme.typography.titleMedium)
            Text("Upload → Check Arabic → Translate → Review → Publish", style = MaterialTheme.typography.bodySmall)
            LinearProgressIndicator(progress = { (stage + 1) / 5f }, modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp))
            Text("${sermon.segments.count { it.verificationStatus == "HUMAN_APPROVED" }} of ${sermon.segments.size} sections approved")
            Text("${sermon.khutbaDate} · ${sermon.targetLanguage.uppercase()}")
            sermon.failureReason?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            if (sermon.status == "SOURCE_REVIEW_REQUIRED") {
                Text(
                    "Translation is locked until a mosque reviewer checks and confirms the extracted Arabic text."
                )
            } else if (sermon.status == "REVIEW_REQUIRED") {
                Text("Publication is locked until every segment is approved by a human reviewer.")
            }
        }
    }
}

@Composable
private fun SourceTextReviewCard(sermon: SermonDetail, viewModel: MainViewModel) {
    var arabicText by remember(sermon.id, sermon.segments) {
        mutableStateOf(sermon.segments.joinToString("\n\n") { it.arabicText })
    }
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text("Step 1 · Verify extracted Arabic", style = MaterialTheme.typography.titleLarge)
            Text(
                "Compare this text with every page of the original document. OCR can confuse letters, names, numbers, Qur’anic verses, and hadith wording.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            OutlinedTextField(
                value = arabicText,
                onValueChange = { arabicText = it },
                label = { Text("Extracted Arabic khutba") },
                minLines = 12,
                textStyle = MaterialTheme.typography.bodyLarge.merge(
                    TextStyle(textDirection = TextDirection.Rtl, textAlign = TextAlign.Right)
                ),
                modifier = Modifier.fillMaxWidth(),
            )
            Button(
                onClick = { viewModel.confirmSourceText(sermon.id, arabicText) },
                enabled = arabicText.length >= 40,
                modifier = Modifier.fillMaxWidth().height(54.dp),
            ) {
                Icon(Icons.Default.CheckCircle, contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text("Confirm Arabic and continue")
            }
        }
    }
}

@Composable
private fun ReviewSegmentCard(
    sermonId: String,
    segment: SermonSegment,
    viewModel: MainViewModel,
) {
    var translation by remember(segment.id, segment.translatedText) {
        mutableStateOf(segment.translatedText.orEmpty())
    }
    var note by remember(segment.id, segment.reviewerNote) {
        mutableStateOf(segment.reviewerNote.orEmpty())
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (segment.verificationStatus == "HUMAN_APPROVED") {
                    Icon(Icons.Default.CheckCircle, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                } else if (segment.issues.isNotEmpty()) {
                    Icon(Icons.Default.Error, contentDescription = null, tint = MaterialTheme.colorScheme.error)
                }
                Spacer(Modifier.width(8.dp))
                Text("Segment ${segment.ordinal + 1}", style = MaterialTheme.typography.titleMedium)
            }
            ArabicText(segment.arabicText)
            OutlinedTextField(
                value = translation,
                onValueChange = { translation = it },
                label = { Text("Translation") },
                minLines = 4,
                modifier = Modifier.fillMaxWidth(),
            )
            if (segment.issues.isNotEmpty()) {
                Text("Model/verifier warnings", color = MaterialTheme.colorScheme.error)
                segment.issues.forEach { Text("• $it", style = MaterialTheme.typography.bodySmall) }
            }
            segment.citations.forEach { CitationCard(it) }
            OutlinedTextField(
                value = note,
                onValueChange = { note = it },
                label = { Text("Reviewer note (optional)") },
                modifier = Modifier.fillMaxWidth(),
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(
                    onClick = {
                        viewModel.reviewSegment(sermonId, segment.id, translation, false, note)
                    },
                    enabled = translation.isNotBlank(),
                    modifier = Modifier.weight(1f),
                ) { Text("Needs work") }
                Button(
                    onClick = {
                        viewModel.reviewSegment(sermonId, segment.id, translation, true, note)
                    },
                    enabled = translation.isNotBlank(),
                    modifier = Modifier.weight(1f),
                ) { Text("Approve") }
            }
        }
    }
}

@Composable
private fun CitationCard(citation: Citation) {
    val uriHandler = LocalUriHandler.current
    Column(
        Modifier.fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceVariant, MaterialTheme.shapes.small)
            .padding(12.dp)
    ) {
        Text(
            "Verified ${citation.sourceKind.replaceFirstChar { it.uppercase() }} · ${citation.title}",
            style = MaterialTheme.typography.labelLarge,
        )
        Text(citation.authority, style = MaterialTheme.typography.labelMedium)
        Text(citation.excerpt, style = MaterialTheme.typography.bodySmall)
        citation.url?.let { url ->
            TextButton(onClick = { uriHandler.openUri(url) }) {
                Icon(
                    Icons.AutoMirrored.Filled.OpenInNew,
                    contentDescription = null,
                    modifier = Modifier.size(16.dp),
                )
                Spacer(Modifier.width(6.dp))
                Text("Open source")
            }
        }
    }
}

private data class PositionedCitation(val position: Int, val citation: Citation, val key: String)
private data class PositionedGlossaryTerm(
    val start: Int,
    val end: Int,
    val term: GlossaryTerm,
)

private val ReaderSourceMarkerRegex = Regex("\\s*\\[S:[^\\]\\r\\n]+\\]")

private fun sanitizedReaderText(value: String): String = value
    .replace(ReaderSourceMarkerRegex, "")
    .replace(Regex("[ \\t]+([,.;:!?])"), "\$1")
    .replace(Regex("[ \\t]{2,}"), " ")
    .trim()

private fun citationReference(citation: Citation): String {
    citation.displayReference?.ifBlank { null }?.let { return it }
    if (citation.sourceKind == "quran") {
        val verseKey = citation.sourceId.substringAfter("quran.com:", "")
        if (verseKey.isNotBlank()) return "Qur’an $verseKey"
    }
    return citation.title.substringBefore(" —").ifBlank { "Source" }
}

internal fun codePointOffset(text: String, offset: Int?): Int? = offset?.takeIf {
    it >= 0 && it <= text.codePointCount(0, text.length)
}?.let { text.offsetByCodePoints(0, it) }

internal fun citationInsertionPoint(text: String, citation: Citation): Int? {
    if (!citation.anchorValid) return null
    val storedStart = codePointOffset(text, citation.translationStart)
    val storedEnd = codePointOffset(text, citation.translationEnd)
    if (
        storedStart != null && storedEnd != null &&
        storedStart >= 0 && storedEnd in (storedStart + 1)..text.length &&
        text.substring(storedStart, storedEnd).equals(citation.excerpt, ignoreCase = true)
    ) {
        return storedEnd
    }
    val excerpt = citation.excerpt.trim()
    if (excerpt.isEmpty()) return null
    val start = text.indexOf(excerpt, ignoreCase = true)
    // Never attach an unanchored repeated quotation to an arbitrary occurrence.
    return if (start >= 0 && text.indexOf(excerpt, start + 1, ignoreCase = true) < 0) start + excerpt.length else null
}

internal fun glossaryDisplayRange(text: String, term: GlossaryTerm): IntRange? {
    val storedStart = codePointOffset(text, term.translationStart)
    val storedEnd = codePointOffset(text, term.translationEnd)
    if (
        storedStart != null && storedEnd != null &&
        storedStart >= 0 && storedEnd in (storedStart + 1)..text.length &&
        text.substring(storedStart, storedEnd).equals(term.displayTerm, ignoreCase = true)
    ) {
        return storedStart until storedEnd
    }
    val phrase = term.displayTerm.trim()
    if (phrase.isEmpty()) return null
    val pattern = Regex(
        "(?<![\\p{L}\\p{N}])${Regex.escape(phrase)}(?![\\p{L}\\p{N}])",
        RegexOption.IGNORE_CASE,
    )
    return pattern.find(text)?.range
}

@Composable
private fun TranslatedTextWithCitationIcons(
    text: String,
    citations: List<Citation>,
    glossaryTerms: List<GlossaryTerm>,
    onCitationClick: (Citation) -> Unit,
    onGlossaryClick: (GlossaryTerm) -> Unit,
    textSize: Float = 18f,
    searchQuery: String = "",
) {
    val readerText = sanitizedReaderText(text)
    val glossaryPositions = buildList {
        var occupiedUntil = 0
        glossaryTerms.mapNotNull { term ->
            val range = glossaryDisplayRange(readerText, term)
            if (range == null) null else PositionedGlossaryTerm(
                start = range.first,
                end = range.last + 1,
                term = term,
            )
        }.sortedWith(
            compareBy<PositionedGlossaryTerm> { it.start }
                .thenByDescending { it.end - it.start },
        ).forEach { item ->
            if (item.start >= occupiedUntil) {
                add(item)
                occupiedUntil = item.end
            }
        }
    }
    val positioned = citations.mapIndexedNotNull { index, citation ->
        val rawPosition = citationInsertionPoint(readerText, citation) ?: return@mapIndexedNotNull null
        val adjustedPosition = glossaryPositions
            .firstOrNull { rawPosition > it.start && rawPosition < it.end }
            ?.end
            ?: rawPosition
        PositionedCitation(
            position = adjustedPosition,
            citation = citation,
            key = "source-$index",
        )
    }.sortedBy { it.position }
    val citationsByPosition = positioned.groupBy { it.position }
    val glossaryByStart = glossaryPositions.associateBy { it.start }
    val glossaryLinkStyle = TextLinkStyles(
        style = SpanStyle(
            color = MaterialTheme.colorScheme.tertiary,
            fontWeight = FontWeight.SemiBold,
            background = MaterialTheme.colorScheme.tertiaryContainer.copy(alpha = 0.45f),
        ),
        pressedStyle = SpanStyle(
            color = MaterialTheme.colorScheme.onTertiaryContainer,
            background = MaterialTheme.colorScheme.tertiaryContainer,
        ),
    )
    val searchColor = MaterialTheme.colorScheme.secondaryContainer
    val annotated = buildAnnotatedString {
        var cursor = 0
        fun appendCitationsAt(position: Int) {
            citationsByPosition[position].orEmpty().forEach { item ->
                append(" (${citationReference(item.citation)}) ")
                appendInlineContent(item.key, "[source]")
            }
        }
        while (cursor < readerText.length) {
            appendCitationsAt(cursor)
            val glossary = glossaryByStart[cursor]
            if (glossary != null) {
                val linkStart = length
                append(readerText.substring(glossary.start, glossary.end))
                addLink(
                    LinkAnnotation.Clickable(
                        tag = glossary.term.arabicTerm,
                        styles = glossaryLinkStyle,
                        linkInteractionListener = { onGlossaryClick(glossary.term) },
                    ),
                    start = linkStart,
                    end = length,
                )
                cursor = glossary.end
            } else {
                val nextGlossary = glossaryPositions.firstOrNull { it.start > cursor }?.start
                val nextCitation = positioned.firstOrNull { it.position > cursor }?.position
                val nextEvent = listOfNotNull(nextGlossary, nextCitation, readerText.length).min()
                append(readerText.substring(cursor, nextEvent))
                cursor = nextEvent
            }
        }
        appendCitationsAt(readerText.length)
        if (searchQuery.isNotBlank()) {
            Regex(Regex.escape(searchQuery), RegexOption.IGNORE_CASE).findAll(toString()).forEach {
                addStyle(SpanStyle(background = searchColor), it.range.first, it.range.last + 1)
            }
        }
    }
    val inlineContent = positioned.associate { item ->
        item.key to InlineTextContent(
            placeholder = Placeholder(
                width = 1.25.em,
                height = 1.25.em,
                placeholderVerticalAlign = PlaceholderVerticalAlign.TextCenter,
            ),
        ) {
            Icon(
                imageVector = Icons.AutoMirrored.Filled.OpenInNew,
                contentDescription = "Open ${citationReference(item.citation)} source",
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.fillMaxSize().clickable {
                    onCitationClick(item.citation)
                },
            )
        }
    }
    Text(
        text = annotated,
        inlineContent = inlineContent,
        style = MaterialTheme.typography.bodyLarge.copy(fontSize = textSize.sp, lineHeight = (textSize * 1.65f).sp),
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ReaderCitationDialog(citation: Citation, onDismiss: () -> Unit) {
    val uriHandler = LocalUriHandler.current
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text(citationReference(citation), style = MaterialTheme.typography.headlineSmall)
            citation.arabicExcerpt?.takeIf { it.isNotBlank() }?.let { ArabicText(it) }
            citation.transliteration?.takeIf { it.isNotBlank() }?.let {
                Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            HorizontalDivider()
            Text(citation.title, style = MaterialTheme.typography.titleMedium)
            Text(citation.authority, color = MaterialTheme.colorScheme.primary)
            citation.url?.let { url ->
                OutlinedButton(onClick = { runCatching { uriHandler.openUri(url) } }) {
                    Text("Open source website")
                }
            }
            TextButton(onClick = onDismiss) { Text("Close") }
            Spacer(Modifier.height(24.dp))
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ReaderGlossaryDialog(term: GlossaryTerm, onDismiss: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text(term.displayTerm, style = MaterialTheme.typography.headlineSmall)
            ArabicText(term.arabicTerm)
            HorizontalDivider()
            Text(term.meaning, style = MaterialTheme.typography.bodyLarge)
            if (term.literalTranslation.isNotBlank()) Text("Literal wording: ${term.literalTranslation}")
            if (term.alternativeContextMeanings.isNotBlank()) {
                Text("Other contexts", style = MaterialTheme.typography.titleMedium)
                Text(term.alternativeContextMeanings)
            }
            TextButton(onClick = onDismiss) { Text("Close") }
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun ArabicText(value: String) {
    Text(
        value,
        modifier = Modifier.fillMaxWidth(),
        textAlign = TextAlign.Right,
        style = MaterialTheme.typography.bodyLarge.merge(
            TextStyle(textDirection = TextDirection.Rtl)
        ),
    )
}

@Composable
private fun SermonCard(sermon: SermonSummary, onClick: () -> Unit) {
    Card(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Row(
            Modifier.padding(17.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(13.dp),
        ) {
            Box(
                Modifier.size(44.dp).background(
                    MaterialTheme.colorScheme.primaryContainer,
                    CircleShape,
                ),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    Icons.Default.Description,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                )
            }
            Column(Modifier.weight(1f)) {
                Text(sermon.title, style = MaterialTheme.typography.titleMedium)
                Text(
                    "${friendlySermonDate(sermon.khutbaDate)} · ${sermon.targetLanguage.uppercase()}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun AdminSermonCard(
    sermon: SermonSummary,
    onOpen: () -> Unit,
    onVisibilityChange: () -> Unit,
    onDelete: () -> Unit,
) {
    val canChangeVisibility = sermon.status == "PUBLISHED" || sermon.status == "HIDDEN"
    val isHidden = sermon.status == "HIDDEN"
    Card(Modifier.fillMaxWidth()) {
        Column {
            Column(
                Modifier.fillMaxWidth().clickable(onClick = onOpen).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Text(sermon.title, style = MaterialTheme.typography.titleMedium)
                Text(
                    "${sermon.khutbaDate} · ${sermon.status.replace('_', ' ')}",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            HorizontalDivider()
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 6.dp),
                horizontalArrangement = Arrangement.End,
            ) {
                if (canChangeVisibility) {
                    TextButton(onClick = onVisibilityChange) {
                        Icon(
                            if (isHidden) Icons.Default.Visibility else Icons.Default.VisibilityOff,
                            contentDescription = null,
                        )
                        Spacer(Modifier.width(6.dp))
                        Text(if (isHidden) "Show" else "Hide")
                    }
                }
                TextButton(onClick = onDelete) {
                    Icon(
                        Icons.Default.Delete,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.error,
                    )
                    Spacer(Modifier.width(6.dp))
                    Text("Remove", color = MaterialTheme.colorScheme.error)
                }
            }
        }
    }
}

private data class SermonDateSections(
    val thisWeek: List<SermonSummary>,
    val upcoming: List<SermonSummary>,
    val archive: List<Pair<String, List<SermonSummary>>>,
)

private fun sermonDateSections(
    sermons: List<SermonSummary>,
    today: LocalDate = LocalDate.now(),
): SermonDateSections {
    val dated = sermons.mapNotNull { sermon ->
        runCatching { LocalDate.parse(sermon.khutbaDate) }.getOrNull()?.let { it to sermon }
    }
    val weekStart = today.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))
    val weekEnd = weekStart.plusDays(6)
    val thisWeek = dated
        .filter { (date, _) -> date in weekStart..weekEnd }
        .sortedByDescending { it.first }
        .map { it.second }
    val upcoming = dated
        .filter { (date, _) -> date > weekEnd }
        .sortedBy { it.first }
        .map { it.second }
    val archive = dated
        .filter { (date, _) -> date < weekStart }
        .sortedByDescending { it.first }
        .groupBy { (date, _) -> YearMonth.from(date) }
        .map { (month, entries) ->
            month.format(DateTimeFormatter.ofPattern("MMMM yyyy", Locale.getDefault())) to
                entries.map { it.second }
        }
    return SermonDateSections(thisWeek, upcoming, archive)
}

private fun friendlySermonDate(value: String): String = runCatching {
    LocalDate.parse(value).format(
        DateTimeFormatter.ofPattern("EEEE, d MMMM yyyy", Locale.getDefault())
    )
}.getOrDefault(value)

private fun shortDate(value: LocalDate): String = value.format(
    DateTimeFormatter.ofPattern("d MMM", Locale.getDefault())
)

private fun upcomingFridayDate(today: LocalDate = LocalDate.now()): String =
    today.with(TemporalAdjusters.nextOrSame(DayOfWeek.FRIDAY)).toString()

@Composable
private fun SectionTitle(value: String, subtitle: String? = null) {
    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
        Text(value, style = MaterialTheme.typography.headlineSmall)
        subtitle?.let {
            Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun AdminOverviewCard(sermonCount: Int) {
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text("Your mosque workspace", style = MaterialTheme.typography.titleLarge)
            Text(
                "Documents are converted to text on your API before any translation provider is called.",
                color = MaterialTheme.colorScheme.onPrimaryContainer,
            )
            OverviewMetric("$sermonCount", "Khutbas")
        }
    }
}

@Composable
private fun OverviewMetric(value: String, label: String, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier,
        color = MaterialTheme.colorScheme.surface.copy(alpha = 0.72f),
        shape = MaterialTheme.shapes.medium,
    ) {
        Column(Modifier.padding(14.dp)) {
            Text(
                value,
                style = MaterialTheme.typography.headlineSmall,
                color = MaterialTheme.colorScheme.primary,
            )
            Text(label, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun AdminUploadCard(title: String, subtitle: String, content: @Composable () -> Unit) {
    Card(
        Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Column(
            Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(11.dp),
        ) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text(
                subtitle,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            content()
        }
    }
}

@Composable
private fun FormField(label: String, value: String, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AppScaffold(
    title: String,
    onBack: () -> Unit,
    content: @Composable (PaddingValues) -> Unit,
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(title) },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                ),
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
        content = content,
    )
}
