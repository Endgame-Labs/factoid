"""The `factoid` command.

Inside a project, `factoid` finds the project's environment and runs there, so users never type `uv run`.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from . import scaffold
from .models import PROVIDERS, ModelError, keys_file, load_keys
from .project import find_root, load, package_name

__all__ = ["main"]


def _reexec_in_project() -> None:
    """Run inside the project's environment when its package is not importable here."""
    if os.environ.get("FACTOID_IN_PROJECT"):
        return
    root = find_root()
    if root is None or not (root / "pyproject.toml").is_file():
        return
    package = package_name(root)
    import importlib.util

    for path in (root / "src", root):
        if (path / package).is_dir():
            sys.path.insert(0, str(path))
    try:
        found = importlib.util.find_spec(package) is not None and importlib.util.find_spec("factoid") is not None
    except (ImportError, ValueError):
        found = False
    if found or shutil.which("uv") is None or not (root / ".venv").exists():
        return
    os.environ["FACTOID_IN_PROJECT"] = "1"
    os.execvp("uv", ["uv", "run", "--project", str(root), "--quiet", "factoid", *sys.argv[1:]])


def _project(**kwargs: Any) -> Any:
    try:
        project = load()
    except FileNotFoundError as err:
        raise click.ClickException(str(err)) from err
    load_keys(project.root)
    return project, project.app(**kwargs)


def _echo_json(value: Any) -> None:
    click.echo(json.dumps(value, indent=2, default=str))


@click.group()
@click.version_option(package_name="factoid")
def cli() -> None:
    """Factoid turns documents into facts and entities."""


# -- init ---------------------------------------------------------------------------------------------------


@cli.command()
@click.option("--package", help="Python package name (defaults to the folder name).")
def init(package: str | None) -> None:
    """Set up a project in the current folder: sample classes, sample documents, and an eval."""
    root = Path.cwd()
    if (root / "pyproject.toml").exists() and find_root(root) == root:
        raise click.ClickException("this folder is already a Factoid project")
    name = package or root.name.replace("-", "_").lower()
    for path in scaffold.write(root, name):
        click.echo(f"  wrote {path.relative_to(root)}")
    click.echo("Next: factoid doctor, then factoid ingest sample_docs")


# -- ingest and reads ---------------------------------------------------------------------------------------


@cli.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--as", "as_class", help="Document class to use, instead of classifying.")
@click.option("--dry-run", is_flag=True, help="Run the whole pipeline and write nothing.")
def ingest(paths: tuple[Path, ...], as_class: str | None, dry_run: bool) -> None:
    """Ingest documents: files or folders."""
    project, app = _project(in_memory=dry_run)
    if dry_run:
        app.calls = type(app.calls)(project.settings.data_path(project.root) / "calls.db")
        app.client.log = app.calls
    klass = app.document_class(as_class) if as_class else None
    files = [p for path in paths for p in (sorted(path.rglob("*")) if path.is_dir() else [path])
             if p.is_file() and not p.name.endswith(".meta.json") and not p.name.startswith(".")]
    for path in files:
        result = app.ingest(path, document_type=klass)
        click.echo(f"{path}: {type(result.document).__name__}, {len(result.facts)} facts, "
                   f"{len(result.rejected)} rejected, {result.duplicates} duplicates")
        if dry_run:
            for fact in result.facts:
                traits = f" [{', '.join(fact.trait_names)}]" if fact.trait_names else ""
                click.echo(f"  + {fact.text}{traits}")
            for rejected in result.rejected:
                click.echo(f"  - {rejected.text}  ({', '.join(rejected.reasons)})")
    total = app.meter.total()
    click.echo(f"model calls: {int(total['calls'])} ({int(total['cache_hits'])} replayed), "
               f"{int(total['input_tokens'])} input tokens, {int(total['output_tokens'])} output tokens")
    app.close()


@cli.command()
@click.argument("query")
@click.option("--about", help="Only facts linked to this entity (a name or key).")
@click.option("--as-of", help="Weight relevance by validity as of this date.")
@click.option("--top-k", default=10, show_default=True)
@click.option("--chunks", is_flag=True, help="Search source chunks instead of facts.")
@click.option("--json", "as_json", is_flag=True)
def search(query: str, about: str | None, as_of: str | None, top_k: int, chunks: bool, as_json: bool) -> None:
    """Search facts (or chunks)."""
    from .entity import Entity

    _, app = _project()
    entity = None
    if about:
        entity = Entity.find(about)
        if entity is None:
            raise click.ClickException(f"no entity named {about!r}")
    if chunks:
        rows = app.search_chunks(query, about=entity, top_k=top_k)
        if as_json:
            return _echo_json(rows)
        for row in rows:
            click.echo(f"{row['score']:.3f}  {row['id']}  {row['text'][:200]!r}")
        return
    hits = app.search_facts(query, about=entity, as_of=as_of, top_k=top_k)
    if as_json:
        return _echo_json([{"id": h.fact.id, "text": h.fact.text, "score": h.score, "validity": h.validity,
                            "traits": h.fact.trait_names, "contradictions": h.contradiction_ids} for h in hits])
    for hit in hits:
        traits = f" [{', '.join(hit.fact.trait_names)}]" if hit.fact.trait_names else ""
        click.echo(f"{hit.score:.4f}  {hit.fact.id}  {hit.fact.text}{traits}")
        for other in hit.contradictions:
            click.echo(f"         contradicted by {other.id}: {other.text}")


@cli.command()
@click.argument("fact_id")
def read(fact_id: str) -> None:
    """One fact, its quotes, its entities, and its history."""
    _, app = _project()
    fact = app.load_fact(fact_id)
    if fact is None:
        raise click.ClickException(f"no fact {fact_id}")
    click.echo(f"{fact.id}  ({type(fact).__name__}, {fact.status})")
    click.echo(f"  {fact.text}")
    click.echo(f"  traits: {', '.join(fact.trait_names) or 'none'}")
    click.echo(f"  valid_from: {fact.valid_from}  expires: {fact.expires}  valid_until: {fact.valid_until}")
    if fact.lifetime:
        click.echo(f"  lifetime: {fact.lifetime}")
    click.echo(f"  still valid now: {fact.valid_at():.2f}")
    for q in fact.quotes:
        click.echo(f"  quote [{q.document_id} #{q.passage_n}]: {q.text[:300]}")
    for m in fact.mentions:
        click.echo(f"  mention {m.text!r} ({m.role}) -> {m.entity_id or 'unlinked'} via {m.method}")
    for row in app.store.relations(fact.id):
        click.echo(f"  relation: {row['fact_id']} {row['relation']} {row['other_id']}")
    for row in app.store.events_for(fact.id):
        click.echo(f"  event {row['seq']}: {row['at']} {row['type']} {row['data']}")


@cli.command()
@click.option("--json", "as_json", is_flag=True)
def stats(as_json: bool) -> None:
    """Facts by status, facts with no trait, unlinked mentions, stale facts, and open contradictions."""
    _, app = _project()
    data = app.stats()
    if as_json:
        return _echo_json(data)
    for key, value in data.items():
        click.echo(f"{key}: {value}")


@cli.group()
def entities() -> None:
    """Entities: list them and their untyped kinds."""


@entities.command("list")
@click.option("--class", "class_name")
def entities_list(class_name: str | None) -> None:
    _, app = _project()
    sql = "select id, class, kind, name from entities where merged_into is null"
    params: list[Any] = []
    if class_name:
        sql += " and class = ?"
        params.append(class_name)
    for row in app.store.query(sql + " order by name", params):
        click.echo(f"{row['id']}  {row['class']:<12} {row['kind'] or '':<14} {row['name']}")


@entities.command("kinds")
def entities_kinds() -> None:
    """Untyped kinds by entity and fact count."""
    _, app = _project()
    rows = app.store.query(
        "select e.kind, count(distinct e.id) entities, count(distinct m.fact_id) facts from entities e "
        "left join mentions m on m.entity_id = e.id where e.class = 'Entity' and e.merged_into is null "
        "group by e.kind order by facts desc")
    for row in rows:
        click.echo(f"{row['kind'] or '(none)':<24} {row['entities']:>6} entities {row['facts']:>7} facts")


# -- introspection ------------------------------------------------------------------------------------------


@cli.group()
def steps() -> None:
    """Inspect pipeline steps."""


@steps.command("show")
@click.argument("class_name")
def steps_show(class_name: str) -> None:
    """Each step, the class that defines it, and its hooks."""
    from .steps import describe_steps

    project, _ = _project(in_memory=True)
    pool = {k.__name__: k for k in [*project.documents, *project.facts, *project.entities]}
    from .document import ProseDocument
    from .entity import Entity
    from .fact import Fact

    pool.update({"ProseDocument": ProseDocument, "Fact": Fact, "Entity": Entity})
    klass = pool.get(class_name)
    if klass is None:
        raise click.ClickException(f"no class named {class_name}; known: {', '.join(sorted(pool))}")
    for row in describe_steps(klass):
        hooks = f"  hooks: {', '.join(row['hooks'])}" if row["hooks"] else ""
        click.echo(f"{row['step']:<16} {row['kind']:<12} {row['defined_in']}{hooks}")


@cli.group()
def classifiers() -> None:
    """Inspect the document classifier registry."""


@classifiers.command("show")
def classifiers_show() -> None:
    from .judge import questions_of

    project, _ = _project(in_memory=True)
    for klass in project.documents:
        own = questions_of(klass.classify)
        extra = f"  asks: {', '.join(own)}" if own else ""
        click.echo(f"{klass.__name__}: {klass.description()}{extra}")


@cli.group()
def prompts() -> None:
    """Inspect prompts and questions."""


@prompts.command("show")
@click.argument("target")
def prompts_show(target: str) -> None:
    """The wording in effect for CLASS.STEP, and where it came from."""
    from .templates import Template

    project, _ = _project(in_memory=True)
    class_name, _, step = target.partition(".")
    pool = {k.__name__: k for k in [*project.documents, *project.facts, *project.entities]}
    klass = pool.get(class_name)
    if klass is None:
        raise click.ClickException(f"no class named {class_name}")
    if step == "assess" and hasattr(klass, "assess_questions"):
        for name, question in klass.assess_questions().items():
            click.echo(f"{name}: {json.dumps(question.wire(), indent=2)}")
        return
    wording = getattr(klass, f"{step}_prompt", None) or getattr(klass, f"{step}_question", None)
    if wording is None:
        raise click.ClickException(f"{class_name} has no prompt or question for {step}")
    origin = wording.origin if isinstance(wording, Template) else "a string on the class"
    owner = next((k.__name__ for k in klass.__mro__ if f"{step}_prompt" in vars(k) or f"{step}_question" in vars(k)),
                 "?")
    click.echo(f"# from {origin} (set on {owner})")
    click.echo(wording.source if isinstance(wording, Template) else wording)


# -- keys, models, and doctor -------------------------------------------------------------------------------


@cli.group()
def keys() -> None:
    """Provider keys."""


@keys.command("set")
@click.argument("provider", type=click.Choice(sorted([*PROVIDERS, "turbopuffer"])))
@click.option("--project", "for_project", is_flag=True, help="Store the key for the current project only.")
def keys_set(provider: str, for_project: bool) -> None:
    """Prompt for a key and store it in ~/.factoid/.env (or the project's .factoid/.env)."""
    root = find_root() if for_project else None
    if for_project and root is None:
        raise click.ClickException("not inside a Factoid project")
    env = "TURBOPUFFER_API_KEY" if provider == "turbopuffer" else PROVIDERS[provider].key_env
    value = click.prompt(f"{env}", hide_input=True).strip()
    path = keys_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [ln for ln in (path.read_text().splitlines() if path.exists() else []) if not ln.startswith(f"{env}=")]
    lines.append(f"{env}={value}")
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o600)
    click.echo(f"stored {env} in {path}")


@cli.command()
def models() -> None:
    """Each workload, its model, and whether its key is set."""
    _, app = _project(in_memory=True)
    click.echo(f"{'workload':<10} {'model':<34} key")
    for workload in ("choose", "generate", "embed", "rerank"):
        model = app.client.models.get(workload)
        if model is None:
            click.echo(f"{workload:<10} {'(none)':<34} -")
            continue
        provider = model.provider
        status = "set" if provider.api_key() else f"not set (using {provider.base_url()})"
        click.echo(f"{workload:<10} {model.name:<34} {status}")


@cli.command()
def doctor() -> None:
    """Make one small call per workload and report what works."""
    from .judge import Noul

    _, app = _project(in_memory=True)
    app.client.replay = False
    checks = {
        "choose": lambda: app.client.ask({"text": "Factoid doctor."}, {"ok": Noul("Is this a test?")}),
        "generate": lambda: app.client.generate("Answer with the word ok."),
        "embed": lambda: app.client.embed(["ok"]),
    }
    if app.client.models.get("rerank"):
        checks["rerank"] = lambda: app.client.rerank("ok", ["ok", "no"])
    failed = False
    for workload, check in checks.items():
        try:
            check()
            click.echo(f"{workload:<10} ok")
        except (ModelError, Exception) as err:  # noqa: BLE001 - report every failure
            failed = True
            click.echo(f"{workload:<10} FAILED: {err}")
    try:
        app.index.bm25(app.ns("facts"), "doctor", 1)
        click.echo(f"{'search':<10} ok ({type(app.index).__name__})")
    except Exception as err:  # noqa: BLE001
        failed = True
        click.echo(f"{'search':<10} FAILED: {err}")
    if failed:
        sys.exit(1)


# -- eval ---------------------------------------------------------------------------------------------------


@cli.command("eval")
@click.argument("suites", nargs=-1)
@click.option("--vary", multiple=True, help="Run each value of a setting, such as fact_evals=none,jev_floors.")
@click.option("--limit", type=int, help="Use only the first N documents of each suite.")
@click.option("--fresh", is_flag=True, help="Do not replay cached model calls.")
@click.option("--quiet", is_flag=True)
def eval_(suites: tuple[str, ...], vary: tuple[str, ...], limit: int | None, fresh: bool, quiet: bool) -> None:
    """Score the project against its labeled suites."""
    from .evals import load_suites, parse_vary, run_suite

    project, _ = _project(in_memory=True)
    found = load_suites(project)
    if not found:
        raise click.ClickException("no suites in evals/")
    chosen = suites or tuple(found)
    unknown = [s for s in chosen if s not in found]
    if unknown:
        raise click.ClickException(f"unknown suites {unknown}; known: {sorted(found)}")
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    run_dir = project.root / "runs" / stamp
    results = []
    for name in chosen:
        suite = found[name]()
        for variant in parse_vary(list(vary)):
            click.echo(f"{name} / {variant.name}")
            results.append(run_suite(project, suite, variant, limit=limit, run_dir=run_dir / name,
                                     replay=not fresh, log=None if quiet else click.echo))
    click.echo("")
    for result in results:
        total = result.usage["total"]
        click.echo(f"{result.suite} / {result.variant.name}: {result.documents} docs, {result.facts} facts, "
                   f"{result.rejected} rejected, {int(total['calls'])} calls ({int(total['cache_hits'])} replayed), "
                   f"{int(total['input_tokens'] + total['output_tokens'])} tokens, "
                   f"p50 {result.latency.get('p50_doc_s', 0)}s/doc")
        for key, value in _flatten(result.metrics).items():
            click.echo(f"    {key:<44} {value}")
    click.echo(f"\nscorecards: {run_dir}")


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict) and len(value) <= 12 and all(not isinstance(v, dict) for v in value.values()) \
                and all(isinstance(v, (int, float)) for v in value.values()):
            out[name] = " ".join(f"{k}={v}" for k, v in value.items())
        elif isinstance(value, dict):
            out.update(_flatten(value, name + "."))
        else:
            out[name] = value
    return out


def main() -> None:
    _reexec_in_project()
    cli()
