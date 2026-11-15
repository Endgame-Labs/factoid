import re

from factoid import Passage, ProseDocument
from factoid.document import split_sentences


class Transcript(ProseDocument):
    """A broadcast interview or news segment transcript, as speaker turns."""

    chunk_size = 4000  # the paper's fixed chunks: 4,000 bytes with 400 bytes of overlap
    chunk_overlap = 400
    guidance = (
        "This is a broadcast transcript. Each passage is one sentence of one speaker's turn. Name who said each thing "
        "(\"Larry Seibert said ...\"), resolve pronouns to the people and organizations they refer to, and keep "
        "opinions, beliefs, and judgments attributed to the person who holds them."
    )

    @property
    def source_datetime(self):
        date = self.metadata.get("date")  # MediaSum writes dates without zero padding, such as "2001-7-25"
        if not date:
            return None
        year, month, day = (int(x) for x in str(date).split("-"))
        return f"{year:04d}-{month:02d}-{day:02d}T00:00:00Z"

    def context(self):
        return {k: self.metadata[k] for k in ("program", "title", "date") if self.metadata.get(k)}

    def segment(self):
        """One passage per sentence, each tagged with its speaker. Turns are paragraphs of "SPEAKER: text"."""
        passages, n = [], 0
        for match in re.finditer(r"[^\n]+", self.text):
            line = match.group(0)
            speaker, sep, _ = line.partition(": ")
            body_start = match.start() + (len(speaker) + len(sep) if sep else 0)
            body = self.text[body_start:match.end()]
            for start, end in split_sentences(body, body_start):
                n += 1
                passages.append(Passage(n=n, start=start, end=end, text=" ".join(self.text[start:end].split()),
                                        speaker=speaker if sep else None))
        return passages
