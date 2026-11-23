import pytest

from web_asr import browser_asr_origin


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("", ""),
        ("speech.example.test:9081", ""),
        (" http://localhost:9081 ", "http://localhost:9081"),
        ("http://192.0.2.20:9082", "http://192.0.2.20:9082"),
        ("http://[2001:db8::20]:9081", "http://[2001:db8::20]:9081"),
        ("http://speech.example.test:65536", ""),
        ("http://speech.example.test:0", ""),
        ("http://127.0.0.01:9081", ""),
        ("http://[192.0.2.20]:9081", ""),
        ("HTTPS://Speech.example.test:443/", "https://speech.example.test"),
        ("https://speech.example.test:9443", "https://speech.example.test:9443"),
        ("https://user:password@speech.example.test", ""),
        ("https://speech.example.test/path", ""),
        ("https://speech.example.test?x=y", ""),
        ("https://speech.example.test#fragment", ""),
        ("https://speech.example.test\\evil.example.test", ""),
        ("javascript:alert(1)", ""),
    ],
)
def test_asr_browser_origin_from_deployment(monkeypatch, url, expected):
    monkeypatch.setenv("ASR_URL", url)

    assert browser_asr_origin() == expected
