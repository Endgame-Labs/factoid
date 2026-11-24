from factoid import Model, Settings


class Project(Settings):
    """The default models: Jev decides, GLM 5.3 Flash writes and answers, and Qwen3 embeds."""

    models = {
        "choose": Model("typesafe/jev-1.14.0"),  # classify, evaluate facts, assess, link, and resolve
        "generate": Model("fireworks/glm-5p3-flash", reasoning_effort="low"),  # extract and repair
        "embed": Model("fireworks/qwen3-embedding-8b"),
    }
