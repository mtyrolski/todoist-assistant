"""Shared project-color resolution for dashboard visualizations."""

from collections.abc import Mapping

DEFAULT_PROJECT_COLOR = "#808080"


def resolve_project_color(
    project_name: object,
    project_colors: Mapping[str, str],
    *,
    fallback: str = DEFAULT_PROJECT_COLOR,
) -> str:
    """Resolve a stable color even when project-name casing differs."""

    normalized_name = str(project_name).strip()
    exact_color = project_colors.get(normalized_name)
    if exact_color and str(exact_color).strip():
        return str(exact_color).strip()

    folded_name = normalized_name.casefold()
    for candidate_name, candidate_color in project_colors.items():
        color = str(candidate_color).strip()
        if str(candidate_name).strip().casefold() == folded_name and color:
            return color
    return fallback
