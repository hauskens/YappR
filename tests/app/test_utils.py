from app.shared import convert_to_srt

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