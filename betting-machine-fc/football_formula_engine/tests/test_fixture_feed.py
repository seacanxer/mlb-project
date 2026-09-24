import pytest

import scraper_1xbit


def test_first_page_failure_is_not_published_as_empty_schedule(monkeypatch):
    def fail(_url):
        raise OSError('feed unavailable')

    monkeypatch.setattr(scraper_1xbit, 'fetch', fail)
    with pytest.raises(OSError, match='feed unavailable'):
        scraper_1xbit.list_matches_paginated()


def test_invalid_feed_shape_is_visible(monkeypatch):
    monkeypatch.setattr(scraper_1xbit, 'fetch', lambda _url: {'error': 'upstream'})
    with pytest.raises(ValueError, match='Invalid fixture feed response'):
        scraper_1xbit.list_matches_paginated()


def test_later_page_failure_does_not_publish_partial_schedule(monkeypatch):
    calls = 0

    def fetch(_url):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {'Value': [{'I': '123', 'S': 1000}]}
        raise TimeoutError('page two timed out')

    monkeypatch.setattr(scraper_1xbit, 'fetch', fetch)
    monkeypatch.setattr(scraper_1xbit.time, 'time', lambda: 0)
    with pytest.raises(TimeoutError, match='page two timed out'):
        scraper_1xbit.list_matches_paginated()
