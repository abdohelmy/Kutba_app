package com.khutba.app.ui

import com.khutba.app.model.Citation
import com.khutba.app.model.GlossaryTerm
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import org.junit.Assert.*
import org.junit.Test

class ReaderTextTest {
    private fun source(start: Int? = null, end: Int? = null) = Citation(
        chunkId = "quran:2:152", sourceId = "quran.com:2:152", title = "Al-Baqarah 2:152",
        authority = "Quran.com", excerpt = "Remember Me.", sourceKind = "quran",
        arabicExcerpt = "فَاذْكُرُونِي", transliteration = "Fadhkuruni",
        url = "https://quran.com/2/152", translationStart = start, translationEnd = end,
    )

    @Test fun unicodeOffsetsKeepRepeatedCitationsAtTheirOwnOccurrence() {
        val text = "🌙 Remember Me. Again: Remember Me."
        val second = text.lastIndexOf("Remember")
        val start = text.codePointCount(0, second)
        assertEquals(text.length, citationInsertionPoint(text, source(start, start + 12)))
    }

    @Test fun ambiguousAndInvalidCitationsAreNotPlacedInline() {
        assertNull(citationInsertionPoint("Remember Me. Remember Me.", source()))
        assertNull(citationInsertionPoint("Remember Me.", source(0, 12).copy(anchorValid = false)))
        assertNull(citationInsertionPoint("A different quotation.", source()))
        assertEquals(12, citationInsertionPoint("Remember Me.", source()))
    }

    @Test fun completeGlossaryPhraseIsHighlightedAfterUnicode() {
        val phrase = "god-consciousness"
        val text = "🌙 $phrase (التقوى)"
        val term = GlossaryTerm("التقوى", "Mindfulness of Allah", phrase, phrase,
            translationStart = 2, translationEnd = 2 + phrase.length)
        val range = glossaryDisplayRange(text, term)!!
        assertEquals(phrase, text.substring(range))
    }

    @Test fun cacheSerializationPreservesArabicAndSourceDetails() {
        val original = source(0, 12)
        assertEquals(original, Json.decodeFromString<Citation>(Json.encodeToString(original)))
        val legacy = """{"chunk_id":"x","source_id":"y","title":"Title","authority":"Source","excerpt":"Quote"}"""
        assertTrue(Json.decodeFromString<Citation>(legacy).anchorValid)
    }

    @Test fun malformedUnicodeOffsetsAreRejected() {
        assertNull(codePointOffset("🌙", -1))
        assertNull(codePointOffset("🌙", 2))
        assertEquals(2, codePointOffset("🌙", 1))
    }
}
