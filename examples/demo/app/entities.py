from factoid import Entity


class Company(Entity):
    """A company: the customer, Kestrel Health, or the vendor, Northstar Data."""


class Person(Entity):
    """A person at the customer or the vendor."""


class Product(Entity):
    """A software product or cloud service, such as Redshift or AWS KMS."""
