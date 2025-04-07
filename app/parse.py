# originally inspired by https://github.com/lawrencehook/SqueexVodSearch/blob/main/preprocessing/scripts/parse.py

import logging
from .models.db import WordMaps, Segments
from flask_sqlalchemy import SQLAlchemy
from io import BytesIO
import webvtt
import re
import nltk
from nltk.corpus import stopwords
from nltk.tag import pos_tag
from nltk.tokenize import word_tokenize
from nltk.stem import PorterStemmer

_ = nltk.download("stopwords")
_ = nltk.download("averaged_perceptron_tagger_eng")
_ = nltk.download("punkt_tab")

sw = stopwords.words("english")
ps = PorterStemmer()
logger = logging.getLogger(__name__)


# This function is used by both parsing and searching to ensure we are getting good search results.
def sanitize_sentence(sentence: str) -> list[str]:
    words = pos_tag(word_tokenize(sentence))
    result: list[str] = []
    for word in words:
        if word[0] not in sw:
            word = ps.stem(word[0])
            result.append(word)
    return result


def get_sec(time_str: str) -> int:
    """Get seconds from time."""
    h, m, s = re.sub(r"\..*$", "", time_str).split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def parse_vtt(db: SQLAlchemy, vtt_buffer: BytesIO, transcription_id: int):
    logger.info(f"Processing vtt transcription: {transcription_id}")
    # savepoint = db.session.begin_nested()
    segments: list[Segments] = []
    word_map: list[WordMaps] = []
    previous = None
    for caption in webvtt.from_buffer(vtt_buffer):
        start = get_sec(caption.start)
        # remove annotations, such as [music]
        text = re.sub(r"\[.*?\]", "", caption.text).strip().lower()

        if "\n" in text:
            continue
        if text == "":
            continue
        if text == previous:
            continue

        segment = Segments(
            text=text,
            start=start,
            transcription_id=transcription_id,
            end=get_sec(caption.end),
        )
        db.session.add(segment)
        db.session.flush()
        previous = text
        segments.append(segment)
        # words = pos_tag(word_tokenize(text))
        words = sanitize_sentence(text)
        # words = text.split()
        for word in words:
            found_existing_word = False
            for wm in word_map:
                if wm.word == word:
                    wm.segments.append(segment.id)
                    found_existing_word = True
                    break
            if found_existing_word == False:
                word_map.append(
                    WordMaps(
                        word=word,
                        segments=[segment.id],
                        transcription_id=transcription_id,
                    )
                )
    db.session.add_all(word_map)
    db.session.commit()
    logger.info(f"Done processing transcription: {transcription_id}")
