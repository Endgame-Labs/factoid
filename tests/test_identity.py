import json

from test_pipeline import Company, Contract, build

from factoid import Fact

META = {"signed_at": "2025-03-01T00:00:00Z"}


def test_an_outside_system_keeps_entities_in_step(make_app, fake):
    app = build(make_app, fake)
    acme = Company.upsert("Acme Corp", keys={"crm_id": "001"}, props={"jurisdiction": "Delaware"})
    same = Company.upsert("Acme Corporation", keys={"crm_id": "001"}, aliases=["ACME"])
    assert same.id == acme.id and same.name == "Acme Corporation"
    assert set(same.aliases) == {"Acme Corp", "ACME"} and same.jurisdiction == "Delaware"
    assert Company.find("Acme Corp").id == acme.id  # the old name still finds it
    assert [e["type"] for e in app.store.events_for(acme.id)][-1] == "entity.updated"


def test_merge_and_split_move_facts_and_search(make_app, fake):
    app = build(make_app, fake)
    result = app.ingest_text("Vega's liability to Orion is capped at $1M under the supply agreement.\n\n"
                             "Orion may not assign the agreement without Vega's consent.",
                             document_type=Contract, metadata=META, uri="a.txt")
    vega = Company.find("Vega")
    twin = Company.create("Vega Components Corp.", keys={"domain": "vega.example"})
    app.ingest_text("Vega Components Corp. ships servo motors.", document_type=Contract, metadata=META,
                    uri="b.txt")
    kept = vega.merge(twin, reason="same company in the CRM")
    assert Company.get(twin.id).id == vega.id and "Vega Components Corp." in kept.aliases
    assert Company.find("vega.example").id == vega.id
    assert {f.id for f in result.facts} <= {f.id for f in vega.facts()}

    cap = next(f for f in result.facts if "capped" in f.text)
    other = vega.split([cap], "Vega Holdings", keys={"domain": "vegaholdings.example"}, reason="the parent")
    assert [f.id for f in other.facts()] == [cap.id] and cap.id not in {f.id for f in vega.facts()}
    assert cap.id in {h.fact.id for h in app.search_facts("liability", about=other)}
    assert cap.id not in {h.fact.id for h in app.search_facts("liability", about=vega)}
    split = [json.loads(e["data"]) for e in app.store.events_for(vega.id) if e["type"] == "entity.split"]
    assert split == [{"into": other.id, "facts": [cap.id], "reason": "the parent"}]
    assert Fact.get(cap.id).status == "current"


def test_merge_and_split_from_the_cli(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from factoid import Entity
    from factoid.cli import _project, cli

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FACTOID_HOME", str(tmp_path))
    assert CliRunner().invoke(cli, ["init", "--package", "deal"]).exit_code == 0
    _, app = _project()
    with app.active():
        acme = Entity.create("Acme", kind="company")
        Entity.create("ACME Inc", kind="company")
    app.close()
    merged = CliRunner().invoke(cli, ["entities", "merge", "Acme", "ACME Inc", "--reason", "same company"])
    assert merged.exit_code == 0, merged.output
    assert f"merged into Acme ({acme.id}); also known as ACME Inc" in merged.output
    split = CliRunner().invoke(cli, ["entities", "split", acme.id, "--facts", "fact_none", "--name", "Acme Labs"])
    assert split.exit_code == 0 and "Acme Labs" in split.output and "0 facts" in split.output
    missing = CliRunner().invoke(cli, ["entities", "merge", "Acme", "Nobody"])
    assert missing.exit_code != 0 and "no entity 'Nobody'" in missing.output
