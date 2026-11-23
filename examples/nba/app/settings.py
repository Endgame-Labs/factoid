from factoid import Model, Settings


class Project(Settings):
    """Models for the Warriors' 2022 playoffs: the same stack as the legal app."""

    models = {
        "choose": Model("typesafe/jev-1.14.0"),  # classify, evaluate facts, assess, link, and resolve
        "generate": Model("fireworks/glm-5p3-flash", reasoning_effort="low"),  # extract and repair
        "embed": Model("fireworks/qwen3-embedding-8b"),
        "rerank": Model("fireworks/qwen3-reranker-8b"),
    }
    concurrency = 12
