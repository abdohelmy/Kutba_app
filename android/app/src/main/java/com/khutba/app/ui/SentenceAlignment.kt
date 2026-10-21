package com.khutba.app.ui

import com.khutba.app.model.SentenceAlignment

internal fun moveAlignment(links: List<SentenceAlignment>, before: String, after: String): List<SentenceAlignment> {
    if (before == after) return links
    var start = 0
    var suffix = 0
    while (start < minOf(before.length, after.length) && before[start] == after[start]) start++
    while (suffix < minOf(before.length, after.length) - start &&
        before[before.length - 1 - suffix] == after[after.length - 1 - suffix]) suffix++
    val end = before.length - suffix
    val delta = after.length - before.length
    return links.mapNotNull { link ->
        val a = link.translationStart
        val b = link.translationEnd
        when {
            b <= start && !(start == end && b == start && b == before.length) -> link
            a >= end && !(start == end && a == start) ->
                link.copy(translationStart = a + delta, translationEnd = b + delta)
            a <= start && b >= end && b + delta > a -> link.copy(translationEnd = b + delta)
            else -> null
        }
    }
}
