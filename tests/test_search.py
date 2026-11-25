import numpy as np
import pytest

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
    with pytest.raises(TypeError):  # f90 is written before f91 fails, and the next commit saves it
        index.upsert("facts", [*rows(["f90"], "b"), {"id": "f91", "text": "t", "vector": same, "bad": object()}])
    index.delete("facts", ["f0", "f59", "f12", "missing"])
    assert searches(index) == searches(LocalIndex(path))

    other.upsert("facts", rows(["f70", "f71"], "b"))  # another connection to the same file
    assert searches(index) == searches(LocalIndex(path))

    for start in (0, 50):  # every vector again, of a new length, in two saves
        index.upsert("facts", rows([f"f{i}" for i in range(start, start + 50)], "a", dims=8))
        if start == 0:
            with pytest.raises(ValueError):  # vectors of two lengths cannot be searched
                index.nearest("facts", [0.0] * 8, 1)
    assert searches(index, dims=8) == searches(LocalIndex(path), dims=8)


def test_local_index_ranks_rows_of_one_vector_by_id_wherever_they_sit(tmp_path):
    rng = np.random.default_rng(0)
    index = LocalIndex(tmp_path / "index.db")
    tied = rng.standard_normal(16)
    query = (tied + 0.3 * rng.standard_normal(16)).tolist()  # BLAS scores some of the nine rows a bit apart
    index.nearest("tied", query, 1)
    for i in reversed(range(9)):
        index.upsert("tied", [{"id": f"t{i}", "text": "t", "vector": tied.tolist()}])
    assert index.nearest("tied", query, 3) == LocalIndex(tmp_path / "index.db").nearest("tied", query, 3) == \
        ["t0", "t1", "t2"]
    assert index.nearest("tied", query, 0) == ["t0"]


def test_local_index_searched_and_saved_from_many_threads_matches_a_fresh_load(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    index = LocalIndex(tmp_path / "index.db")
    index.nearest("facts", [1.0] * 256, 1)

    def work(seed):
        rng = np.random.default_rng(seed)
        for _ in range(300):
            if rng.random() < 0.3:
                index.upsert("facts", [{"id": f"r{rng.integers(60)}", "text": "t",
                                        "vector": rng.standard_normal(256).tolist()}])
            elif rng.random() < 0.3:
                index.delete("facts", [f"r{rng.integers(60)}"])
            else:
                index.nearest("facts", rng.standard_normal(256).tolist(), 5)

    with ThreadPoolExecutor(4) as pool:
        list(pool.map(work, range(4)))
    queries = np.random.default_rng(9).standard_normal((10, 256)).tolist()
    fresh = LocalIndex(tmp_path / "index.db")
    assert [index.nearest("facts", q, 60) for q in queries] == [fresh.nearest("facts", q, 60) for q in queries]
