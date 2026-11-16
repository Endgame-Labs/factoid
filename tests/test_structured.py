from __future__ import annotations

import json
import re

import pytest

from factoid import Entity, Fact, Identity, Ignore, Property, StructuredDocument, Text
from factoid.document import Raw
from factoid.structured import read_rows


class Agreement(Entity):
    """A contract between two or more parties."""

    governing_law: str


class Company(Entity):
    """A company."""


class ContractRegister(StructuredDocument):
    """The data room's list of the target's contracts."""

    row_entity = Agreement
    key = "contract_id"
    when = "updated_at"
    columns = {
        "contract_id": Identity(Agreement, "contract_id", name="Contract {contract_id}"),
        "counterparty": Identity(Company, "company_name"),
        "governing_law": Property(Agreement, "governing_law"),
        "annual_value": "Contract {contract_id} with {counterparty} is worth ${annual_value} a year.",
        "notes": Text(),
        "internal_ref": Ignore(),
    }


REGISTER = """contract_id,counterparty,governing_law,annual_value,notes,internal_ref,updated_at
C-1,Vega Corp,New York,50000,,x1,2026-01-05T00:00:00Z
C-2,Orion Inc,"Delaware",120000,,x2,2026-01-05T00:00:00Z
"""


def build(make_app, fake):
    return make_app(documents=[ContractRegister], entities=[Agreement, Company], facts=[Fact])


def test_read_rows_detects_csv_jsonl_and_json():
    csv_rows = read_rows("a,b\n1,\"two, too\"\n\n3,4\n")
    assert [r.values for r in csv_rows] == [{"a": "1", "b": "two, too"}, {"a": "3", "b": "4"}]
    text = "a,b\n1,2\n3,4\n"
    assert [text[r.start:r.end] for r in read_rows(text)] == ["1,2", "3,4"]
    assert [r.values for r in read_rows('{"a": 1}\n{"a": 2}\n')] == [{"a": 1}, {"a": 2}]
    assert [r.values for r in read_rows('[{"a": 1}, {"a": 2}]')] == [{"a": 1}, {"a": 2}]
    assert [r.values for r in read_rows("a\tb\n1\t2\n")] == [{"a": "1", "b": "2"}]


def test_columns_are_checked_when_the_class_is_defined():
    with pytest.raises(ValueError, match="unknown columns"):
        type("Bad", (StructuredDocument,), {"columns": {"a": "{b} is {a}"}})
    with pytest.raises(ValueError, match="needs an Identity column"):
        type("Bad", (StructuredDocument,), {"row_entity": Agreement, "columns": {"a": Ignore()}})
    with pytest.raises(TypeError):
        type("Bad", (StructuredDocument,), {"columns": {"a": 3}})


def test_rows_link_by_key_set_properties_and_cite_cells(make_app, fake):
    app = build(make_app, fake)
    result = app.ingest(Raw(REGISTER, uri="register.csv"))
    assert isinstance(result.document, ContractRegister)  # matched by header, not by the model
    assert not any("document_class" in q for _, q in fake.asked)
    texts = sorted(f.text for f in result.facts)
    assert texts == ["Contract C-1 with Vega Corp is worth $50000 a year.",
                     "Contract C-2 with Orion Inc is worth $120000 a year."]
    c1 = Agreement.find("Contract C-1")
    assert c1 is not None and c1.governing_law == "New York"
    fact = next(f for f in result.facts if "C-1" in f.text)
    assert {(m.role, m.entity_id) for m in fact.mentions} == {("subject", c1.id),
                                                               ("about", Company.find("Vega Corp").id)}
    quote = fact.quotes[0]
    assert (quote.passage_n, quote.section, quote.text) == (1, "annual_value", "50000")
    assert REGISTER[quote.start:quote.end].startswith("C-1,Vega Corp")
    assert fact.valid_from.year == 2026 and not fake.prompts  # no generation for templated cells


def test_reimport_supersedes_a_changed_value_by_rule(make_app, fake):
    app = build(make_app, fake)
    app.ingest(Raw(REGISTER, uri="register.csv"))
    changed = REGISTER.replace("50000,,x1,2026-01-05", "65000,,x1,2026-03-01")
    asked = len(fake.asked)
    second = app.ingest(Raw(changed, uri="register.csv"))
    assert [f.text for f in second.facts] == ["Contract C-1 with Vega Corp is worth $65000 a year."]
    assert second.duplicates == 1  # C-2 did not change
    old = next(f for f in app.list_facts() if "$50000" in f.text)
    assert old.status == "superseded" and old.valid_until.month == 3
    assert not any(re.fullmatch(r"F\d+", k) for _, q in fake.asked[asked:] for k in q)  # no resolve question


def test_text_cells_go_through_extraction_with_the_row_entity_known(make_app, fake):
    def extractor(prompt):
        found = re.findall(r"^\[(\d+)\] (.+)$", prompt, re.M)
        return json.dumps({"facts": [{"text": f"Under contract C-1, {t}", "passages": [int(n)], "mentions": []}
                                     for n, t in found]})

    fake.generator = extractor
    app = build(make_app, fake)
    text = REGISTER.replace("50000,,x1", "50000,Vega may terminate on 30 days notice.,x1")
    result = app.ingest(Raw(text, uri="register.csv"))
    extracted = [f for f in result.facts if f.text.startswith("Under contract")]
    assert len(extracted) == 1
    assert "contract_id (already identified): Contract C-1" in fake.prompts[0]
    fact = extracted[0]
    assert fact.mentions[0].entity_id == Agreement.find("Contract C-1").id
    assert (fact.quotes[0].passage_n, fact.quotes[0].section) == (1, "notes")


def test_records_and_a_header_that_matches_no_class(make_app, fake):
    app = build(make_app, fake)
    doc = ContractRegister.from_records([{"contract_id": "C-9", "counterparty": "Lyra", "governing_law": "Texas",
                                          "annual_value": 7, "notes": None, "internal_ref": "", "updated_at": ""}],
                                        uri="api:contracts")
    result = app.ingest(doc)
    assert [f.text for f in result.facts] == ["Contract C-9 with Lyra is worth $7 a year."]
    with pytest.raises(ValueError, match="no document class"):
        fake.choice = lambda q, s, n: {k: (0.9 if k == "_other" else 0.1) for k, _ in q.options}
        fake.noul = lambda q, s: 0.1
        app.ingest(Raw("name,age\nAda,36\n", uri="people.csv"))
