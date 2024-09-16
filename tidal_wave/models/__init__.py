def replace_illegal_characters(input_str: str) -> str | None:
    """Replace troublesome characters in album title, version.

    Troublesome characters either crash the program on Windows or cause
    difficulties with file names on all systems.
    """
    if input_str is None:
        return input_str
    return (
        input_str.replace("/", "_")
        .replace("|", "_")
        .replace(":", " -")
        .replace('"', "")
        .replace(">", "")
        .replace("<", "")
        .replace("/", "")
        .replace("\\", "")
        .replace("?", "")
        .replace(" ?", "")
        .replace("? ", "")
        .replace("*", "")
        .replace("\0", "")  # ASCII null character
    )