"""
SOP loader: reads all YAML files from the SOPs directory,
validates each against the schema, and returns the list.

Raises clear errors naming the offending file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from app import config
from app.sops.schema import SOPDefinition


def load_sops(sops_dir: Optional[Path] = None) -> list[SOPDefinition]:
    """
    Load and validate all SOP YAML files from the given directory.

    Args:
        sops_dir: Path to the SOPs directory. Defaults to config.SOPS_DIR.

    Returns:
        List of validated SOPDefinition objects.

    Raises:
        ValueError: If any SOP file is invalid (names the file and error).
        FileNotFoundError: If the SOPs directory doesn't exist.
    """
    if sops_dir is None:
        sops_dir = config.SOPS_DIR

    if not sops_dir.exists():
        raise FileNotFoundError(f"SOPs directory not found: {sops_dir}")

    sops: list[SOPDefinition] = []
    seen_ids: set[str] = set()
    errors: list[str] = []

    yaml_files = sorted(sops_dir.glob("*.yaml"))

    if not yaml_files:
        return sops

    for filepath in yaml_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)

            if raw is None:
                errors.append(f"{filepath.name}: File is empty or not valid YAML.")
                continue

            sop = SOPDefinition(**raw)

            # Check for duplicate IDs
            if sop.id in seen_ids:
                errors.append(
                    f"{filepath.name}: Duplicate SOP id '{sop.id}' "
                    f"(already loaded from another file)."
                )
                continue

            seen_ids.add(sop.id)
            sops.append(sop)

        except yaml.YAMLError as exc:
            errors.append(f"{filepath.name}: YAML parse error: {exc}")
        except ValidationError as exc:
            errors.append(f"{filepath.name}: Validation error:\n{exc}")
        except Exception as exc:
            errors.append(f"{filepath.name}: Unexpected error: {type(exc).__name__}: {exc}")

    if errors:
        raise ValueError(
            f"SOP loading failed with {len(errors)} error(s):\n\n"
            + "\n\n".join(errors)
        )

    return sops
