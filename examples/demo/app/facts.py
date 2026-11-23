"""What the customer and the vendor say on a deal, with traits a sales team would filter on."""

from factoid import Fact, FactTrait


class PainPoint(FactTrait):
    """A problem the customer has today that the purchase should solve."""


class Timeline(FactTrait):
    """A date the customer plans to buy, sign, cut over, or go live by."""


class Pricing(FactTrait):
    """A price, a pricing model, a seat count, or a budget."""


class SecurityRequirement(FactTrait):
    """A security or compliance requirement, such as a report, a certification, or encryption."""


class Commitment(FactTrait):
    """Something a person promised to do, often by a date."""


class CustomerFact(Fact):
    """What the customer, Kestrel Health, says about its needs, plans, budget, and requirements."""

    traits = [PainPoint, Timeline, Pricing, SecurityRequirement, Commitment]


class VendorFact(Fact):
    """What the vendor, Northstar Data, says about its product, its pricing, or what it will do."""

    traits = [Pricing, SecurityRequirement, Commitment]
