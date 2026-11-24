from factoid import ProseDocument

from .facts import ChangeFact


class ReleaseNotes(ProseDocument):
    """One Python release's "What's New" page: its new modules, deprecations, and removals."""

    fact_classes = [ChangeFact]
    guidance = "The page is about the release in its title. A fact without a version is about that release."

    @property
    def source_datetime(self):
        return self.metadata.get("released_at")

    def context(self):
        return {k: self.metadata[k] for k in ("version", "url") if self.metadata.get(k)}
