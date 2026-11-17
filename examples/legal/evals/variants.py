"""Variants for `factoid eval --vary`. `--vary models=@evals.variants:RUNE` runs the suites with Rune for `choose`."""

from legal.settings import Project

from factoid import Model

RUNE = {**Project.models, "choose": Model("fireworks/rune")}
