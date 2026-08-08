from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class ProjectRegistryError(ValueError):
    """Raised when a project is not part of the suite allowlist."""


@dataclass(frozen=True)
class ProjectLocation:
    project_name: str
    brand: str
    directory_name: str

    @property
    def relative_root(self) -> Path:
        return Path(self.brand) / self.directory_name

    @property
    def archive_root(self) -> str:
        return self.relative_root.as_posix()

    @property
    def runtime_root(self) -> str:
        return f"/suite/{self.archive_root}"

    @property
    def repository_root(self) -> str:
        return f"SBM-SUITE/{self.archive_root}"


PROJECT_ALLOWLIST = {
    "dp-api": ProjectLocation("dp-api", "dp", "DP-API"),
    "sbm-api": ProjectLocation("sbm-api", "sbm", "SBM-API"),
    "sbm-db": ProjectLocation("sbm-db", "sbm", "SBM-DB"),
    "sbm-manager": ProjectLocation("sbm-manager", "sbm", "SBM-MANAGER"),
    "sbm-ai-assistant": ProjectLocation(
        "sbm-ai-assistant",
        "sbm",
        "sbm-ai-assistant",
    ),
}


def get_project_location(project_name: str) -> ProjectLocation:
    normalized = project_name.strip().casefold()
    location = PROJECT_ALLOWLIST.get(normalized)
    if location is None:
        raise ProjectRegistryError(
            "project_name must be one of: "
            + ", ".join(sorted(PROJECT_ALLOWLIST))
        )
    return location


def canonical_runtime_project_path(project_name: str) -> str:
    """Return the canonical path used by the mounted runtime contract."""

    return get_project_location(project_name).runtime_root


def runtime_to_repository_path(runtime_path: str) -> str:
    """Convert a canonical ``/suite`` path to repository-relative form."""

    path = PurePosixPath(runtime_path)
    if (
        not runtime_path.startswith("/suite/")
        or str(path) != runtime_path
        or ".." in path.parts
    ):
        raise ProjectRegistryError(
            "runtime path must be a normalized absolute path below /suite"
        )
    return PurePosixPath("SBM-SUITE", *path.parts[2:]).as_posix()


def repository_to_runtime_path(repository_path: str) -> str:
    """Convert an ``SBM-SUITE/...`` target to mounted runtime form."""

    path = PurePosixPath(repository_path)
    if (
        path.is_absolute()
        or not repository_path.startswith("SBM-SUITE/")
        or str(path) != repository_path
        or ".." in path.parts
    ):
        raise ProjectRegistryError(
            "repository path must be normalized and relative to SBM-SUITE"
        )
    return PurePosixPath("/suite", *path.parts[1:]).as_posix()


def resolve_allowed_project_root(
    project_name: str,
    suite_root_or_project_root: Path,
) -> tuple[ProjectLocation, Path]:
    """Resolve a project without accepting an arbitrary request path.

    ``suite_root_or_project_root`` may be the suite mount (``/suite``) or the
    already selected allowlisted project root. Supporting both forms keeps the
    service easy to exercise in an isolated test root while the resulting path
    is always derived from the registry.
    """

    location = get_project_location(project_name)
    configured = suite_root_or_project_root.expanduser()
    if not configured.is_absolute() or ".." in configured.parts:
        raise ProjectRegistryError("project root must be an absolute safe path")

    relative_parts = location.relative_root.parts
    if configured.parts[-len(relative_parts) :] == relative_parts:
        candidate = configured
    else:
        candidate = configured / location.relative_root

    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ProjectRegistryError(
            f"allowlisted project root does not exist: {location.archive_root}"
        ) from exc

    if not resolved.is_dir():
        raise ProjectRegistryError(
            f"allowlisted project root is not a directory: {location.archive_root}"
        )

    return location, resolved
