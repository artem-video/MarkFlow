from markflow.shared.text_norm import normalize


def test_year_with_ordinal_suffix():
    assert normalize("мая 2020-го года") == "мая две тысячи двадцатого года"


def test_year_before_the_word_year_is_ordinal():
    assert normalize("в 18 году") == "в восемнадцатого году"


def test_plain_numbers_are_cardinal():
    assert normalize("5 раз") == "пять раз"
    assert normalize("100 000 человек") == "сто тысяч человек"
    assert normalize("239 тысяч") == "двести тридцать девять тысяч"


def test_text_without_digits_is_unchanged():
    assert normalize("Но насколько сильно") == "но насколько сильно"
