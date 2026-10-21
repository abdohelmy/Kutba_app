package com.khutba.app.ui

import com.khutba.app.model.SentenceAlignment
import org.junit.Assert.assertEquals
import org.junit.Test

class SentenceAlignmentTest {
    private val links = listOf(SentenceAlignment(0, 6, 0, 5), SentenceAlignment(7, 14, 6, 12))

    @Test fun typingMovesFollowingSentenceAndPreservesSource() {
        val updated = moveAlignment(links, "First. Second.", "First word. Second.")
        assertEquals(11, updated[0].translationEnd)
        assertEquals(12, updated[1].translationStart)
        assertEquals(links[1].arabicStart, updated[1].arabicStart)
    }

    @Test fun replacementAcrossSentencesDiscardsUncertainLinks() {
        assertEquals(emptyList<SentenceAlignment>(), moveAlignment(links, "First. Second.", "New paragraph."))
    }

    @Test fun removingFirstSentencePreservesSecondSource() {
        val updated = moveAlignment(links, "First. Second.", "Second.")
        assertEquals(1, updated.size)
        assertEquals(0, updated.single().translationStart)
        assertEquals(6, updated.single().arabicStart)
    }
}
