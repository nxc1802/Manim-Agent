import re
from typing import Any


def parse_storyboard_to_scenes(text: str) -> list[dict[str, Any]]:
    """
    Split Director's storyboard Markdown into individual scenes.
    Expected format for each scene:
    ## Scene X: [Title]
    Visual Intent: ...
    Narration: ...
    """
    # Regex to find "## Scene X: ..." or similar headers
    # We look for lines starting with ## and containing "Scene"
    scene_pattern = re.compile(r"^##\s+Scene\s+\d+:?\s*(.*)$", re.MULTILINE | re.IGNORECASE)

    matches = list(scene_pattern.finditer(text))
    if not matches:
        # Fallback: if no specific "Scene" headers, try any ## header
        scene_pattern = re.compile(r"^##\s+(.*)$", re.MULTILINE)
        matches = list(scene_pattern.finditer(text))

    scenes = []
    for i in range(len(matches)):
        start_pos = matches[i].start()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        matches[i].group(0)
        title = matches[i].group(1).strip()
        content = text[start_pos:end_pos].strip()

        scenes.append(
            {"title": title or f"Scene {i + 1}", "content": content, "scene_order": i + 1}
        )

    return scenes
