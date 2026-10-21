from datetime import date
from unittest.mock import AsyncMock

from conftest import login_headers

from app.db.session import SessionLocal
from app.models import Sermon, SermonSegment, SermonStatus
from app.services.providers.alignment import SentenceLinks
from app.services.sentence_alignment import sentence_spans, validated_links
from app.services.sentence_alignment import AlignedSentence, alignment_input, cached_alignment, _cache


def test_alignment_validates_exact_arabic_repeated_occurrences_and_utf16():
    arabic = '🌙 الحمد لله. ثم الحمد لله.'
    translation = '🌙 Praise Allah. Praise Allah again.'
    result = SentenceLinks(links=[
        dict(sentence_id=0, arabic_excerpt='الحمد لله.', occurrence=0),
        dict(sentence_id=1, arabic_excerpt='الحمد لله.', occurrence=1),
        dict(sentence_id=2, arabic_excerpt='invented', occurrence=0),
        dict(sentence_id=1, arabic_excerpt='الحمد لله.', occurrence=0),
    ])
    links = validated_links(arabic, translation, result)
    assert len(links) == 2
    assert links[0].arabic_start == 3  # Emoji occupies two UTF-16 code units.
    assert links[1].arabic_start > links[0].arabic_start
    assert links[1].translation_start == 17
    assert validated_links(arabic, translation, SentenceLinks(links=[
        dict(sentence_id=0, arabic_excerpt='الحمدُ لله.', occurrence=0),
        dict(sentence_id=1, arabic_excerpt='الحمد لله.', occurrence=5),
    ])) == []


def test_sentence_notes_and_multi_sentence_arabic_source():
    translated = 'Have God-consciousness (التقوى).\nThen remember Allah.'
    assert [translated[a:b] for a, b in sentence_spans(translated)] == [
        'Have God-consciousness (التقوى).', 'Then remember Allah.'
    ]
    result = SentenceLinks(links=[
        dict(sentence_id=0, arabic_excerpt='اتقوا الله واذكروه.', occurrence=0),
        dict(sentence_id=1, arabic_excerpt='اتقوا الله واذكروه.', occurrence=0),
    ])
    links = validated_links('اتقوا الله واذكروه.', translated, result)
    assert len(links) == 2
    assert links[0].arabic_start == links[1].arabic_start
    assert links[0].arabic_end == links[1].arabic_end


def test_cached_offsets_require_exact_whitespace_not_just_matching_sentences():
    arabic = 'الحمد لله.'
    _, _, key = alignment_input(arabic, 'Praise Allah.\nRemember Him.')
    _cache[key] = [AlignedSentence(
        translation_start=14, translation_end=27, arabic_start=0, arabic_end=10,
    )]
    try:
        assert cached_alignment(arabic, 'Praise Allah.\nRemember Him.')
        assert cached_alignment(arabic, 'Praise Allah.\n\nRemember Him.') is None
        assert cached_alignment(arabic, 'Praise Allah.\nRemember Him.', 'Changed base') is None
    finally:
        _cache.pop(key, None)


def test_alignment_endpoint_keeps_edits_unsaved_and_enforces_mosque_access(
    client, seeded_accounts, monkeypatch,
):
    with SessionLocal() as db:
        sermon = Sermon(
            mosque_id=seeded_accounts['mosque_id'], title='Test', khutba_date=date.today(),
            target_language='da', source_file_path='test.pdf', source_file_sha256='a' * 64,
            arabic_text='الحمد لله.', created_by=seeded_accounts['admin_id'],
            status=SermonStatus.REVIEW_REQUIRED,
            segments=[SermonSegment(ordinal=0, arabic_text='الحمد لله.',
                                   translated_text='Lovprisning til Allah.')],
        )
        db.add(sermon)
        db.commit()
        sermon_id, segment_id = sermon.id, sermon.segments[0].id
    align = AsyncMock(return_value=[])
    monkeypatch.setattr('app.api.routes.admin.align_sentences', align)
    path = f'/api/v1/admin/sermons/{sermon_id}/segments/{segment_id}/alignment'
    headers = login_headers(client, 'admin', 'correct-horse-123')
    response = client.post(path, headers=headers, json={'translated_text': 'Edited Danish.'})
    assert response.status_code == 200
    align.assert_awaited_once_with('الحمد لله.', 'Edited Danish.', None)
    assert client.post(path, json={'translated_text': 'Edited.'}).status_code == 401
    with SessionLocal() as db:
        assert db.get(SermonSegment, segment_id).translated_text == 'Lovprisning til Allah.'
        db.get(Sermon, sermon_id).mosque_id = seeded_accounts['other_mosque_id']
        db.commit()
    assert client.post(
        path, headers=headers, json={'translated_text': 'Edited.'}
    ).status_code == 403


def test_saved_editor_alignment_is_persisted_but_unsaved_draft_is_not(
    client, seeded_accounts, monkeypatch,
):
    with SessionLocal() as db:
        row = Sermon(
            mosque_id=seeded_accounts['mosque_id'], title='Test', khutba_date=date.today(),
            target_language='en', source_file_path='test.pdf', source_file_sha256='a' * 64,
            arabic_text='الحمد لله.', created_by=seeded_accounts['admin_id'],
            status=SermonStatus.REVIEW_REQUIRED,
            segments=[SermonSegment(ordinal=0, arabic_text='الحمد لله.',
                                   translated_text='Praise Allah.')],
        )
        db.add(row)
        db.commit()
        sermon_id, segment_id = row.id, row.segments[0].id
    link = AlignedSentence(translation_start=0, translation_end=13, arabic_start=0, arabic_end=10)
    align = AsyncMock(return_value=[link])
    monkeypatch.setattr('app.api.routes.admin.align_sentences', align)
    headers = login_headers(client, 'admin', 'correct-horse-123')
    path = f'/api/v1/admin/sermons/{sermon_id}/segments/{segment_id}'
    assert client.post(path+'/alignment', headers=headers,
                       json={'translated_text':'Praise Allah.'}).status_code == 200
    assert client.post(path+'/alignment', headers=headers,
                       json={'translated_text':'Praise Allah.'}).status_code == 200
    align.assert_awaited_once()  # Persisted mappings also work after a cache/API restart.
    with SessionLocal() as db:
        original = db.get(SermonSegment, segment_id).live_alignment
        assert original['links']
    assert client.post(path+'/alignment', headers=headers,
                       json={'translated_text':'Praise God.'}).status_code == 200
    with SessionLocal() as db:
        segment = db.get(SermonSegment, segment_id)
        assert segment.translated_text == 'Praise Allah.'
        assert segment.live_alignment == original
    # Real align_sentences caches the exact draft. Save must reuse it, not call AI.
    _, _, key = alignment_input('الحمد لله.', 'Praise God.')
    _cache[key] = [link]
    try:
        assert client.patch(path, headers=headers,
                            json={'translated_text':'Praise God.', 'approved':False}).status_code == 200
        with SessionLocal() as db:
            assert db.get(SermonSegment, segment_id).live_alignment['links']
        assert client.patch(path, headers=headers,
                            json={'translated_text':'Different wording.', 'approved':False}).status_code == 200
        with SessionLocal() as db:
            assert db.get(SermonSegment, segment_id).live_alignment == {}
    finally:
        _cache.pop(key, None)
