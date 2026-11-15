"""Legal traits and fact classes.

The first fourteen traits mirror CUAD categories, so the CUAD suite can score them. The rest are traits a deal team
needs that CUAD does not label.
"""

from factoid import Fact, FactTrait, Noul, judge


# -- traits CUAD labels ---------------------------------------------------------------------------------------

class ChangeOfControl(FactTrait):
    """A right or consequence triggered by a change in who owns or controls a party: a merger, an acquisition, or a
    transfer of a majority of its stock or assets."""


class AssignmentRestriction(FactTrait):
    """A party needs the other party's consent, or must give notice, to assign or transfer the contract or its rights
    to someone else."""


class LiabilityCap(FactTrait):
    """A limit on how much a party can owe under the contract, such as a dollar cap, a cap tied to fees paid, or an
    exclusion of a category of damages."""

    threshold = 0.6

    @classmethod
    @judge(limits_liability=Noul("Does the fact limit or exclude what a party can be liable for?"))
    def decide(cls, fact, judgments):
        return judgments.liability_cap >= cls.threshold and judgments.limits_liability >= 0.5


class Exclusivity(FactTrait):
    """An exclusive dealing commitment: a party must buy only from, sell only to, or license only to the other
    party, or may not deal with others in a territory or field."""


class NonCompete(FactTrait):
    """A restriction on a party competing with the other, or operating in a territory, business, or technology."""


class TerminationForConvenience(FactTrait):
    """A party may end the contract without cause, by giving notice, without the other party breaching."""


class GoverningLaw(FactTrait):
    """States which state's or country's law governs the contract."""


class AuditRights(FactTrait):
    """A party may audit or inspect the other party's books, records, or premises to check compliance."""


class Insurance(FactTrait):
    """A party must buy or keep insurance for the other party's benefit."""


class MinimumCommitment(FactTrait):
    """A party must buy, order, or pay at least a minimum amount, quantity, or number of units in a period."""


class LicenseGrant(FactTrait):
    """One party grants the other a license to use intellectual property, software, content, or a trademark."""


class IpOwnershipAssignment(FactTrait):
    """Intellectual property created under the contract is owned by, or assigned to, a party."""


class RenewalTerm(FactTrait):
    """The contract renews or extends after its initial term, automatically or at a party's option."""


class RevenueSharing(FactTrait):
    """A party must share revenue or profit with the other party."""


# -- traits a deal team needs that CUAD does not label --------------------------------------------------------

class ConsentRequired(FactTrait):
    """A named party must approve an action before it happens."""


class Deadline(FactTrait):
    """The latest time an action is allowed."""


class ClosingRisk(FactTrait):
    """Something that could delay or block the deal from closing."""


CUAD_TRAITS = {
    ChangeOfControl: "Change Of Control",
    AssignmentRestriction: "Anti-Assignment",
    LiabilityCap: "Cap On Liability",
    Exclusivity: "Exclusivity",
    NonCompete: "Non-Compete",
    TerminationForConvenience: "Termination For Convenience",
    GoverningLaw: "Governing Law",
    AuditRights: "Audit Rights",
    Insurance: "Insurance",
    MinimumCommitment: "Minimum Commitment",
    LicenseGrant: "License Grant",
    IpOwnershipAssignment: "Ip Ownership Assignment",
    RenewalTerm: "Renewal Term",
    RevenueSharing: "Revenue/Profit Sharing",
}


# -- fact classes -----------------------------------------------------------------------------------------------

class SourceFact(Fact):
    """What a contract, a client, or the other side says."""

    traits = [*CUAD_TRAITS, ConsentRequired, Deadline]
    max_length = 900  # contract clauses run long
    guidance = (
        "Every obligation, right, restriction, condition, payment term, date, and term of a contract counts, and so "
        "do representations, warranties, and covenants, which a deal team checks clause by clause."
    )


class CounselFact(Fact):
    """What our own lawyers concluded: an assessment, a recommendation, or a risk they identified."""

    traits = [ClosingRisk]
