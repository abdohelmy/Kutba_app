from app.services.glossary_phrases import phrase_at_note


def test_phrase_must_belong_to_the_note_not_another_word_or_sentence():
    assert phrase_at_note('Be mindful of Allah ', 'mindful of Allah') == 'mindful of Allah'
    assert phrase_at_note('An important reminder. Different wording ', 'reminder') == ''
    assert phrase_at_note('Misguidance ', 'guidance') == ''
    assert phrase_at_note('Vær gudsbevidst ', 'God-consciousness') == ''
    assert phrase_at_note('Vær gudsbevidst ', 'gudsbevidsthed') == ''
    assert phrase_at_note('Vær GUDSBEVIDST ', 'gudsbevidst') == 'GUDSBEVIDST'
    assert phrase_at_note(
        'Act with careful\nverification ', 'careful verification'
    ) == 'careful\nverification'
