"""Variants for `factoid eval --vary`. `--vary models=@evals.variants:RUNE` runs the suites with Rune for `choose`."""

from factoid import Model
from legal.settings import Project

RUNE = {**Project.models, "choose": Model("fireworks/rune")}
