from factoid import Model, Settings


class Project(Settings):
    """Models, store, and search for legal diligence."""

    models = {
        "choose": Model("typesafe/jev-1.13.0"),  # classify, evaluate facts, assess, link, and resolve
        "generate": Model("fireworks/glm-5p3-flash", reasoning_effort="low"),  # extract and repair
        "embed": Model("fireworks/qwen3-embedding-8b"),
    }
    concurrency = 12
