from factoid import Fact


class TranscriptFact(Fact):
    """What a speaker in a transcript said, reported, or believes."""

    guidance = "Keep who said each claim. An opinion or a belief is a fact about the person who holds it."
