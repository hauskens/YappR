import pytest
from app.shared import convert_to_srt
from app.utils import get_sec

def test_convert_segments_to_srt():
    data = {
        "segments": [
            {
                "start": 0,
                "end": 1,
                "text": "Hello"
            },
            {
                "start": 1.123,
                "end": 2,
                "text": "World"
            }
        ]
    }
    assert convert_to_srt(data) == "1\n00:00:00,000 --> 00:00:01,000\nHello\n\n2\n00:00:01,123 --> 00:00:02,000\nWorld\n"

def test_convert_json_to_srt():
    data = {"segments": [{"text": "Hello", "start": 1.516, "end": 9.565}, {"text": " World", "start": 13.042, "end": 21.26}]}
    assert convert_to_srt(data) == "1\n00:00:01,516 --> 00:00:09,565\nHello\n\n2\n00:00:13,042 --> 00:00:21,260\n World\n"

@pytest.mark.parametrize("time_str,expected_seconds", [
    # HH:MM:SS format
    ("00:00:30", 30),
    ("00:01:00", 60),
    ("01:00:00", 3600),
    ("01:30:45", 5445),
    # XhYmZs format
    ("30s", 30),
    ("45m", 2700),
    ("1h", 3600),
    ("1h30m", 5400),
    ("1h30m45s", 5445),
    ("45m30s", 2730),
    # Edge cases
    ("0h0m0s", 0),
    ("00:00:00", 0),
])
def test_get_sec(time_str, expected_seconds):
    """Test that get_sec correctly converts various time formats to seconds"""
    assert get_sec(time_str) == expected_seconds