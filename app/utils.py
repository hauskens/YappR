# originally inspired by https://github.com/lawrencehook/SqueexVodSearch/blob/main/preprocessing/scripts/parse.py

import logging
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
