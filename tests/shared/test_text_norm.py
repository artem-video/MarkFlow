from markflow.shared.text_norm import find_urls, normalize, strip_markdown, without_links, words


def test_normalize_matches_despite_case_yo_punctuation():
    assert normalize("**Ёлки**, «модная» пропаганда!") == normalize("елки модная ПРОПАГАНДА")


def test_strip_markdown_keeps_visible_text():
    assert strip_markdown("[**https://t.me/luka\\_ebkov/9135**](https://t.me/luka_ebkov/9135)") == \
        "https://t.me/luka_ebkov/9135"
    assert strip_markdown("*0:12 Видишь, с постиронией*") == "0:12 Видишь, с постиронией"


def test_find_urls_prefers_link_target_over_broken_text():
    raw = "**010 ЛАЙВ: **[**https://www.you tube.com/watch?v=gUEkElSFtwM\\&t=1586s**](https://www.youtube.com/watch?v=gUEkElSFtwM&t=1586s)"
    assert find_urls(raw) == ["https://www.youtube.com/watch?v=gUEkElSFtwM&t=1586s"]


def test_find_urls_unescapes_markdown():
    assert find_urls("<https://youtu.be/xy7L9nyowdo?si=A2AX>") == ["https://youtu.be/xy7L9nyowdo?si=A2AX"]
    assert find_urls("https://t.me/luka\\_ebkov/1") == ["https://t.me/luka_ebkov/1"]


def test_without_links():
    assert without_links("**https://www. **[**youtube.com/watch?v=A**](https://www.youtube.com/watch?v=A)") == ""
    assert without_links("**008 ЛАЙВ:** <https://x.ru/a>") == "008 ЛАЙВ:"


def test_words():
    assert words("Что-то вышло из моды…") == ["что", "то", "вышло", "из", "моды"]
