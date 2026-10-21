import io
import time
import wave
from datetime import date
from unittest.mock import AsyncMock

import pytest
from conftest import login_headers

from app.db.session import SessionLocal
from app.models import Sermon, SermonSegment, SermonStatus, VerificationStatus
from app.services import live_sessions as live
from app.services.live_matcher import LiveMatcher, normalize, words, speech_words, speech_similarity
from app.services.sentence_alignment import AlignedSentence

A = (
    "إن الصدق يهدي القلب ويجعل الإنسان ثابت الخطوات صافي النية "
    "حسن المعاملة مع جيرانه وأصحابه في كل يوم"
)
B = (
    "والأمانة مسؤولية عظيمة تشمل حفظ الحقوق وأداء الواجبات واحترام العهود "
    "وصيانة أسرار الناس والوفاء بما وعدنا والعمل بجد"
)
C = (
    "أما الرحمة فهي باب واسع لإصلاح المجتمع ورعاية الضعفاء ومساندة المحتاجين "
    "وتربية الأطفال على الرفق والاحترام وتقديم المساعدة"
)
D = (
    "والنصيحة تجمع القلوب وتبني الثقة بين أفراد الأسرة وتعين الجيران "
    "على التعاون وتجاوز الخلافات بالعدل والحكمة والصبر والتواضع"
)
E = (
    "التواضع فضيلة ترفع قدر الإنسان وتمنحه محبة الآخرين وتشجعه "
    "على قبول الحق والتعلم من الخبرات واحترام الناس"
)
F = (
    "الصبر طريق النجاح لأنه يساعد الطالب على الدراسة والمثابرة وتحقيق الأهداف "
    "والتغلب على الصعوبات دون يأس أو تردد"
)


@pytest.fixture(autouse=True)
def clear_live_buffers():
    live.SESSIONS.clear()
    live.WORKERS.clear()
    live.PREPARING.clear()
    live.ERRORS.clear()
    yield
    live.SESSIONS.clear()
    live.WORKERS.clear()
    live.PREPARING.clear()
    live.ERRORS.clear()


def test_normalization_and_offsets_preserve_original_text():
    assert normalize("أَقُولُ ــ هُدَى") == "اقول  هدي"
    matcher = LiveMatcher([("0", "🌙 أَقُولُ قولي")])
    assert matcher.script[0].start == 3
    assert matcher.tokens == ["اقول", "قولي"]


def test_spoken_blessing_matches_ligature_with_original_offsets():
    prefix = "🌙 ولقد جاء حث القرآن الكريم وهدي النبي "
    source = prefix + "ﷺ"
    matcher = LiveMatcher([("0", source)])
    assert words("ﷺ") == words("صلى الله عليه وسلم")
    assert matcher.tokens == words(prefix + "صلى الله عليه وسلم")
    start = len(prefix.encode("utf-16-le")) // 2
    assert all((word.start, word.end) == (start, start + 1) for word in matcher.script[-4:])
    assert matcher.update(prefix + "صلى الله عليه وسلم", 0)
    assert matcher.position == len(matcher.tokens) - 1
    assert matcher.sentences[0][1] == len(matcher.tokens)


def test_stutters_and_spelling_variations_preserve_distinctive_words():
    assert speech_words("حفظ حفظ الحقوق حفظ الحقوق وأداء الواجبات") == words("حفظ الحقوق وأداء الواجبات")
    assert speech_similarity(normalize("تبلى"), normalize("توبل")) >= 0.72
    assert speech_similarity("الباطنه", "البياطنة") >= 0.72
    assert speech_similarity("في", "من") == 0


def test_noisy_nearby_speech_needs_fresh_progress_not_repeated_audio():
    matcher = LiveMatcher([("0", ". ".join([A, B, C, D]))])
    matcher.update(A, 0)
    before = matcher.position
    first = "والامانه والامانه مسوولية عظيمة تشمل حفز الحقوق وادا الواجبات"
    second = "حفز الحقوق وادا الواجبات واحترام العهود وصيانه اسرار الناس والوفاء"
    def check(text, sequence, end):
        matcher.audio_end, matcher.audio_duration = end, 4
        return matcher.update_quick([hypothesis(text, "none", no_speech_prob=0.8)], sequence)
    assert check(first, 1, 100) is None
    assert matcher.last_diagnostic["reason"] == "awaiting_fresh_local_evidence"
    assert check(second, 2, 102) is None  # Overlapping 4-second audio cannot confirm.
    assert check(first, 3, 104) is None  # Repeating/stuttering isn't forward evidence.
    assert matcher.position == before
    assert check(second, 4, 106)
    assert matcher.last_diagnostic["independent_confirmation"]
    assert before < matcher.position < len(words(A)) + len(words(B))
    assert matcher.history == words(A)


def test_noisy_matching_does_not_accumulate_random_talk_or_skip_passages():
    matcher = LiveMatcher([("0", ". ".join([A, B, C, D]))])
    matcher.update(A, 0)
    before = matcher.position
    for sequence, text in enumerate([NOISE, NOISE, D, D, "قال الله سبحانه تعالى ورسوله"], 1):
        assert matcher.update_quick([hypothesis(text, "none", no_speech_prob=0.8)], sequence * 4) is None
        assert matcher.position == before


def test_network_delay_cannot_turn_overlapping_audio_into_confirmation():
    matcher = LiveMatcher([("0", ". ".join([A, B, C]))])
    matcher.update(A, 0)
    before = matcher.position
    matcher.audio_duration = 4
    matcher.audio_end = 100
    first = " ".join(B.split()[:7])
    second = " ".join(B.split()[3:12])
    assert matcher.update_quick([hypothesis(first, "none", no_speech_prob=0.8)], 1) is None
    matcher.audio_end = 106  # Network jitter: only two seconds of new captured audio.
    assert matcher.update_quick([hypothesis(second, "none", no_speech_prob=0.8)], 2) is None
    assert matcher.position == before
    matcher.audio_end = 108
    assert matcher.update_quick([hypothesis(second, "none", no_speech_prob=0.8)], 3)


def test_similar_neighboring_passages_do_not_supply_false_confirmation():
    matcher = LiveMatcher([("0", ". ".join([A, B, B]))])
    matcher.update(A, 0)
    before = matcher.position
    query = " ".join(B.split()[:8])
    for sequence in (4, 8):
        assert matcher.update_alternatives([hypothesis(query, "none", no_speech_prob=0.8)], sequence) is None
        assert matcher.last_diagnostic["reason"] == "ambiguous_nearby_passages"
        assert matcher.position == before


def test_cohere_distinctive_short_next_passage_advances_without_audio_scores():
    matcher = LiveMatcher([("0", A + ". حفظ الحقوق وأداء الواجبات. " + C)])
    matcher.update(A, 0)
    result = matcher.update_quick([hypothesis(
        "حفظ الحقوق وأداء الواجبات", "none", avg_logprob=None, no_speech_prob=None,
    )], 1)
    assert result
    assert matcher.last_diagnostic["text_only_strong_match"]
    assert matcher.position == len(words(A)) + 3


def test_unclear_chunk_preserves_pending_but_does_not_refresh_expiry():
    matcher = LiveMatcher([("0", A + ". " + B)])
    matcher.update(A, 0)
    matcher.audio_end, matcher.audio_duration = 100, 4
    item = hypothesis(" ".join(B.split()[:7]), "none", no_speech_prob=0.8)
    assert matcher.match_nearby([item], 1, quick=True) is None
    pending = matcher.local_pending
    assert pending is not None
    matcher.audio_end = 102
    assert matcher.match_nearby([hypothesis("كلام قصير", "none")], 2, quick=True) is None
    assert matcher.local_pending == pending
    matcher.audio_end = 125
    matcher.match_nearby([], 14, quick=True)
    assert matcher.local_pending is None


def test_fresh_following_passage_can_confirm_short_pending_passage():
    matcher = LiveMatcher([("0", A + ". حفظ الحقوق وأداء الواجبات. رعاية الضعفاء ومساندة المحتاجين.")])
    matcher.update(A, 0)
    matcher.audio_end, matcher.audio_duration = 100, 4
    assert matcher.match_nearby([hypothesis(
        "حفظ الحقوق وأداء الواجبات", "none", no_speech_prob=0.8,
    )], 1, quick=True) is None
    before = matcher.position
    matcher.audio_end, matcher.audio_duration = 102, 8
    following = hypothesis("رعاية الضعفاء ومساندة المحتاجين", "none", no_speech_prob=0.8)
    assert matcher.match_nearby([following], 2, quick=False) is None
    # Overlapping following speech keeps the first observation without
    # refreshing it or counting as independent confirmation.
    assert matcher.local_pending[1] == 100
    matcher.audio_end = 108
    assert matcher.match_nearby([following], 5, quick=False)
    assert matcher.position > before
    assert matcher.last_diagnostic["independent_confirmation"]


def test_passage_log_records_observations_not_skipped_text():
    matcher = LiveMatcher([("0", ". ".join([A, B, C, D]))])
    session = live.LiveSession("sermon", "mosque", "revision", matcher)
    assert live.record_passage(session, 0) is None
    matcher.update(A, 1)
    assert live.record_passage(session, 1) == 0
    matcher.update(C, 5)
    assert live.record_passage(session, 5) == 2
    assert sorted(session.confirmed_passages) == [0, 2]
    assert session.confirmed_passages[2] == {"first_sequence": 5, "last_sequence": 5}
    matcher.local_pending = (3, 100, 80, frozenset())
    live.reset_session_buffers(session)
    assert matcher.local_pending is None
    assert sorted(session.confirmed_passages) == [0, 2]


def test_fresh_confirmations_progress_and_off_script_holds():
    matcher = LiveMatcher([("0", A + ". " + B + ". " + C + ". " + D)])
    weak = A.split()
    for index in (4, 9, 14):
        weak[index] = "اختبار"
    weak = " ".join(weak)
    assert 0.72 <= matcher.candidate([normalize(word) for word in weak.split()]).confidence < 0.90
    assert matcher.update(weak, 0) is None
    assert matcher.update(weak, 1) is None  # The same audio/text isn't confirmation.
    assert matcher.update(B, 2) is not None
    original = matcher.position
    assert (
        matcher.update(
            (
                "السيارة الجديدة تحتاج إلى تغيير الزيت وفحص الإطارات قبل السفر "
                "إلى المدينة خلال العطلة الصيفية الطويلة"
            ),
            3,
        )
        is None
    )
    assert matcher.position == original
    assert matcher.state == "waiting"
    matcher.update(C, 4)
    assert matcher.update(D, 5) is not None
    assert matcher.position > original
    assert matcher.update(D, 5) is None  # Stale results cannot advance.


def test_strong_unique_first_chunk_starts_without_confirmation():
    matcher = LiveMatcher([("0", A + ". " + B + ". " + C)])
    assert matcher.update(A, 0) is not None
    assert matcher.state == "matched"
    position = matcher.position
    assert matcher.update(A, 1) is None
    assert matcher.position == position
    assert matcher.update("السيارة الجديدة تحتاج إلى فحص الإطارات قبل السفر في العطلة الصيفية", 2) is None
    assert matcher.position == position


def test_short_initial_chunk_still_needs_fresh_confirmation():
    matcher = LiveMatcher([("0", A + ". " + B)])
    assert matcher.update(" ".join(A.split()[:8]), 0) is None
    assert matcher.position is None


NOISE = (
    "السيارة الجديدة تحتاج إلى تغيير الزيت وفحص الإطارات قبل السفر "
    "إلى المدينة خلال العطلة الصيفية الطويلة"
)


def test_garbled_history_cannot_veto_a_strong_fresh_first_chunk():
    matcher = LiveMatcher([("0", A + ". " + B + ". " + C)])
    assert matcher.update(NOISE, 0) is None
    assert matcher.update(A, 1) is not None
    assert matcher.last_diagnostic["history_recovered"]
    assert matcher.last_diagnostic["query_source"] == "current_chunk"
    assert matcher.last_diagnostic["candidate_overlap"] == 1
    assert matcher.last_diagnostic["rolling_best_window_overlap"] < 0.72


def test_recovery_after_off_script_speech_holds_until_a_good_chunk():
    matcher = LiveMatcher([("0", A + ". " + B + ". " + C)])
    assert matcher.update(A, 0) is not None
    original = matcher.position
    assert matcher.update(NOISE, 1) is None
    assert matcher.position == original
    assert matcher.update(B, 2) is not None
    assert matcher.position > original
    assert matcher.last_diagnostic["history_recovered"]
    recovered = matcher.position
    assert matcher.update(B, 3) is None  # Duplicated audio is not fresh evidence.
    assert matcher.position == recovered


def test_recovered_weak_first_match_still_needs_confirmation():
    matcher = LiveMatcher([("0", A + ". " + B + ". " + C)])
    matcher.update(NOISE, 0)
    weak = A.split()
    for i in (4, 9, 14):
        weak[i] = "اختبار"
    weak = " ".join(weak)
    assert matcher.update(weak, 1) is None
    assert matcher.last_diagnostic["history_recovered"]
    assert matcher.last_diagnostic["reason"] == "awaiting_initial_confirmation"
    assert matcher.position is None
    assert matcher.update(weak, 2) is None
    assert matcher.position is None


def test_history_recovery_does_not_bypass_repetition_or_off_script_tail_checks():
    repeated = LiveMatcher([("0", (A + ". " + B + ". ") * 3)])
    repeated.update(NOISE, 0)
    assert repeated.update(A, 1) is None
    assert repeated.position is None
    assert repeated.last_diagnostic["current_chunk_reason"] == "ambiguous_repeated_passage"
    matcher = LiveMatcher([("0", A + ". " + B + ". " + C)])
    matcher.update(A, 0)
    original = matcher.position
    matcher.update(NOISE, 1)
    assert matcher.update(B + " فحص إطارات السيارة خلال العطلة الصيفية", 2) is None
    assert matcher.position == original


def test_matcher_diagnostics_explain_failures_without_storing_speech():
    matcher = LiveMatcher([("0", A + ". " + B)])
    matcher.update("", 0)
    assert matcher.last_diagnostic["reason"] == "empty_or_non_arabic_text"
    matcher.update("إن الصدق", 1)
    assert matcher.last_diagnostic["reason"] == "insufficient_new_words"
    matcher.update("سافر التاجر بالطائرة واشترى سيارة جديدة", 2)
    assert matcher.last_diagnostic["reason"] == "insufficient_distinct_script_words"
    matcher = LiveMatcher([("0", A + ". " + B)])
    matcher.update(A, 0)
    assert matcher.last_diagnostic["reason"] == "matched"
    assert matcher.last_diagnostic["candidate_overlap"] == 1
    assert all(not isinstance(v, (list, dict)) for v in matcher.last_diagnostic.values())


def test_large_skip_needs_two_distinct_confirmations():
    filler = ". ".join([C for _ in range(8)])
    matcher = LiveMatcher(
        [
            (
                "0",
                A + ". " + B + ". " + filler + ". " + D + ". " + E + ". " + F,
            )
        ]
    )
    matcher.update(A, 0)
    matcher.update(B, 1)
    original = matcher.position
    assert original is not None
    assert matcher.update(D, 2) is None
    assert matcher.position == original
    assert matcher.last_diagnostic["reason"] == "awaiting_jump_confirmation"
    assert (
        matcher.update(
            E,
            3,
        )
        is not None
    )
    assert matcher.position > original + 60  # Two fresh passages, not one, confirm the jump.
    assert (
        matcher.update(
            F,
            4,
        )
        is not None
    )
    assert matcher.position > original + 60


def test_repeated_formula_alone_cannot_reanchor():
    matcher = LiveMatcher([("0", (A + ". " + B + ". ") * 3)])
    assert matcher.update(A, 0) is None
    assert matcher.update(B, 1) is None
    assert matcher.position is None
    assert matcher.update("قال الله تعالى رسول الله صلى الله عليه وسلم قال الله تعالى", 2) is None


def hypothesis(text, reference="current", **quality):
    return dict(text=text, reference=reference, avg_logprob=-0.3,
                no_speech_prob=0.02, compression_ratio=1.2) | quality


def test_cohere_null_acoustic_scores_support_full_and_quick_matches():
    from app.api.routes.live import TranscriptCandidate
    def candidate(text):
        return TranscriptCandidate(reference="none", text=text, avg_logprob=None,
                                   no_speech_prob=None, compression_ratio=1.2).model_dump()
    matcher = LiveMatcher([("0", ". ".join([A, B, C]))])
    assert matcher.update_alternatives([candidate(A)], 0)
    assert matcher.update_quick([candidate(" ".join(B.split()[:7]))], 1)
    before = matcher.position
    assert matcher.update_quick([candidate(NOISE)], 2) is None
    assert matcher.position == before


def test_sentence_hints_follow_heard_position_across_segments_and_end():
    matcher = LiveMatcher([("0", "🌙 " + A + ".\n" + B + "."), ("1", C)])
    assert [item["text"] for item in matcher.references()] == [normalize(A), normalize(B)]
    matcher.update(B, 0)
    assert [item["text"] for item in matcher.references()] == [normalize(B), normalize(C)]
    matcher.update(C, 1)
    assert matcher.references() == [{"reference":"current", "text":normalize(C)}]
    assert LiveMatcher([]).references() == []
    long = LiveMatcher([("0", " ".join([A] * 100))])
    assert len(long.references()[0]["text"]) <= 1200
    assert len(long.references()[0]["text"].split()) <= 60


def test_two_hypotheses_choose_better_match_but_update_once():
    matcher = LiveMatcher([("0", A + ". " + B + ". " + C)])
    assert matcher.update_alternatives([hypothesis(NOISE), hypothesis(A, "next")], 0)
    assert matcher.last_diagnostic["selected_reference"] == "next"
    assert matcher.history == [normalize(word) for word in A.split()]
    position = matcher.position
    assert matcher.update_alternatives([hypothesis(B), hypothesis(C, "next")], 0) is None
    assert matcher.position == position


def test_two_weak_hypotheses_are_not_two_initial_confirmations():
    matcher = LiveMatcher([("0", A + ". " + B + ". " + C)])
    weak = A.split()
    for i in (4, 9, 14):
        weak[i] = "اختبار"
    weak = " ".join(weak)
    assert matcher.update_alternatives([hypothesis(weak), hypothesis(weak, "next")], 0) is None
    assert matcher.position is None
    assert matcher.last_diagnostic["reason"] == "awaiting_initial_confirmation"
    assert matcher.update_alternatives([hypothesis(B), hypothesis(B, "next")], 1)


@pytest.mark.parametrize("quality", [{"avg_logprob":-1.2}, {"no_speech_prob":0.9}, {"compression_ratio":3.0}])
def test_reference_matching_cannot_override_poor_audio_evidence(quality):
    matcher = LiveMatcher([("0", A + ". " + B)])
    assert matcher.update_alternatives([hypothesis(A, **quality)], 0) is None
    assert matcher.position is None
    assert matcher.last_diagnostic["reason"] == "unreliable_speech"


def test_biased_and_conflicting_hypotheses_hold_position():
    matcher = LiveMatcher([("0", A + ". " + B + ". " + C)])
    assert matcher.update_alternatives([hypothesis(NOISE, avg_logprob=-0.1),
                                       hypothesis(A, "next", avg_logprob=-0.9)], 0) is None
    assert matcher.position is None
    assert matcher.update_alternatives([hypothesis(A), hypothesis(B, "next")], 1) is None
    assert matcher.last_diagnostic["reason"] == "conflicting_transcriptions"
    assert matcher.position is None


def test_quick_check_only_enters_next_sentence_without_polluting_history():
    matcher = LiveMatcher([("0", ". ".join([A, B, C, D]))])
    assert matcher.update_quick([hypothesis(B, "none")], 0) is None
    assert matcher.position is None
    matcher.update(A, 1)
    history = matcher.history.copy()
    before = matcher.position
    assert matcher.update_quick([hypothesis(C, "none")], 2) is None
    assert matcher.position == before  # A perfect later sentence cannot skip B.
    assert matcher.update_quick([hypothesis(" ".join(B.split()[:7]), "none")], 3)
    assert matcher.position == len(A.split()) + 6
    assert matcher.last_diagnostic["reason"] == "quick_next_sentence"
    assert matcher.history == history
    position = matcher.position
    # A later full check may include an overlapping tail behind the quick result.
    matcher.update(" ".join(B.split()[:5]), 4)
    assert matcher.position >= position


def test_moderate_no_speech_score_requires_strong_next_passage_evidence():
    matcher = LiveMatcher([("0", ". ".join([A, B, C]))])
    matcher.update(A, 0)
    before, history = matcher.position, matcher.history.copy()
    # Even exact later text cannot bypass the next-passage rule.
    assert matcher.update_quick([hypothesis(C, "none", no_speech_prob=0.65)], 1) is None
    short = " ".join(B.split()[:5])
    assert matcher.update_quick([hypothesis(short, "none", no_speech_prob=0.65)], 2) is None
    text = " ".join(B.split()[:7])
    assert matcher.update_quick([hypothesis(text, "none", no_speech_prob=0.65,
                                          avg_logprob=-0.5)], 3) is None
    assert matcher.position == before
    assert matcher.update_quick([hypothesis(text, "none", no_speech_prob=0.65)], 4)
    assert matcher.position == len(words(A)) + 6
    assert matcher.history == history


def test_moderate_no_speech_score_cannot_accept_partial_match():
    matcher = LiveMatcher([("0", ". ".join([A, B, C]))])
    matcher.update(A, 0)
    before = matcher.position
    text = " ".join(B.split()[:6] + ["اختبار"])
    assert matcher.update_quick([hypothesis(text, "none", no_speech_prob=0.65)], 1) is None
    assert matcher.position == before


def test_reader_mappings_split_comma_joined_arabic_for_quick_checks():
    text = "🌙 " + A + "، " + B + "، " + C + "."
    source = text.encode("utf-16-le")
    first_end = len(("🌙 " + A).encode("utf-16-le")) // 2
    second_start = first_end + 2
    second_end = second_start + len(B)
    third_start = second_end + 2
    matcher = LiveMatcher([("0", text)], {"0": [(3,first_end),(second_start,second_end),
                                               (third_start,len(source)//2)]})
    assert [(a,b) for a,b,_ in matcher.sentences] == [
        (0,len(A.split())), (len(A.split()),len(A.split())+len(B.split())),
        (len(A.split())+len(B.split()),len(A.split())+len(B.split())+len(C.split()))]
    assert matcher.update(A,0)
    previous = matcher.position
    assert matcher.update_quick([hypothesis(" ".join(C.split()[:7]),"none")],1) is None
    assert matcher.position == previous
    assert matcher.update_quick([hypothesis(" ".join(B.split()[:7]),"none")],2)
    assert matcher.last_diagnostic["reason"] == "quick_next_sentence"
    assert matcher.references()[0]["text"] == normalize(B)
    assert matcher.references()[1]["text"] == normalize(C)
    # Invalid mappings must not create out-of-source passages or split words.
    invalid = LiveMatcher([("0",text)],{"0":[(-1,first_end),(0,999999)]})
    assert len(invalid.sentences) == 1


@pytest.mark.parametrize("text,quality", [
    (NOISE, {}), (" ".join(B.split()[:4]), {}),
    (B, {"no_speech_prob": 0.8}), (B, {"avg_logprob": -0.9}),
    (B, {"compression_ratio": 3}),
    (B + " السيارة الجديدة تحتاج تغيير الزيت", {}),
])
def test_quick_check_rejects_short_uncertain_and_off_script_speech(text, quality):
    matcher = LiveMatcher([("0", ". ".join([A, B, C]))])
    matcher.update(A, 0)
    position = matcher.position
    matcher.pending = len(A.split()) + len(B.split()) + 8
    pending = matcher.pending
    assert matcher.update_quick([hypothesis(text, "none", **quality)], 1) is None
    assert matcher.position == position and matcher.pending == pending
    assert matcher.state == "matched"


def test_quick_check_cannot_jump_far_into_long_next_sentence_or_use_a_hint():
    matcher = LiveMatcher([("0", A + ". " + B + " " + C + " " + D)])
    matcher.update(A, 0)
    position = matcher.position
    assert matcher.update_quick([hypothesis(D, "none")], 1) is None
    assert matcher.update_quick([hypothesis(B, "next")], 2) is None
    assert matcher.position == position
    assert matcher.update_quick([hypothesis(B, "none")], 3)
    assert matcher.position - position <= 24
    accepted = matcher.position
    assert matcher.update_quick([hypothesis(C, "none")], 3) is None
    assert matcher.position == accepted


def sermon(accounts):
    with SessionLocal() as db:
        text = A + ". " + B + ". " + C + ". " + D
        row = Sermon(
            mosque_id=accounts["mosque_id"],
            title="Live test",
            khutba_date=date.today(),
            target_language="en",
            source_file_path="test.pdf",
            source_file_sha256="a" * 64,
            arabic_text=text,
            status=SermonStatus.PUBLISHED,
            created_by=accounts["admin_id"],
            segments=[
                SermonSegment(
                    ordinal=0,
                    arabic_text=text,
                    translated_text=(
                        "Be truthful. Fulfil your responsibilities. Show mercy. Offer advice."
                    ),
                    verification_status=VerificationStatus.HUMAN_APPROVED,
                )
            ],
        )
        db.add(row)
        db.commit()
        segment = row.segments[0]
        segment.live_alignment = {
            "revision": live.segment_revision(segment),
            "links": [
                {
                    "translation_start": 0,
                    "translation_end": 12,
                    "arabic_start": 0,
                    "arabic_end": len(A),
                },
                {
                    "translation_start": 13,
                    "translation_end": 42,
                    "arabic_start": len(A) + 2,
                    "arabic_end": len(A) + len(B) + 2,
                },
            ],
        }
        db.commit()
        return row.id, segment.id


def wav():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\0\0" * 16000)
    return buffer.getvalue()


def test_session_permissions_worker_token_audio_and_stale_results(
    client, seeded_accounts, owner_headers
):
    sermon_id, segment_id = sermon(seeded_accounts)
    admin = login_headers(client, "admin", "correct-horse-123")
    path = f"/api/v1/admin/sermons/{sermon_id}/live"
    assert client.post(path, json={"action": "start"}).status_code == 401
    assert client.post("/api/v1/owner/live-worker-token", headers=admin).status_code == 403
    assert client.post(path, headers=admin, json={"action": "start"}).status_code == 503
    token = client.post("/api/v1/owner/live-worker-token", headers=owner_headers).json()["token"]
    worker = {"Authorization": "Bearer " + token}
    assert client.get("/api/v1/live-worker/job", headers=admin).status_code == 401
    assert client.get("/api/v1/live-worker/job", headers=worker).status_code == 204
    started = client.post(path, headers=admin, json={"action": "start"})
    assert started.status_code == 200
    session_id = started.json()["session_id"]
    assert client.post(path, headers=admin, json={"action": "start"}).status_code == 409
    for sequence, text in enumerate([A, B]):
        live.SESSIONS[sermon_id].audio_received = 0
        result = client.post(
            path + f"/audio?session_id={session_id}&sequence={sequence}",
            headers=admin,
            files={"file": ("speech.wav", wav(), "audio/wav")},
        )
        assert result.status_code == 202
        job = client.get("/api/v1/live-worker/job" + ("?semantic_shadow=true" if sequence else ""),
                         headers=worker).json()
        assert "arabic_text" not in job
        if sequence:
            assert job["semantic_passages"][0] == {"index": 0, "text": A}
        else:
            assert "semantic_passages" not in job
        assert [item["reference"] for item in job["references"]] == ["current", "next"]
        payload = {"session_id": session_id, "job_id": job["job_id"], "text": text,
                   "debug": sequence == 0}
        if sequence == 1:
            payload.pop("text")
            payload["candidates"] = [hypothesis(NOISE), hypothesis(B, "next")]
            invalid = payload | {"candidates": [hypothesis(A)] * 4}
            assert client.post("/api/v1/live-worker/result", headers=worker, json=invalid).status_code == 422
        accepted = client.post(
                "/api/v1/live-worker/result",
                headers=worker,
                json=payload,
            )
        assert accepted.status_code == 200
        if sequence == 0:
            details = accepted.json()["debug"]
            assert details["reason"] == "matched" and details["highlight_count"] == 1
            assert A not in accepted.text and "text" not in details
        else:
            assert accepted.json() == {"status":"accepted"}
        assert (
            client.post(
                "/api/v1/live-worker/result",
                headers=worker,
                json={"session_id": session_id, "job_id": job["job_id"], "text": text},
            ).status_code
            == 409
        )
    public = client.get(f"/api/v1/reader/sermons/{sermon_id}/live").json()
    assert public["status"] == "matched"
    assert public["highlights"][0]["segment_id"] == segment_id
    assert public["highlights"][0]["excerpt"] == "Fulfil your responsibilities."
    assert "arabic_text" not in public
    assert (
        client.post(
            path, headers=admin, json={"action": "pause", "session_id": "wrong"}
        ).status_code
        == 409
    )
    assert (
        client.post(path, headers=admin, json={"action": "pause", "session_id": session_id}).json()[
            "status"
        ]
        == "paused"
    )
    assert (
        client.post(
            path, headers=admin, json={"action": "resume", "session_id": session_id}
        ).json()["audio_sequence"]
        == 1
    )
    with SessionLocal() as db:
        db.get(SermonSegment, segment_id).translated_text = "Edited text"
        db.commit()
    assert not client.get(f"/api/v1/reader/sermons/{sermon_id}/live").json()["active"]
    assert (
        client.delete("/api/v1/owner/live-worker-token", headers=owner_headers).status_code == 204
    )
    assert client.get("/api/v1/live-worker/job", headers=worker).status_code == 401


def test_quick_job_mode_is_server_owned_and_full_jobs_take_priority(client, seeded_accounts, owner_headers):
    sermon_id, _ = sermon(seeded_accounts)
    admin = login_headers(client, "admin", "correct-horse-123")
    token = client.post("/api/v1/owner/live-worker-token", headers=owner_headers).json()["token"]
    worker = {"Authorization": "Bearer " + token}
    client.get("/api/v1/live-worker/job", headers=worker)
    path = f"/api/v1/admin/sermons/{sermon_id}/live"
    session_id = client.post(path, headers=admin, json={"action":"start"}).json()["session_id"]
    session = live.SESSIONS[sermon_id]
    opening = client.get(f"/api/v1/reader/sermons/{sermon_id}/live").json()
    assert opening["provisional"] and opening["highlights"][0]["excerpt"] == "Be truthful."
    assert session.matcher.position is None and session.matcher.pending is None

    def upload(sequence, kind):
        session.audio_received = 0
        return client.post(path + f"/audio?session_id={session_id}&sequence={sequence}&kind={kind}",
                           headers=admin, files={"file":("speech.wav", wav(), "audio/wav")})

    assert upload(0, "quick").json()["status"] == "skipped"
    assert not session.jobs
    session.matcher.update(A, 0)
    assert upload(1, "quick").status_code == 202
    job = client.get("/api/v1/live-worker/job", headers=worker).json()
    assert job["kind"] == "quick" and job["references"] == []
    before = session.matcher.position
    # Supplying a full-mode flag in the result must not bypass the queued mode.
    response = client.post("/api/v1/live-worker/result", headers=worker, json={
        "session_id":session_id, "job_id":job["job_id"], "kind":"full",
        "candidates":[hypothesis(D, "none")], "debug":True})
    assert response.status_code == 200 and session.matcher.position == before
    assert response.json()["debug"]["kind"] == "quick"
    upload(2, "quick")
    upload(3, "full")
    assert [(j.sequence,j.kind) for j in session.jobs] == [(3,"full")]
    assert upload(4, "quick").json()["status"] == "skipped"
    assert [(j.sequence,j.kind) for j in session.jobs] == [(3,"full")]
    job = client.get("/api/v1/live-worker/job", headers=worker).json()
    assert job["kind"] == "full"
    assert len(job["references"]) == 2


@pytest.mark.parametrize("kind,age", [("quick", 9), ("full", 17)])
def test_delayed_result_holds_highlight_and_records_no_coverage(client, seeded_accounts, owner_headers, kind, age):
    sermon_id, _ = sermon(seeded_accounts)
    admin = login_headers(client, "admin", "correct-horse-123")
    token = client.post("/api/v1/owner/live-worker-token", headers=owner_headers).json()["token"]
    worker = {"Authorization": "Bearer " + token}
    client.get("/api/v1/live-worker/job", headers=worker)
    path = f"/api/v1/admin/sermons/{sermon_id}/live"
    session_id = client.post(path, headers=admin, json={"action":"start"}).json()["session_id"]
    session = live.SESSIONS[sermon_id]
    session.matcher.update(A, 0)
    before = session.matcher.position
    job = live.AudioJob(sequence=1, audio=wav(), kind=kind, created=time.monotonic()-age)
    session.jobs.append(job)
    claimed = client.get("/api/v1/live-worker/job", headers=worker).json()
    response = client.post("/api/v1/live-worker/result", headers=worker, json={
        "session_id":session_id, "job_id":claimed["job_id"],
        "candidates":[hypothesis(B, "none")], "debug":True})
    assert response.status_code == 200
    debug = response.json()["debug"]
    assert debug["reason"] == "delayed_audio_ignored"
    assert debug["result_age_ms"] >= age*1000
    assert debug["queue_wait_ms"] >= age*1000
    assert debug["confirmed_passages"] == [] and debug["observed_passage"] is None
    assert session.matcher.position == before
    assert not session.jobs


def test_provisional_opening_does_not_prevent_mid_sermon_acquisition(client, seeded_accounts):
    sermon_id, _ = sermon(seeded_accounts)
    with SessionLocal() as db:
        row = db.get(Sermon, sermon_id)
        matcher = LiveMatcher([("0", row.arabic_text)])
        live.SESSIONS[sermon_id] = live.LiveSession(sermon_id, row.mosque_id,
                                                 live.sermon_revision(row), matcher)
        assert live.public_state(row, sermon_id)["provisional"]
        assert matcher.update_alternatives([hypothesis(NOISE),hypothesis(NOISE,"next"),
                                            hypothesis(B,"none")],3)
        state = live.public_state(row, sermon_id)
        assert not state["provisional"]
        assert state["highlights"][0]["excerpt"] == "Fulfil your responsibilities."
        # A late reader immediately receives the existing confirmed location.
        assert live.public_state(row, sermon_id)["highlights"] == state["highlights"]


def test_next_passage_preview_persists_until_confirmed_progress(seeded_accounts):
    sermon_id, _ = sermon(seeded_accounts)
    with SessionLocal() as db:
        row = db.get(Sermon, sermon_id)
        matcher = LiveMatcher([("0", row.arabic_text)])
        session = live.LiveSession(sermon_id, row.mosque_id, live.sermon_revision(row), matcher)
        live.SESSIONS[sermon_id] = session
        live.WORKERS["test"] = time.monotonic()
        session.audio_received = time.monotonic()
        matcher.position = 2
        assert not live.public_state(row, sermon_id)["tentative_highlights"]
        matcher.position = len(words(A)) - 3
        before = matcher.position
        assert matcher.local_pending is None
        state = live.public_state(row, sermon_id)
        assert state["highlights"][0]["excerpt"] == "Be truthful."
        assert state["tentative_highlights"][0]["excerpt"] == "Fulfil your responsibilities."
        assert matcher.position == before and not session.confirmed_passages
        session.paused = True
        assert live.public_state(row, sermon_id)["tentative_highlights"] == state["tentative_highlights"]
        session.paused = False
        session.audio_received = time.monotonic() - 60
        live.WORKERS.clear()
        assert live.public_state(row, sermon_id)["tentative_highlights"] == state["tentative_highlights"]
        matcher.position = len(words(A)) + 1
        assert live.public_state(row, sermon_id)["highlights"] == [
            {k: v for k, v in h.items() if k != "basis"} for h in state["tentative_highlights"]
        ]
        assert not live.public_state(row, sermon_id)["tentative_highlights"]
        matcher.position = len(matcher.tokens) - 1
        assert not live.public_state(row, sermon_id)["tentative_highlights"]


def test_preview_timer_estimates_completion_and_upgrades_without_moving_green(seeded_accounts, monkeypatch):
    sermon_id, _ = sermon(seeded_accounts)
    now = time.monotonic()
    monkeypatch.setattr(live.time, "monotonic", lambda: now)
    with SessionLocal() as db:
        row = db.get(Sermon, sermon_id)
        matcher = LiveMatcher([("0", row.arabic_text)])
        session = live.LiveSession(sermon_id, row.mosque_id, live.sermon_revision(row), matcher)
        live.SESSIONS[sermon_id] = session
        live.WORKERS["test"] = now
        session.audio_received = now
        matcher.position = 3
        matcher.audio_end = now
        live.record_passage(session, 1)
        assert not live.public_state(row, sermon_id)["tentative_highlights"]
        delay = (len(words(A)) - 4) / 2
        now += delay - .1
        session.audio_received = now
        assert not live.public_state(row, sermon_id)["tentative_highlights"]
        now += .2
        session.audio_received = now
        state = live.public_state(row, sermon_id)
        assert state["tentative_highlights"][0]["excerpt"] == "Fulfil your responsibilities."
        assert state["tentative_highlights"][0]["basis"] == "timer"
        assert matcher.position == 3
        matcher.position = len(words(A)) - 3
        state = live.public_state(row, sermon_id)
        assert state["tentative_highlights"][0]["basis"] == "words"
        # A later timer-only estimate must not downgrade the latched cue.
        matcher.position = 3
        assert live.public_state(row, sermon_id)["tentative_highlights"] == state["tentative_highlights"]
        session.paused = True
        live.reset_session_buffers(session)
        now += 20
        assert live.public_state(row, sermon_id)["tentative_highlights"] == state["tentative_highlights"]
        matcher.position = len(words(A)) + 1
        assert not live.public_state(row, sermon_id)["tentative_highlights"]


def test_preview_timer_does_not_start_from_stale_audio(seeded_accounts):
    sermon_id, _ = sermon(seeded_accounts)
    with SessionLocal() as db:
        row = db.get(Sermon, sermon_id)
        matcher = LiveMatcher([("0", row.arabic_text)])
        session = live.LiveSession(sermon_id, row.mosque_id, live.sermon_revision(row), matcher)
        live.SESSIONS[sermon_id] = session
        live.WORKERS["test"] = time.monotonic()
        matcher.position = 3
        matcher.audio_end = time.monotonic() - 10
        session.audio_received = matcher.audio_end
        live.record_passage(session, 1)
        assert not live.public_state(row, sermon_id)["tentative_highlights"]


def test_quick_checks_do_not_expire_full_jump_confirmation():
    matcher = LiveMatcher([("0", ". ".join([A,B,C,D,E,F]))])
    matcher.update(A,3)
    assert matcher.update(E,7) is None
    assert matcher.pending is not None
    position = matcher.position
    for sequence in (8,9,10):
        assert matcher.update_quick([hypothesis(NOISE,"none")],sequence) is None
        assert matcher.position == position
    assert matcher.update(F,11)
    assert matcher.position > position + 60


def test_third_hypothesis_conflict_is_not_ignored():
    matcher = LiveMatcher([("0", ". ".join([A,B,C,D]))])
    assert matcher.update_alternatives([hypothesis(A),hypothesis(A,"next"),hypothesis(C,"none")],0) is None
    assert matcher.position is None
    assert matcher.last_diagnostic["reason"] == "conflicting_transcriptions"


def test_wav_validation_and_buffer_limits(client, seeded_accounts, owner_headers):
    with pytest.raises(ValueError):
        live.validate_wav(b"not wav")
    with pytest.raises(ValueError):
        live.validate_wav(b"x" * (live.MAX_AUDIO_BYTES + 1))
    live.validate_wav(wav())
    sermon_id, _ = sermon(seeded_accounts)
    admin = login_headers(client, "admin", "correct-horse-123")
    token = client.post("/api/v1/owner/live-worker-token", headers=owner_headers).json()["token"]
    client.get("/api/v1/live-worker/job", headers={"Authorization": "Bearer " + token})
    path = f"/api/v1/admin/sermons/{sermon_id}/live"
    session_id = client.post(path, headers=admin, json={"action": "start"}).json()["session_id"]
    for sequence in range(6):
        live.SESSIONS[sermon_id].audio_received = 0
        assert (
            client.post(
                path + f"/audio?session_id={session_id}&sequence={sequence}",
                headers=admin,
                files={"file": ("a.wav", wav(), "audio/wav")},
            ).status_code
            == 202
        )
    assert len(live.SESSIONS[sermon_id].jobs) == 2
    live.SESSIONS[sermon_id].touched = time.monotonic() - 100
    assert not client.get(f"/api/v1/reader/sermons/{sermon_id}/live").json()["active"]


def test_prepare_is_cached_and_never_changes_published_text(
    client, seeded_accounts, owner_headers, monkeypatch
):
    sermon_id, segment_id = sermon(seeded_accounts)
    with SessionLocal() as db:
        segment = db.get(SermonSegment, segment_id)
        original = segment.translated_text
        segment.live_alignment = {}
        db.commit()
    fake = AsyncMock(
        return_value=[
            AlignedSentence(
                translation_start=0, translation_end=12, arabic_start=0, arabic_end=len(A)
            )
        ]
    )
    monkeypatch.setattr(live, "align_sentences", fake)
    token = client.post("/api/v1/owner/live-worker-token", headers=owner_headers).json()["token"]
    worker = {"Authorization": "Bearer " + token}
    client.get("/api/v1/live-worker/job", headers=worker)
    headers = login_headers(client, "admin", "correct-horse-123")
    path = f"/api/v1/admin/sermons/{sermon_id}/live"
    assert client.post(path + "/prepare", headers=headers).status_code == 202
    assert client.get(path, headers=headers).json()["mapping_ready"]
    assert client.post(path + "/prepare", headers=headers).status_code == 202
    assert fake.await_count == 1
    with SessionLocal() as db:
        assert db.get(SermonSegment, segment_id).translated_text == original
        assert db.get(Sermon, sermon_id).status == SermonStatus.PUBLISHED


def test_publish_prepares_without_worker_and_reuses_saved_editing_map(
    client, seeded_accounts, monkeypatch
):
    sermon_id, segment_id = sermon(seeded_accounts)
    with SessionLocal() as db:
        db.get(Sermon, sermon_id).status = SermonStatus.REVIEW_REQUIRED
        db.commit()
    align = AsyncMock(side_effect=AssertionError("Unchanged editing map must be reused"))
    monkeypatch.setattr(live, "align_sentences", align)
    headers = login_headers(client, "admin", "correct-horse-123")
    response = client.post(f"/api/v1/admin/sermons/{sermon_id}/publish", headers=headers)
    assert response.status_code == 200
    assert not live.WORKERS
    align.assert_not_awaited()
    with SessionLocal() as db:
        assert live.mapping_ready(db.get(Sermon, sermon_id))
        assert db.get(SermonSegment, segment_id).live_alignment["links"]


def test_publish_prepares_only_missing_passages_and_failure_does_not_block_reading(
    client, seeded_accounts, monkeypatch
):
    sermon_id, segment_id = sermon(seeded_accounts)
    with SessionLocal() as db:
        row = db.get(Sermon, sermon_id)
        row.status = SermonStatus.REVIEW_REQUIRED
        row.segments.append(SermonSegment(
            ordinal=1, arabic_text=C, translated_text="Show mercy.",
            verification_status=VerificationStatus.HUMAN_APPROVED,
        ))
        original_map = db.get(SermonSegment, segment_id).live_alignment
        db.commit()
    align = AsyncMock(side_effect=RuntimeError("Provider unavailable"))
    monkeypatch.setattr(live, "align_sentences", align)
    headers = login_headers(client, "admin", "correct-horse-123")
    path = f"/api/v1/admin/sermons/{sermon_id}"
    assert client.post(path + "/publish", headers=headers).status_code == 200
    align.assert_awaited_once_with(C, "Show mercy.", None)
    assert client.get(f"/api/v1/reader/sermons/{sermon_id}").status_code == 200
    status = client.get(path + "/live", headers=headers).json()
    assert status["preparation_error"] and not status["mapping_ready"]
    assert align.await_count == 1  # Polling must not loop/rebill failed attempts.
    with SessionLocal() as db:
        assert db.get(SermonSegment, segment_id).live_alignment == original_map
    align.side_effect = None
    align.return_value = [AlignedSentence(
        translation_start=0, translation_end=11, arabic_start=0, arabic_end=len(C),
    )]
    assert client.post(path + "/live/prepare", headers=headers).status_code == 202
    assert client.get(path + "/live", headers=headers).json()["mapping_ready"]
    assert not live.ERRORS


def test_old_publication_recovers_automatically_without_a_worker(
    client, seeded_accounts, monkeypatch
):
    sermon_id, segment_id = sermon(seeded_accounts)
    with SessionLocal() as db:
        db.get(SermonSegment, segment_id).live_alignment = {}
        db.commit()
    align = AsyncMock(return_value=[AlignedSentence(
        translation_start=0, translation_end=12, arabic_start=0, arabic_end=len(A),
    )])
    monkeypatch.setattr(live, "align_sentences", align)
    headers = login_headers(client, "admin", "correct-horse-123")
    path = f"/api/v1/admin/sermons/{sermon_id}/live"
    assert client.get(path, headers=headers).json()["preparing"]
    assert client.get(path, headers=headers).json()["mapping_ready"]
    align.assert_awaited_once()
    assert not live.WORKERS


def test_publishing_danish_prepares_danish_without_remapping_english(
    client, seeded_accounts, monkeypatch
):
    from app.services.danish import english_revision

    sermon_id, _ = sermon(seeded_accounts)
    with SessionLocal() as db:
        parent = db.get(Sermon, sermon_id)
        child = Sermon(
            mosque_id=parent.mosque_id, english_sermon_id=parent.id,
            english_revision=english_revision(parent), title="Dansk",
            khutba_date=parent.khutba_date, target_language="da",
            source_file_path=parent.source_file_path,
            source_file_sha256=parent.source_file_sha256, arabic_text=parent.arabic_text,
            status=SermonStatus.REVIEW_REQUIRED, created_by=parent.created_by,
            segments=[SermonSegment(
                ordinal=0, arabic_text=parent.arabic_text, translated_text="Vær sandfærdig.",
                verification_status=VerificationStatus.HUMAN_APPROVED,
            )],
        )
        db.add(child)
        db.commit()
        child_id, arabic, english = child.id, parent.arabic_text, parent.segments[0].translated_text
    align = AsyncMock(return_value=[AlignedSentence(
        translation_start=0, translation_end=15, arabic_start=0, arabic_end=len(A),
    )])
    monkeypatch.setattr(live, "align_sentences", align)
    headers = login_headers(client, "admin", "correct-horse-123")
    assert client.post(f"/api/v1/admin/sermons/{child_id}/publish", headers=headers).status_code == 200
    align.assert_awaited_once_with(arabic, "Vær sandfærdig.", english)
    with SessionLocal() as db:
        assert live.mapping_ready(db.get(Sermon, child_id))


def test_pause_drops_claimed_audio_and_results_after_worker_revocation(
    client, seeded_accounts, owner_headers
):
    sermon_id, _ = sermon(seeded_accounts)
    token = client.post("/api/v1/owner/live-worker-token", headers=owner_headers).json()["token"]
    worker = {"Authorization": "Bearer " + token}
    client.get("/api/v1/live-worker/job", headers=worker)
    admin = login_headers(client, "admin", "correct-horse-123")
    path = f"/api/v1/admin/sermons/{sermon_id}/live"
    session_id = client.post(path, headers=admin, json={"action": "start"}).json()["session_id"]
    client.post(
        path + f"/audio?session_id={session_id}&sequence=0",
        headers=admin,
        files={"file": ("a.wav", wav(), "audio/wav")},
    )
    job = client.get("/api/v1/live-worker/job", headers=worker).json()
    client.post(path, headers=admin, json={"action": "pause", "session_id": session_id})
    assert not live.SESSIONS[sermon_id].jobs
    assert (
        client.post(
            "/api/v1/live-worker/result",
            headers=worker,
            json={"session_id": session_id, "job_id": job["job_id"], "text": A},
        ).status_code
        == 409
    )
    client.post("/api/v1/owner/live-worker-token", headers=owner_headers)
    assert client.get("/api/v1/live-worker/job", headers=worker).status_code == 401


def test_danish_uses_the_same_arabic_position_with_its_own_offsets(
    client, seeded_accounts, owner_headers
):
    from app.services.danish import english_revision

    sermon_id, _ = sermon(seeded_accounts)
    with SessionLocal() as db:
        parent = db.get(Sermon, sermon_id)
        child = Sermon(
            mosque_id=parent.mosque_id,
            english_sermon_id=parent.id,
            english_revision=english_revision(parent),
            title="Dansk",
            khutba_date=parent.khutba_date,
            target_language="da",
            source_file_path=parent.source_file_path,
            source_file_sha256=parent.source_file_sha256,
            arabic_text=parent.arabic_text,
            status=SermonStatus.PUBLISHED,
            created_by=parent.created_by,
            segments=[
                SermonSegment(
                    ordinal=0,
                    arabic_text=parent.arabic_text,
                    translated_text="Vær sandfærdig. Opfyld dine pligter.",
                    verification_status=VerificationStatus.HUMAN_APPROVED,
                )
            ],
        )
        db.add(child)
        db.commit()
        segment = child.segments[0]
        segment.live_alignment = {
            "revision": live.segment_revision(segment),
            "links": [
                {
                    "translation_start": 16,
                        "translation_end": 36,
                    "arabic_start": len(A) + 2,
                    "arabic_end": len(A) + len(B) + 2,
                }
            ],
        }
        db.commit()
        child_id = child.id
        session = live.LiveSession(
            parent.id,
            parent.mosque_id,
            live.sermon_revision(parent),
            LiveMatcher([("0", parent.arabic_text)]),
        )
        session.matcher.update(A, 0)
        session.matcher.update(B, 1)
        session.audio_received = time.monotonic()
        live.SESSIONS[parent.id] = session
        live.WORKERS["test"] = time.monotonic()
    response = client.get(f"/api/v1/reader/sermons/{child_id}/live").json()
    assert response["highlights"][0]["excerpt"] == "Opfyld dine pligter."
