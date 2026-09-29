

def test_theme_palette_is_pink_red_and_white() -> None:
    from saturnino.gui import THEME

    assert THEME["accent"] == "#e94f8a"
    assert THEME["danger"] == "#d9415d"
    assert THEME["surface"] == "#ffffff"
