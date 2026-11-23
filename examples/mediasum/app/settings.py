from factoid import Model, Settings


class Project(Settings):
    """Models for the ISC-RAG rerun. Embeddings match the paper (nomic-embed-text-v1.5)."""

    models = {
        "choose": Model("typesafe/jev-1.14.0"),
        "generate": Model("fireworks/glm-5p3-flash", reasoning_effort="low"),  # extraction and repair
        "embed": Model("fireworks/nomic-ai/nomic-embed-text-v1.5"),
    }
    concurrency = 16
