from factoid import Entity


class Company(Entity):
    """A company or other organization that is a party to a deal or a contract."""

    unique_keys = ["domain"]
    jurisdiction: str


class Agreement(Entity):
    """One contract and its amendments, as a whole, such as a named supply, license, or services agreement."""

    unique_keys = ["contract_id"]
    counterparty: str
    governing_law: str


class Person(Entity):
    """A named person: a lawyer, a client contact, a signatory, or someone at the other side."""

    unique_keys = ["email"]
    role: str
