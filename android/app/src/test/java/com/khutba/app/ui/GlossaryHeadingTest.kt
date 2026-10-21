package com.khutba.app.ui

import com.khutba.app.model.GlossaryTerm
import org.junit.Assert.assertEquals
import org.junit.Test

class GlossaryHeadingTest {
    private fun term(text: String) = GlossaryTerm(
        arabicTerm = "التقوى", meaning = "Mindfulness", literalTranslation = "piety",
        displayTerm = "التقوى", englishPhrase = "God-consciousness",
        localizedPhrase = "God-consciousness", popupPhrase = "God-consciousness",
        popupLanguage = "en", translationStart = text.codePointCount(0, text.indexOf("التقوى")),
    )
    @Test fun danishHeadingUsesRenderedDanishAndNeverEnglishMetadata() {
        val text = "🌙 Vær gudsbevidst (التقوى)."
        assertEquals("🌙 Vær gudsbevidst", glossaryHeading(text, term(text), "da"))
        assertEquals("gudsbevidst", glossaryHeading(text, term(text).copy(localizedPhrase = "gudsbevidst"), "da"))
    }
    @Test fun staleEnglishHeadingDoesNotSurviveAnEdit() {
        val text = "Keep mindful devotion (التقوى)."
        assertEquals("Keep mindful devotion", glossaryHeading(text, term(text), "en"))
    }
}
