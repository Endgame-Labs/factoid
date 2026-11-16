from factoid import ProseDocument

from .facts import SourceFact


class Contract(ProseDocument):
    """A signed contract or an amendment to one."""

    not_for = "Emails, memos, and drafts that discuss a contract."
    fact_classes = [SourceFact]  # a contract says what it says; our lawyers' views come from elsewhere
    sentence_passages = True  # quotes are single sentences, so a fact cites exactly the clause it rests on
    # Amendments that rewrite a section retire the clauses they replace. "Section 3.2 is amended to read in its
    # entirety" replaces the whole section; "the first paragraph of Section 4" replaces a part; "Section 6 is
    # deleted in its entirety" with no new text ends the old clauses.
    replacement_pattern = (
        r"(?:amended|restated)\s+(?:and\s+restated\s+)?(?:to\s+read\s+)?in\s+(?:its|their)\s+entirety"
        r"|deleted\s+in\s+(?:its|their)\s+entirety|replaced\s+in\s+(?:its|their)\s+entirety"
    )
    partial_replacement_pattern = r"paragraph|subsection|clause|sentence|definition|proviso|\d\s*\([a-z0-9]+\)"
    deletion_pattern = r"(?s)^(?!.*(?:replaced|as follows|to read)).*deleted\s+in\s+(?:its|their)\s+entirety"
    chunk_size = 6000
    chunk_overlap = "10%"
    guidance = (
        "This is a contract. Extract the obligations, rights, restrictions, conditions, dates, terms, amounts, and "
        "parties it sets out, one fact per clause or per distinct obligation. Name the contract and the parties in "
        "each fact (for example \"Under the Supply Agreement between Orion and Vega, ...\"), never \"this "
        "Agreement\" or \"the Company\". Keep exceptions and conditions in the same fact as the rule they limit."
    )

    @property
    def source_datetime(self):
        return self.metadata.get("signed_at")

    def context(self):
        parties = self.metadata.get("parties")
        return {"parties": parties} if parties else {}


class CounselEmail(ProseDocument):
    """An email between our lawyers and the client or the other side."""

    @property
    def source_datetime(self):
        return self.metadata.get("sent_at")

    def context(self):
        return {k: self.metadata[k] for k in ("from", "to", "subject") if self.metadata.get(k)}
