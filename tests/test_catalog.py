from saturnino.catalog import AnimeResult, EpisodeRef, parse_anime_results, parse_episode_links, select_numbers


def test_parse_search_results_deduplicates_and_preserves_metadata() -> None:
    html = """
    <a href='/anime/chainsmoker-cat-73cfQ'><h3>Chainsmoker Cat</h3><p>03 Luglio 2026 · 12 ep</p></a>
    <a href='/anime/chainsmoker-cat-73cfQ'><h3>Chainsmoker Cat</h3><p>03 Luglio 2026 · 12 ep</p></a>
    <a href='/anime/chainsmoker-cat-ita-ZDG6n'><h3>Chainsmoker Cat (ITA)</h3><p>DUB</p></a>
    """
    results = parse_anime_results(html, "https://www.animesaturn.net")
    assert results == [
        AnimeResult("Chainsmoker Cat", "https://www.animesaturn.net/anime/chainsmoker-cat-73cfQ", "03 Luglio 2026 · 12 ep"),
        AnimeResult("Chainsmoker Cat (ITA)", "https://www.animesaturn.net/anime/chainsmoker-cat-ita-ZDG6n", "DUB"),
    ]


def test_parse_episode_links_is_numeric_and_sorted() -> None:
    html = """
    <a href='/episode/show/ep-11' title='Episodio 11'>11</a>
    <a href='/episode/show/ep-1' title='Episodio 1'>1</a>
    <a href='/episode/show/ep-1' title='Episodio 1'>1</a>
    <a href='/anime/related'>Related</a>
    """
    assert parse_episode_links(html, "https://www.animesaturn.net") == [
        EpisodeRef("1", "https://www.animesaturn.net/episode/show/ep-1"),
        EpisodeRef("11", "https://www.animesaturn.net/episode/show/ep-11"),
    ]


def test_select_numbers_supports_all_ranges_and_rejects_unknown() -> None:
    episodes = [EpisodeRef(str(number), f"url-{number}") for number in range(1, 6)]
    assert select_numbers("1, 3-4", episodes) == episodes[:1] + episodes[2:4]
    assert select_numbers("all", episodes) == episodes
    assert select_numbers("9", episodes) == []
