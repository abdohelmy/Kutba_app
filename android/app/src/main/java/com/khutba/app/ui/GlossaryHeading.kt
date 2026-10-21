package com.khutba.app.ui

import com.khutba.app.model.GlossaryTerm

internal fun glossaryHeading(text: String, term: GlossaryTerm, language: String): String {
    val neutral = if (language == "da") "Ordforklaring" else "Word meaning"
    val start = term.translationStart ?: return neutral
    if (start < 0 || start > text.codePointCount(0, text.length)) return neutral
    val preceding = text.substring(0, text.offsetByCodePoints(0, start))
        .replace(Regex("[(（]\\s*$"), "").trimEnd()
    val candidates = buildList {
        if (term.popupLanguage.isBlank() || term.popupLanguage == language) add(term.popupPhrase)
        add(if (language == "da") term.localizedPhrase else term.englishPhrase)
    }
    for (candidate in candidates.filter { it.isNotBlank() }) {
        val pattern = candidate.trim().split(Regex("\\s+")).joinToString("\\s+") { Regex.escape(it) }
        val match = Regex("(?<![\\p{L}\\p{N}_])$pattern\\s*$", RegexOption.IGNORE_CASE).find(preceding)
        if (match != null) return match.value.trimEnd()
    }
    return preceding.split(Regex("[\\r\\n.!?;:…,)]+")).last().trim().trimStart('‘', '’', '"', '“', '”').ifBlank { neutral }
}
