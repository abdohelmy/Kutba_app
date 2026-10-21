"""Conservative Arabic script tracking. No model calls and no transcript persistence."""

import math
import re
import unicodedata
from copy import copy
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher

WORD_RE = re.compile(r"[\u0621-\u064a\u066e-\u06d3\u064b-\u065f\u0670\ufb50-\ufdff\ufe70-\ufeff]+")
COMMON = set(
    (
        "الله اللهم قال وقال يقول يا في من على إلى ان إن لا ما هذا هذه هو هي ثم كان "
        "رسول صلى عليه وسلم تعالى سبحانه"
    ).split()
)


def normalize(value: str) -> str:
    value = "".join(
        c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c) and c != "ـ"
    )
    return value.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي"}))


def words(value: str) -> list[str]:
    # Presentation ligatures such as ﷺ expand into several spoken words.
    return [part.group() for match in WORD_RE.finditer(value)
            for part in WORD_RE.finditer(normalize(match.group()))]


def speech_words(value: str) -> list[str]:
    """Collapse immediate word/short phrase repetitions in recognized speech."""
    result = []
    for token in words(value):
        result.append(token)
        for size in (3, 2, 1):
            if len(result) >= size * 2 and result[-size:] == result[-2*size:-size]:
                del result[-size:]
                break
    return result


def speech_similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    # Common spelling/clitic variations, not stemming or semantic substitution.
    left, right = left.replace("ة", "ه"), right.replace("ة", "ه")
    if left == right:
        return 0.95
    if min(len(left), len(right)) < 4:
        return 0.0
    if (left[0] in "وف" and left[1:] == right) or (right[0] in "وف" and right[1:] == left):
        return 0.9
    ratio = SequenceMatcher(None, left, right, autojunk=False).ratio()
    return ratio if ratio >= 0.72 else 0.0


def speech_alignment(query: list[str], script: list[str]) -> list[tuple[int, int, float]]:
    """Ordered approximate word alignment; bounded to nearby passages."""
    scores = [[0.0] * (len(script) + 1) for _ in range(len(query) + 1)]
    choices = {}
    similarities = {}
    for i, word in enumerate(query, 1):
        for j, target in enumerate(script, 1):
            key = (word, target)
            if key not in similarities:
                similarities[key] = speech_similarity(word, target)
            similarity = similarities[key]
            value, direction = max((scores[i-1][j], "up"), (scores[i][j-1], "left"))
            if similarity and scores[i-1][j-1] + similarity > value:
                value, direction = scores[i-1][j-1] + similarity, "match"
            scores[i][j], choices[i, j] = value, direction
    pairs = []
    i, j = len(query), len(script)
    while i and j:
        direction = choices[i, j]
        if direction == "match":
            pairs.append((i-1, j-1, similarities[query[i-1], script[j-1]]))
            i, j = i-1, j-1
        elif direction == "up":
            i -= 1
        else:
            j -= 1
    return list(reversed(pairs))


@dataclass(frozen=True)
class ScriptWord:
    text: str
    segment_id: str
    start: int  # UTF-16, like the existing sentence alignment.
    end: int


@dataclass(frozen=True)
class Match:
    index: int
    confidence: float


class LiveMatcher:
    def __init__(self, segments: list[tuple[str, str]], passage_spans: dict[str, list[tuple[int, int]]] | None = None):
        self.script: list[ScriptWord] = []
        self.sentences: list[tuple[int, int, str]] = []
        self.locations: dict[str, list[int]] = defaultdict(list)
        for identity, text in segments:
            first_word = len(self.script)
            offsets = [0]
            for character in text:
                offsets.append(offsets[-1] + (2 if ord(character) > 0xFFFF else 1))
            for match in WORD_RE.finditer(text):
                for token in words(match.group()):
                    self.locations[token].append(len(self.script))
                    self.script.append(
                        ScriptWord(token, identity, offsets[match.start()], offsets[match.end()])
                    )
            # References come from the original Arabic, including passages with
            # no translation mapping. Never advance this cursor based on a hint.
            word_index = first_word
            segment_sentences = []
            for sentence in re.split(r"(?<=[.!?؟؛])\s+|\n+", text):
                count = len(words(sentence))
                if count:
                    segment_sentences.append((word_index, word_index + count, sentence.strip()))
                    word_index += count
            spans = (passage_spans or {}).get(identity, [])
            if spans:
                # Reader mappings can split an Arabic comma-joined sentence
                # into several translated sentences. Reuse those exact source
                # boundaries so 'next passage' means the same thing to readers.
                starts = [word.start for word in self.script[first_word:]]
                cuts = {first_word, len(self.script)}
                cuts.update(start for start, _, _ in segment_sentences)
                cuts.update(end for _, end, _ in segment_sentences)
                for start, end in spans:
                    if 0 <= start < end <= offsets[-1]:
                        cuts.update((first_word + bisect_left(starts, start),
                                     first_word + bisect_left(starts, end)))
                ordered = sorted(cuts)
                encoded = text.encode("utf-16-le")
                for start, end in zip(ordered, ordered[1:]):
                    if start < end:
                        a, b = self.script[start].start, self.script[end - 1].end
                        self.sentences.append((start, end, encoded[a*2:b*2].decode("utf-16-le")))
            else:
                self.sentences.extend(segment_sentences)
        self.tokens = [word.text for word in self.script]
        counts = Counter(self.tokens)
        self.weights = {
            word: min(3.0, 1 + math.log(len(self.tokens) / (count + 1)))
            for word, count in counts.items()
        }
        self.common = {normalize(w) for w in COMMON}
        self.history: list[str] = []
        self.position: int | None = None
        self.pending: int | None = None
        self.pending_sequence = -1
        self.last_sequence = -1
        self.full_updates = 0
        self.state = "waiting"
        self.confidence = 0.0
        self.last_diagnostic: dict = {}
        self.local_pending = None
        self.audio_end: float | None = None
        self.audio_duration = 8.0

    def match_nearby(self, alternatives: list[dict], sequence: int, *, quick: bool) -> ScriptWord | None:
        """Recover noisy speech locally; independent audio confirms weak evidence."""
        if self.position is None:
            return None
        current = next((i for i, (a, b, _) in enumerate(self.sentences)
                        if a <= self.position < b), None)
        if current is None:
            return None
        end_time = self.audio_end if self.audio_end is not None else sequence * 2.0
        duration = self.audio_duration if self.audio_end is not None else (4.0 if quick else 8.0)
        if self.local_pending and end_time - self.local_pending[1] > 24:
            self.local_pending = None
        candidates = []
        for item in alternatives:
            if (not item["text"].strip() or (item["avg_logprob"] is not None and item["avg_logprob"] < -1.5)
                    or item["compression_ratio"] > 2.4
                    or (item["no_speech_prob"] is not None and item["no_speech_prob"] >= 0.98)
                    or (quick and item["reference"] != "none")):
                continue
            query = speech_words(item["text"])[-36:]
            if len(query) < 4:
                continue
            for passage in range(current, min(len(self.sentences), current + (2 if quick else 3))):
                a, b, _ = self.sentences[passage]
                start = max(0, a - 6, self.position - 8)
                end = min(b, self.position + (25 if quick else 81), start + 80)
                pairs = speech_alignment(query, self.tokens[start:end])
                if len(pairs) < 4 or len(query) - pairs[-1][0] - 1 > 2:
                    continue
                evidence = frozenset(self.tokens[start+j] for _, j, quality in pairs
                                     if start+j >= a and self.tokens[start+j] not in self.common
                                     and quality >= 0.72)
                index = start + pairs[-1][1]
                if len(evidence) < 3 or index < a or len(pairs) / (pairs[-1][1]-pairs[0][1]+1) < 0.5:
                    continue
                score = sum(quality for _, _, quality in pairs) / len(query)
                # Missing model-specific scores contribute no acoustic evidence.
                if item["no_speech_prob"] is not None:
                    score -= 0.08 * item["no_speech_prob"]
                if item["avg_logprob"] is not None:
                    score -= max(0, -item["avg_logprob"]-0.5) * 0.15
                if score >= 0.65:
                    candidates.append((score, passage, index, evidence, item))
        if not candidates:
            # A short/unclear chunk is not contradictory evidence. Retain the
            # original observation briefly, without refreshing its timestamp.
            return None
        candidates.sort(key=lambda candidate: candidate[0], reverse=True)
        score, passage, index, evidence, item = candidates[0]
        reference = item["reference"]
        rival = next((c for c in candidates if c[1] != passage), None)
        self.last_diagnostic.update(local_overlap=round(score, 3), local_passage=passage)
        if rival and score - rival[0] < 0.10:
            self.local_pending = None
            self.last_diagnostic["reason"] = "ambiguous_nearby_passages"
            return None
        if index <= self.position:
            return None
        previous = self.local_pending
        confirmed = (previous is not None and previous[0] <= passage <= previous[0] + 1
                     and duration <= end_time - previous[1] <= 24
                     and (sequence - previous[4]) * 2 >= duration
                     and index >= previous[2] + 2 and len(evidence - previous[3]) >= 2)
        strong = (score >= 0.90 and len(evidence) >= 6 and reference == "none"
                  and item["no_speech_prob"] is not None and item["avg_logprob"] is not None
                  and item["no_speech_prob"] < 0.5 and item["avg_logprob"] >= -0.35)
        # Cohere has no acoustic confidence fields. Distinctive, near-exact
        # unprompted text can establish *nearby* progress, never a distant jump.
        text_strong = (
            passage <= current + 1 and reference == "none" and score >= 0.95
            and len(evidence) >= 4
            and item["no_speech_prob"] is None and item["avg_logprob"] is None
            and all(self.tokens.count(word) == 1 for word in evidence)
        )
        if not (strong or text_strong or confirmed):
            # Keep the first observation across overlapping windows. Only fresh
            # speech with additional distinctive words can confirm it.
            if previous is None or passage not in (previous[0], previous[0] + 1) or end_time - previous[1] > 24:
                self.local_pending = (passage, end_time, index, evidence, sequence)
            self.last_diagnostic["reason"] = "awaiting_fresh_local_evidence"
            return None
        self.position = index
        self.confidence = round(score, 3)
        self.state = "matched"
        self.pending = self.local_pending = None
        self.last_diagnostic.update(reason="nearby_speech_match", candidate_word_index=index,
                                    candidate_overlap=round(score, 3), selected_reference=reference,
                                    independent_confirmation=bool(confirmed))
        self.last_diagnostic["text_only_strong_match"] = bool(text_strong)
        return self.current

    def references(self) -> list[dict]:
        """At startup use the opening sentence; thereafter follow heard speech."""
        position = self.pending if self.pending is not None else (self.position or 0)
        current = next((i for i, (start, end, _) in enumerate(self.sentences)
                        if start <= position < end), None)
        if current is None:
            return []
        result = []
        for label, index in (("current", current), ("next", current + 1)):
            if index >= len(self.sentences):
                continue
            start, _, text = self.sentences[index]
            # Bound hints for long unpunctuated paragraphs. Keep a little context
            # before the last heard word and the words likely to follow it.
            text = normalize(text)
            tokens = list(WORD_RE.finditer(text))
            offset = max(0, position - start - 8) if label == "current" and len(tokens) > 60 else 0
            selected = tokens[offset:offset + 60]
            if selected:
                excerpt = text[selected[0].start():selected[-1].end()]
                result.append({"reference": label, "text": normalize(excerpt)[:1200]})
        return result

    def update_alternatives(self, alternatives: list[dict], sequence: int) -> ScriptWord | None:
        """Evaluate decodes of ONE audio chunk against identical prior state."""
        if sequence <= self.last_sequence:
            return self.update("", sequence)
        viable = [item for item in alternatives if item["text"].strip()
                  and (item["avg_logprob"] is None or item["avg_logprob"] >= -1.0)
                  and (item["no_speech_prob"] is None or item["no_speech_prob"] < 0.6)
                  and item["compression_ratio"] <= 2.4]
        if not viable:
            self.update("", sequence)
            self.pending = None
            self.last_diagnostic.update(reason="unreliable_speech", candidate_count=len(alternatives))
            return self.match_nearby(alternatives, sequence, quick=False)
        # A sentence hint can bias recognition. Do not prefer a script-perfect
        # decode whose acoustic likelihood is substantially worse than its rival.
        known_audio = [item["avg_logprob"] for item in viable if item["avg_logprob"] is not None]
        best_audio = max(known_audio) if known_audio else None
        trials = []
        for item in viable:
            if best_audio is not None and item["avg_logprob"] is not None and item["avg_logprob"] < best_audio - 0.5:
                continue
            trial = copy(self)
            trial.history = self.history.copy()
            result = trial.update(item["text"], sequence)
            score = trial.last_diagnostic.get("candidate_overlap", 0)
            trials.append((score, item["avg_logprob"] if item["avg_logprob"] is not None else -1.0,
                           trial, result, item["reference"]))
        trials.sort(key=lambda trial: (trial[0], trial[1]), reverse=True)
        score, _, winner, result, reference = trials[0]
        for rival_score, _, rival, _, _ in trials[1:]:
            if not score or not rival_score:
                continue
            distance = abs(winner.last_diagnostic["candidate_word_index"]
                           - rival.last_diagnostic["candidate_word_index"])
            if distance > 16 and score - rival_score < 0.10:
                self.last_sequence = sequence
                self.pending = None
                self.local_pending = None
                self.state = "waiting"
                self.last_diagnostic = {"sequence": sequence, "reason": "conflicting_transcriptions",
                                        "candidate_count": len(alternatives)}
                return None
        self.__dict__.update(winner.__dict__)
        self.last_diagnostic.update(selected_reference=reference, candidate_count=len(alternatives))
        if result is None:
            return self.match_nearby(alternatives, sequence, quick=False)
        self.local_pending = None
        return result

    def update_quick(self, alternatives: list[dict], sequence: int) -> ScriptWord | None:
        """Four-second audio may cross ONE sentence boundary, never re-anchor.

        Only fresh audio is evidence here. It must not modify full-check history
        or supply the confirmation for a pending long jump.
        """
        self.last_diagnostic = {"sequence": sequence, "kind": "quick", "reason": "quick_hold"}
        if sequence <= self.last_sequence:
            self.last_diagnostic["reason"] = "stale_sequence"
            return None
        self.last_sequence = sequence
        if self.position is None:
            self.last_diagnostic["reason"] = "quick_needs_full_match"
            return None
        current = next((i for i, (start, end, _) in enumerate(self.sentences)
                        if start <= self.position < end), None)
        if current is None or current + 1 >= len(self.sentences):
            self.last_diagnostic["reason"] = "quick_no_next_passage"
            return None
        next_start, next_end, _ = self.sentences[current + 1]
        if next_start > self.position + 24:
            self.last_diagnostic["reason"] = "quick_next_passage_too_far"
            return None
        # Include the current sentence's tail for natural boundary crossings.
        start = max(self.sentences[current][0], self.position - 8)
        end = min(next_end, self.position + 25)
        matches = []
        reliable = False
        best_overlap = 0.0
        for item in alternatives:
            uncertain_speech = item["no_speech_prob"] is None or item["no_speech_prob"] >= 0.5
            if (item["reference"] != "none"
                    or (item["avg_logprob"] is not None and item["avg_logprob"] < -0.7)
                    or (item["no_speech_prob"] is not None and item["no_speech_prob"] >= 0.75)
                    or item["compression_ratio"] > 2.4
                    or (uncertain_speech and item["avg_logprob"] is not None and item["avg_logprob"] < -0.35)):
                continue
            reliable = True
            query = words(item["text"])
            if not 5 <= len(query) <= 24:
                continue
            blocks = [b for b in SequenceMatcher(None, query, self.tokens[start:end],
                                                autojunk=False).get_matching_blocks() if b.size]
            if not blocks or len(query) - (blocks[-1].a + blocks[-1].size) > 1:
                continue
            count = sum(b.size for b in blocks)
            overlap = count / len(query)
            best_overlap = max(best_overlap, overlap)
            next_words = {self.tokens[start + b.b + offset] for b in blocks for offset in range(b.size)
                          if start + b.b + offset >= next_start
                          and self.tokens[start + b.b + offset] not in self.common}
            index = start + blocks[-1].b + blocks[-1].size - 1
            # A moderate no-speech score alone need not veto a strong local
            # decode. Require near-exact text and extra distinctive evidence;
            # this exception never applies to acquisition or distant jumps.
            if uncertain_speech and (overlap < 0.95 or count < 6 or len(next_words) < 4):
                continue
            if count >= 5 and overlap >= 0.85 and len(next_words) >= 3 and next_start <= index < next_end:
                matches.append((overlap, item["avg_logprob"] if item["avg_logprob"] is not None else -1.0, index))
        if not matches:
            self.last_diagnostic.update(reason="quick_no_local_match" if reliable else "quick_unreliable_speech",
                                        best_window_overlap=round(best_overlap, 3))
            return self.match_nearby(alternatives, sequence, quick=True)
        score, _, index = max(matches)
        self.position = index
        self.confidence = round(score, 3)
        self.state = "matched"
        self.pending = None
        self.local_pending = None
        self.last_diagnostic.update(reason="quick_next_sentence", candidate_overlap=round(score, 3),
                                    candidate_word_index=index, selected_reference="none")
        return self.current

    def candidate(self, query: list[str]) -> Match | None:
        anchors = [
            (i, token)
            for i, token in enumerate(query)
            if token not in self.common and token in self.locations
        ]
        distinct = len({token for _, token in anchors})
        self.last_diagnostic["distinct_script_anchors"] = distinct
        if distinct < 4:
            self.last_diagnostic["reason"] = "insufficient_distinct_script_words"
            return None
        anchors.sort(key=lambda item: len(self.locations[item[1]]))
        starts = set()
        for query_index, token in anchors[:8]:
            # Very common tokens must not create thousands of candidate windows.
            for index in self.locations[token][:100]:
                for delta in (-2, 0, 2):
                    starts.add(max(0, index - query_index + delta))
        candidates = []

        def weight_of(token):
            return 0.5 if token in self.common else self.weights.get(token, 3.0)

        weight = sum(weight_of(w) for w in query)
        enough_words = enough_overlap = False
        for start in starts:
            end = min(len(self.tokens), start + len(query) + 4)
            if self.position is not None and end < self.position - 30:
                continue
            blocks = SequenceMatcher(
                None, query, self.tokens[start:end], autojunk=False
            ).get_matching_blocks()
            count = sum(block.size for block in blocks)
            score = (
                sum(
                    weight_of(query[i])
                    for block in blocks
                    for i in range(block.a, block.a + block.size)
                )
                / weight
            )
            self.last_diagnostic["max_matching_words"] = max(
                count, self.last_diagnostic.get("max_matching_words", 0)
            )
            if score > self.last_diagnostic.get("best_window_overlap", -1):
                self.last_diagnostic["best_window_overlap"] = round(score, 3)
                self.last_diagnostic["best_window_matching_words"] = count
            if count < 8:
                continue
            enough_words = True
            if score < 0.72:
                continue
            enough_overlap = True
            last = next((block for block in reversed(blocks) if block.size), None)
            if last is None or len(query) - (last.a + last.size) > 3:
                continue  # An off-script tail cannot advance the highlight.
            index = start + last.b + last.size - 1
            candidates.append(Match(index, score))
        if not candidates:
            self.last_diagnostic["reason"] = (
                "insufficient_matching_words" if not enough_words
                else "low_overlap" if not enough_overlap else "off_script_tail"
            )
            return None
        candidates.sort(
            key=lambda item: (
                -item.confidence,
                abs(item.index - self.position) if self.position is not None else item.index,
            )
        )
        best = candidates[0]
        rivals = [c for c in candidates if abs(c.index - best.index) > 16]
        if rivals and best.confidence - rivals[0].confidence < 0.10:
            # Repeated quotation/formula: only the neighbourhood is evidence.
            nearby = [
                c
                for c in candidates
                if self.position is not None and self.position - 12 <= c.index <= self.position + 60
            ]
            if not nearby:
                self.last_diagnostic["reason"] = "ambiguous_repeated_passage"
                return None
            best = nearby[0]
        self.last_diagnostic.update(candidate_overlap=round(best.confidence, 3),
                                    candidate_word_index=best.index)
        return best

    def update(self, transcript: str, sequence: int) -> ScriptWord | None:
        self.last_diagnostic = {"sequence": sequence}
        if sequence <= self.last_sequence:
            self.last_diagnostic["reason"] = "stale_sequence"
            return None
        self.last_sequence = sequence
        incoming = words(transcript)[-80:]
        self.full_updates += 1
        # Chunks contain a short audio overlap; don't count it as fresh evidence.
        overlap = 0
        for size in range(1, min(24, len(self.history), len(incoming)) + 1):
            if self.history[-size:] == incoming[:size]:
                overlap = size
        novel = incoming[overlap:]
        self.last_diagnostic.update(arabic_words=len(incoming), new_words=len(novel),
                                    overlap_words=overlap)
        if len(novel) < 3:
            self.last_diagnostic["reason"] = "empty_or_non_arabic_text" if not incoming else "insufficient_new_words"
            self.state = "waiting"
            return None
        self.history = (self.history + novel)[-36:]
        match = self.candidate(self.history)
        fresh_query = incoming[-36:]
        if match is None and len(fresh_query) >= 8 and fresh_query != self.history:
            # Unreliable old STT must not veto a sufficiently strong fresh chunk.
            # Use the same candidate checks, then the same confirmation/jump rules.
            rolling_diagnostic = self.last_diagnostic.copy()
            self.last_diagnostic = {
                key: rolling_diagnostic[key]
                for key in ("sequence", "arabic_words", "new_words", "overlap_words")
            }
            fresh_match = self.candidate(fresh_query)
            fresh_diagnostic = self.last_diagnostic.copy()
            if fresh_match is not None:
                match = fresh_match
                self.history = fresh_query
                self.last_diagnostic.update(
                    history_recovered=True,
                    query_source="current_chunk",
                    rolling_reason=rolling_diagnostic.get("reason"),
                    rolling_best_window_overlap=rolling_diagnostic.get("best_window_overlap"),
                )
            else:
                self.last_diagnostic = rolling_diagnostic
                self.last_diagnostic.update(
                    current_chunk_reason=fresh_diagnostic.get("reason"),
                    current_chunk_best_window_overlap=fresh_diagnostic.get("best_window_overlap"),
                )
        if match is None:
            # Drop the old on-script context so returning speech can re-anchor.
            self.history = incoming[-24:]
            self.pending = None
            self.state = "waiting"
            return None
        # candidate() already rejects ambiguous repeated passages. A strong,
        # distinctive initial match can start immediately; later large jumps
        # still require fresh confirming speech, even at perfect confidence.
        strong_initial = (
            self.position is None
            and match.confidence >= 0.90
            and len(self.history) >= 10
            and len({w for w in self.history if w not in self.common and w in self.locations}) >= 6
        )
        distant = (self.position is None and not strong_initial) or (
            self.position is not None and match.index > self.position + 60
        )
        if distant:
            confirmed = (
                self.pending is not None
                and 0 <= match.index - self.pending <= 60
                and 0 < self.full_updates - self.pending_sequence <= 2
                and match.index > self.pending
            )
            if not confirmed:
                self.pending = match.index
                self.pending_sequence = self.full_updates
                self.state = "waiting"
                self.last_diagnostic["reason"] = (
                    "awaiting_initial_confirmation" if self.position is None else "awaiting_jump_confirmation"
                )
                return None
        if self.position is not None and match.index < self.position - 12:
            self.last_diagnostic["reason"] = "backward_match_rejected"
            self.state = "waiting"
            return None
        # Overlapping audio can end a few words behind a recent short check.
        # Keep the confirmed highlight steady instead of bouncing backwards.
        self.position = max(match.index, self.position or 0)
        self.pending = None
        self.confidence = round(match.confidence, 3)
        self.state = "matched"
        self.last_diagnostic["reason"] = "matched"
        return self.current

    @property
    def current(self) -> ScriptWord | None:
        return self.script[self.position] if self.position is not None else None
