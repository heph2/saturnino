

def test_progress_percent_is_bounded_and_handles_unknown_size() -> None:
    from saturnino.gui import progress_percent

    assert progress_percent(25, 100) == 25
    assert progress_percent(150, 100) == 100
    assert progress_percent(-1, 100) == 0
    assert progress_percent(25, None) is None
    assert progress_percent(25, 0) is None
