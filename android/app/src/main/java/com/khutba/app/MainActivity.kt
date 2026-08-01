package com.khutba.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.khutba.app.ui.KhutbaApp
import com.khutba.app.ui.MainViewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            KhutbaTheme {
                val viewModel: MainViewModel = viewModel()
                val state by viewModel.state.collectAsStateWithLifecycle()
                KhutbaApp(state = state, viewModel = viewModel)
            }
        }
    }
}

@Composable
private fun KhutbaTheme(content: @Composable () -> Unit) {
    val colors = if (isSystemInDarkTheme()) {
        darkColorScheme(
            primary = Color(0xFF73DBB2),
            onPrimary = Color(0xFF003828),
            primaryContainer = Color(0xFF07513C),
            onPrimaryContainer = Color(0xFFB4F1D6),
            secondary = Color(0xFFE6C66D),
            secondaryContainer = Color(0xFF554500),
            background = Color(0xFF101512),
            surface = Color(0xFF171D19),
            surfaceVariant = Color(0xFF25302A),
        )
    } else {
        lightColorScheme(
            primary = Color(0xFF075D43),
            onPrimary = Color.White,
            primaryContainer = Color(0xFFC5F1DD),
            onPrimaryContainer = Color(0xFF003829),
            secondary = Color(0xFF8A6800),
            secondaryContainer = Color(0xFFFFE594),
            onSecondaryContainer = Color(0xFF2A2000),
            tertiary = Color(0xFF8B4D32),
            background = Color(0xFFF7F5ED),
            surface = Color(0xFFFFFEFA),
            surfaceVariant = Color(0xFFE8EFEA),
            outlineVariant = Color(0xFFCAD7D0),
        )
    }
    val shapes = Shapes(
        small = RoundedCornerShape(12.dp),
        medium = RoundedCornerShape(20.dp),
        large = RoundedCornerShape(28.dp),
    )
    val typography = Typography(
        displaySmall = TextStyle(fontSize = 38.sp, lineHeight = 44.sp, fontWeight = FontWeight.Bold),
        headlineSmall = TextStyle(fontSize = 25.sp, lineHeight = 32.sp, fontWeight = FontWeight.Bold),
        titleLarge = TextStyle(fontSize = 21.sp, lineHeight = 28.sp, fontWeight = FontWeight.SemiBold),
        titleMedium = TextStyle(fontSize = 17.sp, lineHeight = 24.sp, fontWeight = FontWeight.SemiBold),
        bodyLarge = TextStyle(fontSize = 16.sp, lineHeight = 25.sp),
    )
    MaterialTheme(colorScheme = colors, shapes = shapes, typography = typography, content = content)
}
