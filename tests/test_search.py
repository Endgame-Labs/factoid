import numpy as np

from factoid.search import LocalIndex


def test_local_index_search_after_saves_and_deletes_matches_a_fresh_load(tmp_path):
    rng = np.random.default_rng(0)
    path = tmp_path / "index.db"
    index, other = LocalIndex(path), LocalIndex(path)

    def rows(ids, tag, dims=16):
        return [{"id": i, "text": f"fact {i}", "vector": rng.standard_normal(dims).tolist(), "tag": tag} for i in ids]

    def searches(ix, dims=16):
        queries = [same, *np.random.default_rng(1).standard_normal((20, dims)).tolist()][dims != 16:]
        return [(ix.nearest("facts", q, 3), ix.nearest("facts", q, 5, filters={"tag": "b"})) for q in queries]

    same = rng.standard_normal(16).tolist()  # five rows share it, so their scores tie
    index.upsert("facts", rows([f"f{i}" for i in range(30)], "a"))
    searches(index)  # loads the vectors once; what follows keeps them
    index.upsert("facts", rows([f"f{i}" for i in range(30, 60)], "b"))
    index.upsert("facts", [{"id": f"f8{i}", "text": "same", "vector": same, "tag": ("b",)} for i in range(5)])
    index.upsert("facts", rows(["f3", "f40", "f3"], "b"))  # replaced, and named twice in one save
    index.upsert("facts", [{"id": "f7", "text": "no vector now"}])
    index.delete("facts", ["f0", "f59", "f12", "missing"])
    assert searches(index) == searches(LocalIndex(path))

    other.upsert("facts", rows(["f70", "f71"], "b"))  # another connection to the same file
    assert searches(index) == searches(LocalIndex(path))

    for start in (0, 50):  # every vector again, of a new length, in two saves
        index.upsert("facts", rows([f"f{i}" for i in range(start, start + 50)], "a", dims=8))
    assert searches(index, dims=8) == searches(LocalIndex(path), dims=8)
