"""The `factoid` command.

Inside a project, `factoid` finds the project's environment and runs there, so users never type `uv run`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import click

from . import scaffold
from .models import (
    GENERATION_STEPS,
    KEY_SOURCES,
    PROVIDERS,
    ModelError,
    check_models,
    keys_file,
    load_keys,
)
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


def _project_or_defaults() -> Any:
    """The project's app, or, outside a project, an app with the default settings (for `models` and `doctor`)."""
    if find_root() is not None:
        return _project(in_memory=True)[1]
    from .app import Factoid
    from .settings import Settings

    load_keys(None)
    click.echo("(not in a Factoid project: showing the default models; `factoid init` creates a project)")
    return Factoid(Settings, in_memory=True, documents=[], entities=[], facts=[])


#: What each provider's keys start with, to catch a paste of the wrong thing.
KEY_PREFIXES = {"fireworks": "fw_", "openai": "sk-", "openrouter": "sk-or-"}


def check_key(provider: str, value: str) -> str | None:
    """A problem with a pasted key, or None."""
    if not value:
        return "the key is empty"
    if any(not ch.isprintable() or ch.isspace() for ch in value):
        return ("the key has spaces, control characters, or terminal escape codes in it; paste it again, or set "
                "it with an environment variable")
    prefix = KEY_PREFIXES.get(provider)
    if prefix and not value.startswith(prefix):
        return f"{provider} keys start with {prefix!r}, and this one does not"
    return None


def _echo_json(value: Any) -> None:
    click.echo(json.dumps(value, indent=2, default=str))


def _echo_calls(total: dict[str, float], cache: Path | None) -> None:
    """The model call line, which says plainly when answers came from the cache instead of the models."""
    calls, replayed, older = int(total["calls"]), int(total["cache_hits"]), int(total.get("older_hits", 0))
    click.echo(f"model calls: {calls}, {int(total['input_tokens']):,} input tokens, "
               f"{int(total['output_tokens']):,} output tokens")
    if replayed:
        where = f" from {_rel(cache)}" if cache else ""
        click.echo(f"  {replayed} of the {calls} calls were replayed{where}: identical requests reuse saved answers "
                   f"and cost nothing.")
        if older:
            click.echo(f"  {older} of those answers were saved by a different version of Factoid.")
        click.echo("  --fresh calls the models again.")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def _local(stamp: str | None) -> str:
    """A stored UTC time shown in the local time zone, with its offset."""
    if not stamp:
        return str(stamp)
    try:
        moment = datetime.fromisoformat(stamp)
    except ValueError:
        return stamp
    if moment.tzinfo is None:
        return stamp
    return moment.astimezone().isoformat(timespec="seconds")


def _data_dir_option(func: Any) -> Any:
    return click.option("--data-dir", type=click.Path(exists=True, file_okay=False, path_type=Path),
                        help="Another store, such as an eval run's folder (runs/<time>/<suite>/<variant>).")(func)


def _app_for(data_dir: Path | None) -> Any:
    return _project(**({"data_dir": data_dir} if data_dir else {}))[1]


def _version_message() -> str:
    from .version import describe

    return f"factoid {describe()}"


@click.group()
@click.version_option(message=_version_message())
def cli() -> None:
    """Factoid turns documents into facts and entities."""


# -- init ---------------------------------------------------------------------------------------------------


@cli.command()
@click.option("--package", help="Python package name (defaults to the folder name).")
@click.option("--models", "preset", type=click.Choice(list(scaffold.PRESETS)), default="jev", show_default=True,
              help="Which providers settings.py uses: jev (TypeSafe and Fireworks), fireworks (Fireworks alone), "
                   "or openai (OpenAI alone).")
def init(package: str | None, preset: str) -> None:
    """Set up a project in the current folder: sample classes, sample documents, and an eval."""
    root = Path.cwd()
    if (root / "pyproject.toml").exists() and find_root(root) == root:
        raise click.ClickException("this folder is already a Factoid project")
    name = package or root.name.replace("-", "_").lower()
    for path in scaffold.write(root, name, preset):
        click.echo(f"  wrote {path.relative_to(root)}")
    providers = scaffold.PRESETS[preset][0]
    if preset == "fireworks":
        click.echo("\nThe fireworks preset is experimental: Rune's fact eval floors come from one news eval, and the "
                   "contract\nevals have not been run on it yet. --models openai is the fully checked one-key choice.")
    click.echo(f"\nThese models need a key for {' and '.join(providers)}. Next:")
    click.echo("  factoid keys set               asks for each key and says where to get it")
    click.echo("  factoid doctor                 one small call per workload")
    click.echo("  factoid ingest sample_docs")


# -- ingest and reads ---------------------------------------------------------------------------------------


@cli.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--as", "as_class", help="Document class to use, instead of classifying.")
@click.option("--dry-run", is_flag=True, help="Run the whole pipeline and write nothing.")
@click.option("--again", is_flag=True, help="Ingest documents that are stored already and have not changed.")
@click.option("--fresh", is_flag=True, help="Call the models even for requests whose answers are cached.")
def ingest(paths: tuple[Path, ...], as_class: str | None, dry_run: bool, again: bool, fresh: bool) -> None:
    """Ingest documents: files or folders. A document that is stored already and has not changed is skipped."""
    project, app = _project(in_memory=dry_run, **({"replay": False} if fresh else {}))
    if dry_run:
        app.calls = type(app.calls)(project.settings.data_path(project.root) / "calls.db")
        app.client.log = app.calls
    klass = app.document_class(as_class) if as_class else None
    files = [p for path in paths for p in (sorted(path.rglob("*")) if path.is_dir() else [path])
             if p.is_file() and not p.name.endswith(".meta.json") and not p.name.startswith(".")]
    for path in files:
        result = app.ingest(path, document_type=klass, again=again)
        if result.unchanged:
            click.echo(f"{path}: unchanged since it was ingested, so skipped ({len(result.facts)} current facts; "
                       f"--again ingests it anyway)")
            continue
        click.echo(f"{path}: {type(result.document).__name__}, {len(result.facts)} facts, "
                   f"{len(result.rejected)} rejected, {result.duplicates} duplicates")
        if dry_run:
            for fact in result.facts:
                traits = f" [{', '.join(fact.trait_names)}]" if fact.trait_names else ""
                click.echo(f"  + {fact.text}{traits}")
            for rejected in result.rejected:
                click.echo(f"  - {rejected.text}  ({', '.join(rejected.reasons)})")
    _echo_calls(app.meter.total(), getattr(app.calls, "path", None))
    app.close()


@cli.command()
@click.argument("query")
@click.option("--about", help="Only facts linked to this entity (a name or key).")
@click.option("--as-of", help="Weight relevance by validity as of this date.")
@click.option("--top-k", default=10, show_default=True)
@click.option("--chunks", is_flag=True, help="Search source chunks instead of facts.")
@click.option("--json", "as_json", is_flag=True)
@_data_dir_option
def search(query: str, about: str | None, as_of: str | None, top_k: int, chunks: bool, as_json: bool,
           data_dir: Path | None) -> None:
    """Search facts (or chunks). The score ranks results: keyword and vector ranks fused (reciprocal rank fusion),
    times how likely the fact is still valid. It is not a similarity, and values near 0.03 are normal."""
    from .entity import Entity

    app = _app_for(data_dir)
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
    if hits:
        click.echo("(score: fused keyword and vector rank, times validity; it orders results and is not a similarity)")


@cli.command()
@click.argument("fact_id")
@_data_dir_option
def read(fact_id: str, data_dir: Path | None) -> None:
    """One fact, its quotes, its entities, and its history. Fact ids come from `search` and `facts list`."""
    app = _app_for(data_dir)
    fact = app.load_fact(fact_id)
    if fact is None:
        raise click.ClickException(f"no fact {fact_id}")
    click.echo(f"{fact.id}  ({type(fact).__name__}, {fact.status})")
    click.echo(f"  {fact.text}")
    click.echo(f"  traits: {', '.join(fact.trait_names) or 'none'}")
    click.echo(f"  valid_from: {fact.valid_from}  expires: {fact.expires}  valid_until: {fact.valid_until}")
    if fact.lifetime:
        click.echo(f"  lifetime: {fact.lifetime}")
    click.echo(f"  still valid now: {fact.valid_at():.2f}  ({_validity_note(fact)})")
    for q in fact.quotes:
        click.echo(f"  quote [{q.document_id} #{q.passage_n}]: {q.text[:300]}")
    for m in fact.mentions:
        click.echo(f"  mention {m.text!r} ({m.role}) -> {m.entity_id or 'unlinked'} via {m.method}")
    for row in app.store.relations(fact.id):
        click.echo(f"  relation: {row['fact_id']} {row['relation']} {row['other_id']}")
    for row in app.store.events_for(fact.id):
        click.echo(f"  event {row['seq']}: {_local(row['at'])} {row['type']} {row['data']}")


def _validity_note(fact: Any) -> str:
    """How `still valid now` was worked out, in a few words."""
    if fact.status in ("corrected", "retracted"):
        return f"the fact is {fact.status}"
    if fact.status in ("superseded", "ended"):
        return "it held until valid_until" if fact.valid_until else f"the fact is {fact.status}"
    if fact.expires in (None, "never"):
        return "it does not expire"
    if fact.expires == "at_deadline":
        return "it holds until valid_until"
    if not fact.lifetime:
        return "no lifetime estimate, so it is taken as still true"
    total = sum(fact.lifetime.values()) or 1.0
    spread = ", ".join(f"{name} {weight / total:.0%}" for name, weight in fact.lifetime.items())
    return f"the chance it still holds: it decays from valid_from by its estimated lifetime ({spread})"


@cli.command()
@click.option("--json", "as_json", is_flag=True)
@click.option("--examples", default=0, show_default=True,
              help="Up to N sample facts per fact class, at most one per document, and the N entities with the most "
                   "facts per entity class.")
@click.option("--data-dir", type=click.Path(exists=True, file_okay=False, path_type=Path),
              help="Another store, such as an eval run's folder (runs/<time>/<suite>/<variant>).")
def stats(as_json: bool, examples: int, data_dir: Path | None) -> None:
    """Documents, facts, and entities by class; facts by status; facts with no trait, unlinked mentions, stale
    facts, and open contradictions. With --examples, sample facts and the most connected entities."""
    _, app = _project(**({"data_dir": data_dir} if data_dir else {}))
    data = app.stats(examples=examples)
    if as_json:
        return _echo_json(data)
    sample = data.pop("examples", None)
    for key, value in data.items():
        click.echo(f"{key}: {value}")
    if sample:
        for klass, texts in sample["facts"].items():
            click.echo(f"\n{klass} facts:")
            for text in texts:
                click.echo(f"  - {text}")
        for klass, rows in sample["entities"].items():
            click.echo(f"\n{'Untyped' if klass == 'Entity' else klass} entities:")
            for row in rows:
                click.echo(f"  - {row['name']} ({row['facts']} fact{'s' if row['facts'] != 1 else ''})")


@cli.group()
def entities() -> None:
    """Entities: list them and their untyped kinds."""


@entities.command("list")
@click.option("--class", "class_name")
@_data_dir_option
def entities_list(class_name: str | None, data_dir: Path | None) -> None:
    """Entities by name, with their class, untyped kind, and other names."""
    app = _app_for(data_dir)
    sql = "select id, class, kind, name, aliases from entities where merged_into is null"
    params: list[Any] = []
    if class_name:
        sql += " and class = ?"
        params.append(class_name)
    for row in app.store.query(sql + " order by name", params):
        aliases = json.loads(row["aliases"] or "[]")
        also = f"  (also: {'; '.join(aliases)})" if aliases else ""
        click.echo(f"{row['id']}  {row['class']:<12} {row['kind'] or '':<14} {row['name']}{also}")


@cli.group()
def facts() -> None:
    """Facts: list them."""


@facts.command("list")
@click.option("--document", help="Only facts from this document (its id, title, or file name).")
@click.option("--trait", help="Only facts with this trait (its name, such as liability_cap).")
@click.option("--status", default="current", show_default=True,
              help="current, superseded, ended, corrected, contradicted, retracted, or all.")
@click.option("--limit", default=50, show_default=True, help="0 lists every fact.")
@click.option("--json", "as_json", is_flag=True)
@_data_dir_option
def facts_list(document: str | None, trait: str | None, status: str, limit: int, as_json: bool,
               data_dir: Path | None) -> None:
    """Facts in the order they were added, with their ids, traits, and documents."""
    app = _app_for(data_dir)
    sql = ("select f.id, f.text, f.status, f.traits, d.title, d.uri from facts f "
           "left join documents d on d.id = f.document_id where 1 = 1")
    params: list[Any] = []
    if status != "all":
        sql += " and f.status = ?"
        params.append(status)
    if document:
        sql += " and (d.id = ? or d.title = ? or d.uri = ? or d.uri like ?)"
        params += [document, document, document, f"%/{document}"]
    if trait:
        sql += " and exists (select 1 from json_each(f.traits) t where t.value = ?)"
        params.append(trait)
    sql += " order by f.created_at, f.rowid"
    if limit:
        sql += f" limit {int(limit)}"
    rows = app.store.query(sql, params)
    if as_json:
        return _echo_json([{"id": r["id"], "text": r["text"], "status": r["status"],
                            "traits": json.loads(r["traits"] or "[]"), "document": r["title"] or r["uri"]}
                           for r in rows])
    for row in rows:
        traits = json.loads(row["traits"] or "[]")
        tag = f" [{', '.join(traits)}]" if traits else ""
        state = "" if status == "current" else f" ({row['status']})"
        click.echo(f"{row['id']}  {row['text']}{tag}{state}")
    if not rows:
        click.echo("no facts match")


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


# -- structured documents ---------------------------------------------------------------------------------


@cli.group()
def struct() -> None:
    """Structured files: inspect one, write its parser class, and dry-run the parser."""


def _structured_classes(project: Any) -> list[Any]:
    from .structured import StructuredDocument

    return [k for k in project.documents if issubclass(k, StructuredDocument)]


def _optional_project() -> Any:
    try:
        project = load()
    except FileNotFoundError:
        return None
    load_keys(project.root)
    return project


@struct.command("inspect")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--json", "as_json", is_flag=True)
def struct_inspect(file: Path, as_json: bool) -> None:
    """Columns, types, sample values, guessed roles, a starting parser class, and which class matches the file."""
    from .structured import inspect_rows, read_rows, starter_class

    rows = read_rows(file.read_text(errors="replace"))
    columns = inspect_rows(rows)
    project = _optional_project()
    matches = []
    if project is not None:
        header = [c["column"] for c in columns]
        for klass in _structured_classes(project):
            missing = sorted(klass.required_columns() - set(header))
            matches.append({"class": klass.__name__, "matches": not missing, "missing": missing})
    if as_json:
        _echo_json({"rows": len(rows), "columns": columns, "classes": matches})
        return
    click.echo(f"{file}: {len(rows)} rows, {len(columns)} columns")
    for c in columns:
        click.echo(f"  {c['column']:<24} {c['type']:<7} {c['filled']:>6}/{c['rows']:<6} {c['distinct']:>6} distinct  "
                   f"{' | '.join(v[:30] for v in c['samples'])}")
    for m in matches:
        state = "matches the header" if m["matches"] else f"missing {', '.join(m['missing'])}"
        click.echo(f"class {m['class']}: {state}")
    click.echo("\nA starting parser class (guessed by rules; fix the entity classes and templates):\n")
    click.echo(starter_class(_class_name(file), columns))


def _class_name(file: Path) -> str:
    return "".join(part.capitalize() for part in re.split(r"[^A-Za-z0-9]+", file.stem) if part) or "Rows"


@struct.command("parser")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--name", help="Class name (defaults to one made from the file name).")
@click.option("--prompt", "prompt_only", is_flag=True, help="Print the prompt and inspection; call no model.")
@click.option("--out", type=click.Path(dir_okay=False, path_type=Path),
              help="File to add the class to (defaults to the package's documents.py).")
def struct_parser(file: Path, name: str | None, prompt_only: bool, out: Path | None) -> None:
    """Have a model write the parser class for a file, or print the prompt for your own coding agent."""
    from .entity import Entity
    from .structured import _cell, inspect_rows, read_rows, starter_class
    from .templates import builtin, render

    project = _optional_project()
    rows = read_rows(file.read_text(errors="replace"))
    columns = inspect_rows(rows)
    name = name or _class_name(file)
    entities = []
    for klass in (project.entities if project else []):
        props = ", ".join(f"{k}: {getattr(v, '__name__', v)}" for k, v in klass.typed_props().items())
        entities.append({"name": klass.__name__, "doc": klass.description(), "props": props,
                         "keys": ", ".join(klass.unique_keys)})
    sample = [json.dumps({k: _cell(v)[:120] for k, v in r.values.items()}) for r in rows[:15]]
    prompt = render(builtin("struct_parser.md.j2"), name=name, entities=entities, file=file.name, rows=len(rows),
                    columns=columns, sample=sample, starter=starter_class(name, columns),
                    package=project.package if project else "your_package")
    if prompt_only:
        click.echo(prompt)
        return
    if project is None:
        raise click.ClickException("not inside a Factoid project; use --prompt to print the prompt")
    app = project.app()
    code = app.client.generate(prompt, step="parser", max_tokens=4000).strip()
    if code.startswith("```"):
        code = code.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    target = out or _package_dir(project) / "documents.py"
    existing = target.read_text() if target.exists() else ""
    target.write_text(existing + ("\n\n" if existing.strip() else "") + code + "\n")
    app.close()
    click.echo(f"added {name} to {target}")
    click.echo(f"Next: factoid struct try {file}")


def _package_dir(project: Any) -> Path:
    for base in (project.root / "src", project.root):
        if (base / project.package).is_dir():
            return base / project.package
    return project.root / project.package


@struct.command("try")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--rows", "limit", default=20, show_default=True)
@click.option("--as", "as_class", help="Structured class to use, instead of matching the header.")
def struct_try(file: Path, limit: int, as_class: str | None) -> None:
    """Dry-run a parser on the first rows: the sentences, their citations, and links. Writes nothing and calls no
    model; text cells are listed, and extracted at ingest."""
    from .structured import Text

    project, app = _project(in_memory=True)
    text = file.read_text(errors="replace")
    classes = _structured_classes(project)
    if as_class:
        klass = next((k for k in classes if k.__name__ == as_class), None)
        if klass is None:
            raise click.ClickException(f"no structured class {as_class}; known: "
                                       f"{', '.join(k.__name__ for k in classes) or 'none'}")
    else:
        from .structured import header_of

        header = header_of(text) or []
        matched = [k for k in classes if k.matches_header(header)]
        if not matched:
            raise click.ClickException("no structured class matches this file's header; write one with "
                                       "`factoid struct parser`, or pass --as")
        klass = max(matched, key=lambda k: len(k.columns))
    document = klass(text, uri=str(file), title=file.stem)
    rows = document.read()
    header = {c for r in rows for c in r.values}
    unmapped = sorted(header - klass.required_columns())
    missing = sorted(klass.required_columns() - header)
    click.echo(f"{file}: {klass.__name__}, {len(rows)} rows; showing {min(limit, len(rows))}")
    if unmapped:
        click.echo(f"warning: columns not in the map: {', '.join(unmapped)}")
    if missing:
        click.echo(f"warning: mapped columns not in the file: {', '.join(missing)}")
    for row in rows[:limit]:
        row.entities = document.identify(row)
        click.echo(f"row {row.n} (key {document.row_key(row)}):")
        for column, entity_id in row.entities.items():
            entity = app.load_entity(entity_id)
            click.echo(f"  {column} -> {type(entity).__name__} {entity.name!r}" if entity else f"  {column} -> ?")
        for fact in document.row_facts(row):
            q = fact.quotes[0]
            click.echo(f"  + {fact.text}  [{file.name}, row {q.passage_n}, {q.section}]")
        for column, role in klass.columns.items():
            if isinstance(role, Text) and str(row.values.get(column) or "").strip():
                click.echo(f"  ~ {column}: text, extracted at ingest ({len(str(row.values[column]))} characters)")
    app.close()


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


TURBOPUFFER = {"env": "TURBOPUFFER_API_KEY", "url": "https://turbopuffer.com/dashboard",
               "for": "search, only when settings.py sets search = Turbopuffer(...)"}
KEY_CHOICES = sorted([*PROVIDERS, "turbopuffer"])


def _key_env(provider: str) -> str:
    return TURBOPUFFER["env"] if provider == "turbopuffer" else PROVIDERS[provider].key_env


def _key_status(provider: str) -> str:
    """Whether a provider's key is set, and where it comes from."""
    env = _key_env(provider)
    if not os.environ.get(env, "").strip():
        base = f"{provider.upper()}_BASE_URL"
        return f"not needed ({base} is set)" if os.environ.get(base, "").strip() else "not set"
    source = KEY_SOURCES.get(env)
    value = os.environ[env].strip()
    stored = {}
    if source is not None and source.is_file():
        for line in source.read_text().splitlines():
            name, _, raw = line.partition("=")
            stored[name.strip()] = raw.strip().strip("'\"")
    if stored.get(env) != value:
        return "set (environment variable)"
    home = Path.home()
    shown = f"~/{source.relative_to(home)}" if source.is_relative_to(home) else str(source)
    return f"set ({shown})"


def _needed_keys(app: Any) -> dict[str, list[str]]:
    """The providers a project's settings call, and the workloads each one serves."""
    needed: dict[str, list[str]] = {}
    for workload, model in app.client.models.items():
        if model is not None and model.provider_name in PROVIDERS:
            needed.setdefault(model.provider_name, []).append(workload)
    if type(app.index).__name__ == "Turbopuffer":
        needed.setdefault("turbopuffer", []).append("search")
    return needed


def _about_key(provider: str) -> list[str]:
    """What a provider's key is for and where to get one, as lines to print before the prompt."""
    if provider == "turbopuffer":
        return [f"turbopuffer: {TURBOPUFFER['for']}.", f"  Get a key: {TURBOPUFFER['url']}"]
    p = PROVIDERS[provider]
    lines = [f"{provider}: can serve {', '.join(p.kinds)}.", f"  Get a key: {p.key_url}"]
    if p.access:
        lines.append(f"  {p.access}.")
    if provider == "typesafe":
        lines.append("  No TypeSafe access? OpenAI (openai/gpt-6-luna) also serves choose; `factoid init --models "
                     "openai` sets a project up with OpenAI alone. Fireworks' Rune is experimental.")
    return lines


def _store_key(provider: str, value: str, root: Path | None) -> None:
    problem = check_key(provider, value)
    if problem and not click.confirm(f"{problem}. Store it anyway?", default=False):
        raise click.ClickException("key not stored")
    env = _key_env(provider)
    path = keys_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [ln for ln in (path.read_text().splitlines() if path.exists() else []) if not ln.startswith(f"{env}=")]
    lines.append(f"{env}={value}")
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o600)
    os.environ[env] = value
    KEY_SOURCES[env] = path
    click.echo(f"stored {env} in {path}")


@cli.group()
def keys() -> None:
    """Provider keys: which ones your models need, where to get them, and where they are stored."""


@keys.command("set")
@click.argument("provider", required=False, type=click.Choice(KEY_CHOICES))
@click.option("--project", "for_project", is_flag=True, help="Store the key for the current project only.")
def keys_set(provider: str | None, for_project: bool) -> None:
    """Store a provider key in ~/.factoid/.env (or the project's .factoid/.env).

    With no PROVIDER, it asks for each key the project's models need (or the default models, outside a project)
    and says where to get each one. Press Enter to skip a key.
    """
    root = find_root() if for_project else None
    if for_project and root is None:
        raise click.ClickException("not inside a Factoid project")
    if provider:
        for line in _about_key(provider):
            click.echo(line)
        value = click.prompt(_key_env(provider), hide_input=True).strip()
        _store_key(provider, value, root)
        return
    app = _project_or_defaults()
    needed = _needed_keys(app)
    where = "This project's models" if find_root() is not None else "The default models"
    click.echo(f"{where} need these keys:")
    for name, workloads in needed.items():
        click.echo(f"  {name:<12} {_key_env(name):<22} {', '.join(workloads):<24} {_key_status(name)}")
    click.echo("")
    missing = [name for name in needed if _key_status(name) == "not set"]
    if not missing:
        click.echo("All set. `factoid keys set <provider>` replaces one; `factoid doctor` checks them.")
        return
    click.echo("For each missing key, paste it, or press Enter to skip.")
    for name in missing:
        click.echo("")
        for line in _about_key(name):
            click.echo(line)
        value = click.prompt(_key_env(name), default="", show_default=False, hide_input=True).strip()
        if not value:
            click.echo(f"skipped {name}")
            continue
        _store_key(name, value, root)
    click.echo("\nNext: factoid doctor")


@keys.command("list")
def keys_list() -> None:
    """Every provider: whether its key is set, where it comes from, what uses it, and where to get one."""
    app = _project_or_defaults()
    needed = _needed_keys(app)
    click.echo(f"{'provider':<12} {'variable':<22} {'status':<42} {'used by':<24} get a key")
    for name in KEY_CHOICES:
        url = TURBOPUFFER["url"] if name == "turbopuffer" else PROVIDERS[name].key_url
        used = ", ".join(needed.get(name, [])) or "-"
        click.echo(f"{name:<12} {_key_env(name):<22} {_key_status(name):<42} {used:<24} {url}")


@cli.command()
def models() -> None:
    """Each workload, its model, and whether its key is set."""
    app = _project_or_defaults()
    click.echo(f"{'workload':<10} {'model':<34} key")
    steps = [s for s in GENERATION_STEPS if s in app.client.models]
    for workload in ("choose", "generate", *steps, "embed", "rerank"):
        model = app.client.models.get(workload)
        if model is None:
            click.echo(f"{workload:<10} {'(none)':<34} -")
            continue
        provider = PROVIDERS.get(model.provider_name)
        if provider is None:
            status = f"unknown provider {model.provider_name!r}"
        elif provider.api_key():
            status = _key_status(provider.name)
        elif provider.ready():
            status = f"no key; calls {provider.base_url()} ({provider.base_url_env})"
        else:
            status = f"not set (`factoid keys set {provider.name}`)"
        click.echo(f"{workload:<10} {model.name:<34} {status}")
    for problem in check_models(app.client.models):
        click.echo(f"problem: {problem}")


@cli.command()
def doctor() -> None:
    """Make one small call per workload and report what works."""
    from .judge import Noul

    app = _project_or_defaults()
    app.client.replay = False
    problems = check_models(app.client.models)
    for problem in problems:
        click.echo(f"settings   FAILED: {problem}")
    checks = {
        "choose": lambda: app.client.ask({"text": "Factoid doctor."}, {"ok": Noul("Is this a test?")}),
        "generate": lambda: app.client.generate("Answer with the word ok."),
        "embed": lambda: app.client.embed(["ok"]),
    }
    if app.client.models.get("rerank"):
        checks["rerank"] = lambda: app.client.rerank("ok", ["ok", "no"])
    failed = bool(problems)
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
@click.option("--vary", multiple=True, help="Run each value of a setting, such as fact_evals=none,decision_floors.")
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
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")  # local time, so a run's folder sorts and reads as its day
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
        older = int(total.get("older_hits", 0))
        if older:
            click.echo(f"    ({older} replayed answers were saved by a different version of Factoid)")
        for key, value in _flatten(result.metrics).items():
            click.echo(f"    {key:<44} {value}")
    replayed = sum(int(r.usage["total"]["cache_hits"]) for r in results)
    if replayed and not fresh:
        click.echo(f"\n{replayed} calls were replayed from .factoid/calls.db: identical requests reuse saved answers, "
                   f"which makes a rerun free and repeatable. --fresh calls the models again.")
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
