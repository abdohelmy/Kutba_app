package com.khutba.app.ui

import android.net.Uri
import android.util.Patterns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.automirrored.filled.MenuBook
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.automirrored.filled.OpenInNew
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.UploadFile
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.unit.dp
import com.khutba.app.model.Citation
import com.khutba.app.model.Mosque
import com.khutba.app.model.SermonDetail
import com.khutba.app.model.SermonSegment
import com.khutba.app.model.SermonSummary

private val SupportedDocumentMimeTypes = arrayOf(
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)

@Composable
fun KhutbaApp(state: KhutbaUiState, viewModel: MainViewModel) {
    Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        when (state.screen) {
            Screen.LOGIN -> LoginScreen(viewModel::login, viewModel::register)
            Screen.READER_MOSQUES -> MosqueListScreen(
                mosques = state.mosques,
                onSelect = viewModel::selectMosque,
                onLogout = viewModel::logout,
            )
            Screen.READER_SERMONS -> SermonListScreen(
                mosque = state.selectedMosque,
                sermons = state.sermons,
                onSelect = viewModel::openPublishedSermon,
                onBack = viewModel::back,
            )
            Screen.SERMON_DETAIL -> ReaderSermonScreen(state.selectedSermon, viewModel::back)
            Screen.ADMIN_HOME -> AdminHomeScreen(state, viewModel)
            Screen.ADMIN_SERMON -> AdminSermonScreen(state.selectedSermon, viewModel)
        }
        if (state.loading) {
            Box(
                Modifier.fillMaxSize().background(MaterialTheme.colorScheme.scrim.copy(alpha = 0.25f)),
                contentAlignment = Alignment.Center,
            ) {
                CircularProgressIndicator()
            }
        }
    }
    state.error?.let { message ->
        AlertDialog(
            onDismissRequest = viewModel::dismissError,
            confirmButton = {
                TextButton(onClick = viewModel::dismissError) { Text("OK") }
            },
            title = { Text("Request failed") },
            text = { Text(message) },
        )
    }
}

@Composable
private fun LoginScreen(
    onLogin: (String, String, LoginType) -> Unit,
    onRegister: (String, String, String) -> Unit,
) {
    var loginType by remember { mutableStateOf(LoginType.INDIVIDUAL) }
    var registering by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    val emailIsValid = Patterns.EMAIL_ADDRESS.matcher(email.trim()).matches()
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
                    Text(
                        if (registering) "Create your account" else "Welcome back",
                        style = MaterialTheme.typography.headlineSmall,
                    )
                    Text(
                        if (registering) "Register as an individual reader."
                        else "Choose how you are signing in.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    if (!registering) {
                        AccountTypeSelector(
                            selected = loginType,
                            onSelected = {
                                loginType = it
                                registering = false
                            },
                        )
                    }
                    if (registering) {
                        OutlinedTextField(
                            value = name,
                            onValueChange = { name = it },
                            label = { Text("Name") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                    OutlinedTextField(
                        value = email,
                        onValueChange = { email = it },
                        label = { Text("Email address") },
                        isError = email.isNotBlank() && !emailIsValid,
                        supportingText = {
                            if (email.isNotBlank() && !emailIsValid) {
                                Text("Enter a complete email address, such as admin@example.com")
                            }
                        },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    OutlinedTextField(
                        value = password,
                        onValueChange = { password = it },
                        label = { Text("Password") },
                        visualTransformation = PasswordVisualTransformation(),
                        singleLine = true,
                        supportingText = { Text("At least 10 characters") },
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Button(
                        onClick = {
                            if (registering) {
                                onRegister(name, email, password)
                            } else {
                                onLogin(email, password, loginType)
                            }
                        },
                        enabled = emailIsValid && password.length >= 10 &&
                            (!registering || name.isNotBlank()),
                        modifier = Modifier.fillMaxWidth().height(54.dp),
                    ) {
                        Text(
                            when {
                                registering -> "Create individual account"
                                loginType == LoginType.MOSQUE -> "Sign in to mosque workspace"
                                else -> "Continue as individual"
                            },
                            fontWeight = FontWeight.SemiBold,
                        )
                    }
                    if (loginType == LoginType.INDIVIDUAL || registering) {
                        TextButton(
                            onClick = {
                                registering = !registering
                                loginType = LoginType.INDIVIDUAL
                            },
                            modifier = Modifier.align(Alignment.CenterHorizontally),
                        ) {
                            Text(
                                if (registering) "I already have an account"
                                else "New here? Create an individual account"
                            )
                        }
                    } else {
                        Text(
                            "Mosque accounts are created by the platform administrator.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            textAlign = TextAlign.Center,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun AccountTypeSelector(selected: LoginType, onSelected: (LoginType) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
        AccountTypeOption(
            title = "Individual",
            description = "Read khutbas",
            icon = Icons.Default.Person,
            selected = selected == LoginType.INDIVIDUAL,
            onClick = { onSelected(LoginType.INDIVIDUAL) },
            modifier = Modifier.weight(1f),
        )
        AccountTypeOption(
            title = "Mosque",
            description = "Manage & review",
            icon = Icons.Default.Home,
            selected = selected == LoginType.MOSQUE,
            onClick = { onSelected(LoginType.MOSQUE) },
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun AccountTypeOption(
    title: String,
    description: String,
    icon: ImageVector,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.clickable(onClick = onClick),
        shape = RoundedCornerShape(18.dp),
        color = if (selected) MaterialTheme.colorScheme.primaryContainer
        else MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.55f),
        border = BorderStroke(
            1.5.dp,
            if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outlineVariant,
        ),
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text(
                description,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MosqueListScreen(
    mosques: List<Mosque>,
    onSelect: (Mosque, String?) -> Unit,
    onLogout: () -> Unit,
) {
    var language by remember { mutableStateOf("") }
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Choose your mosque") },
                actions = {
                    IconButton(onClick = onLogout) {
                        Icon(Icons.AutoMirrored.Filled.Logout, contentDescription = "Sign out")
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
            item {
                OutlinedTextField(
                    value = language,
                    onValueChange = { language = it },
                    label = { Text("Language code (optional, e.g. en or da)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            items(mosques, key = { it.id }) { mosque ->
                Card(
                    onClick = { onSelect(mosque, language) },
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
) {
    AppScaffold(title = mosque?.name ?: "Sermons", onBack = onBack) { padding ->
        LazyColumn(
            Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (sermons.isEmpty()) item {
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant,
                    ),
                ) {
                    Text(
                        "No published sermons match this language yet.",
                        modifier = Modifier.padding(20.dp),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            items(sermons, key = { it.id }) { sermon ->
                SermonCard(sermon, onClick = { onSelect(sermon.id) })
            }
        }
    }
}

@Composable
private fun ReaderSermonScreen(sermon: SermonDetail?, onBack: () -> Unit) {
    AppScaffold(title = sermon?.title ?: "Sermon", onBack = onBack) { padding ->
        if (sermon == null) return@AppScaffold
        LazyColumn(
            Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp),
        ) {
            item {
                Surface(
                    color = MaterialTheme.colorScheme.primaryContainer,
                    shape = MaterialTheme.shapes.medium,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Row(
                        Modifier.padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        Icon(
                            Icons.Default.CheckCircle,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.primary,
                        )
                        Column {
                            Text("${sermon.khutbaDate} · ${sermon.targetLanguage.uppercase()}")
                            Text(
                                "Human-reviewed by the publishing mosque",
                                color = MaterialTheme.colorScheme.onPrimaryContainer,
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    }
                }
            }
            items(sermon.segments, key = { it.id }) { segment ->
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(18.dp)) {
                        Text(segment.translatedText.orEmpty(), style = MaterialTheme.typography.bodyLarge)
                        Spacer(Modifier.height(16.dp))
                        HorizontalDivider()
                        Spacer(Modifier.height(16.dp))
                        ArabicText(segment.arabicText)
                        if (segment.citations.isNotEmpty()) {
                            Spacer(Modifier.height(12.dp))
                            Text(
                                "Reference: ${segment.citations.joinToString { it.title }}",
                                style = MaterialTheme.typography.labelMedium,
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
private fun AdminHomeScreen(state: KhutbaUiState, viewModel: MainViewModel) {
    var sourceTitle by remember { mutableStateOf("") }
    var sourceAuthority by remember { mutableStateOf("") }
    var sourceLanguage by remember { mutableStateOf("en") }
    var sermonTitle by remember { mutableStateOf("") }
    var sermonDate by remember { mutableStateOf("") }
    val targetLanguage = "en"

    val sourcePicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
        uri?.let { viewModel.uploadSource(it, sourceTitle, sourceAuthority, sourceLanguage) }
    }
    val sermonPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
        uri?.let { viewModel.uploadSermon(it, sermonTitle, sermonDate, targetLanguage) }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Mosque administration") },
                actions = {
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
                    sourceCount = state.sources.size,
                    sermonCount = state.sermons.size,
                )
            }
            item { SectionTitle("Trusted sources", "Approved wording used to ground translations") }
            item {
                AdminUploadCard(
                    title = "Add approved reference",
                    subtitle = "Upload a text-based PDF or DOCX. The API extracts its text before retrieval.",
                ) {
                    FormField("Source title", sourceTitle) { sourceTitle = it }
                    FormField("Authority / publisher", sourceAuthority) { sourceAuthority = it }
                    FormField("Language code", sourceLanguage) { sourceLanguage = it }
                    OutlinedButton(
                        onClick = { sourcePicker.launch(SupportedDocumentMimeTypes) },
                        enabled = sourceTitle.isNotBlank() && sourceAuthority.isNotBlank() && sourceLanguage.isNotBlank(),
                        modifier = Modifier.fillMaxWidth().height(52.dp),
                    ) {
                        Icon(Icons.Default.UploadFile, contentDescription = null)
                        Spacer(Modifier.width(8.dp))
                        Text("Choose PDF or DOCX source")
                    }
                }
            }
            item {
                Text(
                    "${state.sources.size} approved source document(s) available",
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
            item { SectionTitle("Khutbas", "Upload, translate, review, then publish") }
            item {
                AdminUploadCard(
                    title = "Upload Arabic khutba",
                    subtitle = "PDF and DOCX are supported. Only extracted Arabic text is sent for translation.",
                ) {
                    FormField("Khutba title", sermonTitle) { sermonTitle = it }
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
                        enabled = sermonTitle.isNotBlank() && sermonDate.matches(Regex("\\d{4}-\\d{2}-\\d{2}")) && targetLanguage.isNotBlank(),
                        modifier = Modifier.fillMaxWidth().height(52.dp),
                    ) {
                        Icon(Icons.Default.UploadFile, contentDescription = null)
                        Spacer(Modifier.width(8.dp))
                        Text("Choose PDF or DOCX khutba")
                    }
                }
            }
            items(state.sermons, key = { it.id }) { sermon ->
                SermonCard(sermon, onClick = { viewModel.openAdminSermon(sermon.id) })
            }
        }
    }
}

@Composable
private fun AdminSermonScreen(sermon: SermonDetail?, viewModel: MainViewModel) {
    AppScaffold(title = sermon?.title ?: "Review", onBack = viewModel::back) { padding ->
        if (sermon == null) return@AppScaffold
        LazyColumn(
            Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            item {
                StatusBlock(sermon)
                if (sermon.status == "DRAFT" || sermon.status == "FAILED") {
                    Spacer(Modifier.height(12.dp))
                    Button(
                        onClick = { viewModel.translate(sermon.id) },
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("Create grounded translation draft") }
                }
            }
            if (sermon.status == "SOURCE_REVIEW_REQUIRED") {
                item { SourceTextReviewCard(sermon, viewModel) }
            } else {
                items(sermon.segments, key = { it.id }) { segment ->
                    ReviewSegmentCard(sermon.id, segment, viewModel)
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
private fun StatusBlock(sermon: SermonDetail) {
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(16.dp)) {
            Text("Status: ${sermon.status}", style = MaterialTheme.typography.titleMedium)
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
            if (citation.sourceKind == "mosque") citation.title
            else "Verified ${citation.sourceKind.replaceFirstChar { it.uppercase() }} · ${citation.title}",
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
                    "${sermon.khutbaDate} · ${sermon.targetLanguage.uppercase()}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text(sermon.status.replace('_', ' '), color = MaterialTheme.colorScheme.primary)
            }
        }
    }
}

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
private fun AdminOverviewCard(sourceCount: Int, sermonCount: Int) {
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
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                OverviewMetric("$sourceCount", "Sources", Modifier.weight(1f))
                OverviewMetric("$sermonCount", "Khutbas", Modifier.weight(1f))
            }
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
