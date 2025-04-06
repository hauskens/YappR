# modified version of https://github.com/lawrencehook/SqueexVodSearch/blob/main/preprocessing/scripts/parse.py
# Mozilla Public License Version 2.0 -> https://github.com/lawrencehook/SqueexVodSearch/blob/main/LICENSE

from io import BytesIO
import sys
import webvtt
import re
import json

import nltk

_ = nltk.download("stopwords")
from nltk.corpus import stopwords

sw = stopwords.words("english")

"""
Notes

output:
    - id: the video ID
    - segments: a list of segments as they appear in the vtt file.
        - segment: [startTime, text]
    - word_map: a dictionary that maps a word to a list of indexes in which it appears in the segments list
    - upload_date

    extended:
        - full_text
        - TODO: Map an index in the full_text string to a time.
            - string index
            - word index
            - I have the time of each word, I think

            To test: what info can i reliably retrieve? a la <c></c>



segment object:
    [start time, text]
"""


def get_sec(time_str: str) -> int:
    """Get seconds from time."""
    h, m, s = re.sub(r"\..*$", "", time_str).split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


# if __name__ == "__main__":

# if len(sys.argv) < 2:
#     print("Expected 1 command line paramter (vtt file path). Exiting...")
#     sys.exit(1)
#
# # Get all upload dates by video id.
# dates = {}
# with open("data/dates.txt") as dates_file:
#     for line in dates_file.readlines():
#         vid, date = line.strip().split(":")
#         dates[vid] = int(date)


# # Get video ID from filename.
# p = re.compile(r"\[([^\[]*?)\]\.en\.vtt")
# vtt_filename = sys.argv[1]
# vid = p.search(vtt_filename).group(1)
# upload_date = dates[vid]
def parse_vtt(vtt_buffer: BytesIO):
    for capture in webvtt.from_buffer(vtt_buffer):
        print(capture.start)
    # # Parse vtt file
    # segments = []
    # word_map = {}
    # full_text = ""
    # idx_to_time = {}
    # seen_starts = set()
    # for caption in webvtt.read(vtt_filename):
    #
    #     start = get_sec(caption.start)
    #     text = re.sub(r"\[.*?\]", "", caption.text).strip().lower()
    #
    #     if "\n" in text:
    #         continue
    #     if text == "":
    #         continue
    #     if start in seen_starts:
    #         continue
    #     if len(segments) > 0 and text == segments[-1][1]:
    #         continue
    #
    #     seen_starts.add(start)
    #     segments.append([start, text])
    #
    #     idx = len(segments) - 1
    #     words = text.split()
    #     for word in words:
    #         if word in sw:
    #             continue
    #         if word in word_map:
    #             word_map[word].add(idx)
    #         else:
    #             word_map[word] = {idx}
    #
    #     full_text += " " + text
    #     idx_to_time[len(full_text)] = get_sec(caption.end)
    #
    # # print(full_text)
    # # print(idx_to_time)
    #
    # # import re
    # # query = 'everyone in the chat'
    # # indices = [i.start() for i in re.finditer(pattern=query, string=full_text)]
    # # for i in indices:
    # #     print(i)
    # #     dec = 0
    # #     while (i-dec) not in idx_to_time:
    # #         dec += 1
    # #     print('start: ' + idx_to_time[i-dec])
    # #     print(full_text[i-dec:i+len(query)])
    # # sys.exit(1)
    #
    # # Convert sets to lists, for the json export
    # for word, idxs in word_map.items():
    #     word_map[word] = list(idxs)
    #
    # # Export parsed data to json
    # print(
    #     json.dumps(
    #         {
    #             "id": vid,
    #             "segments": segments,
    #             "word_map": word_map,
    #             "full_text": full_text,
    #             "idx_to_time": idx_to_time,
    #             "upload_date": upload_date,
    #         }
    #     )
    # )
    # # }, indent=2))
