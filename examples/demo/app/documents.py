from factoid import ProseDocument

from .facts import CustomerFact, VendorFact


class CallTranscript(ProseDocument):
    """A transcript of a sales call, one line per turn: "[mm:ss] Name: what they said"."""

    fact_classes = [CustomerFact, VendorFact]
    speaker_pattern = r"\[\d+:\d\d\]\s+(?P<speaker_name>[A-Z][\w.'-]+(?: [A-Z][\w.'-]+)*):\s"
    guidance = (
        "Name who said each fact (\"Elena Ortiz said ...\") when it is a plan, a requirement, or a promise. Name the "
        "companies in full. Turn relative dates such as \"this Friday\" into dates, using the call's date."
    )

    @property
    def source_datetime(self):
        return self.metadata.get("held_at")

    def context(self):
        return {k: self.metadata[k] for k in ("participants",) if self.metadata.get(k)}


class Email(ProseDocument):
    """An email between the customer and the vendor."""

    fact_classes = [CustomerFact, VendorFact]
    guidance = "The sender wrote the email: name them when a fact is their plan or promise."

    @property
    def source_datetime(self):
        return self.metadata.get("sent_at")

    def context(self):
        return {k: self.metadata[k] for k in ("from", "to") if self.metadata.get(k)}
