from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class ContextExportRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    project_name: str = Field(min_length=1)
    workflow: Literal["context-deploy"]
    lifecycle_phase: Literal[
        "planning-activation",
        "implementation-progress",
        "implementation-closure",
    ]
    objective_id: str = Field(min_length=1)
    project_root: str = Field(min_length=1)
    source_context_root: str = Field(min_length=1)
    format_context_path: str = Field(min_length=1)
    output_directory: str = Field(min_length=1)
    change_summary: Optional[str] = None
    changed_files: Optional[List[str]] = None
    git_diff: Optional[str] = None
    qa_results: Optional[str] = None
    user_prompt: Optional[str] = None

    @field_validator(
        "project_root",
        "source_context_root",
        "format_context_path",
        "output_directory",
    )
    @classmethod
    def validate_required_path(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError(
                "path value must not be empty"
            )

        return value

    @field_validator("changed_files")
    @classmethod
    def validate_changed_files(
        cls,
        value: Optional[List[str]],
    ) -> Optional[List[str]]:
        if value is None:
            return None

        normalized = [
            item.strip()
            for item in value
            if item and item.strip()
        ]

        if len(normalized) != len(set(normalized)):
            raise ValueError(
                "changed_files must not contain duplicates"
            )

        return normalized

    @model_validator(mode="after")
    def validate_planning_user_prompt(self):
        if (
            self.lifecycle_phase == "planning-activation"
            and not self.user_prompt
        ):
            raise ValueError(
                "user_prompt is required for planning-activation"
            )
        return self


class ContextExportResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    status: Literal["completed"]
    project_name: str = Field(min_length=1)
    workflow: Literal["context-deploy"]
    lifecycle_phase: Literal[
        "planning-activation",
        "implementation-progress",
        "implementation-closure",
    ]
    objective_id: str = Field(min_length=1)
    context_zip_path: str = Field(min_length=1)
    indexed_source_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    collection_name: Literal["sbm_contexts"]
    errors: List[str] = Field(
        default_factory=list
    )


class ContextUpgradeResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    project_name: str = Field(min_length=1)
    workflow: Literal["context-upgrade"]
    updated_files: List[str]
    backup_directory: str = Field(min_length=1)
    commit_message_file: str
    executive_readme_file: str
    input_cleaned: bool
    errors: List[str] = Field(
        default_factory=list
    )

    @field_validator("updated_files")
    @classmethod
    def validate_updated_files(
        cls,
        value: List[str],
    ) -> List[str]:
        normalized = [
            item.strip()
            for item in value
            if item and item.strip()
        ]

        if not normalized:
            raise ValueError(
                "updated_files must contain at least one file"
            )

        if len(normalized) != len(set(normalized)):
            raise ValueError(
                "updated_files must not contain duplicates"
            )

        return normalized


class ContextContractResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str = Field(min_length=64, max_length=64)
    supported_patch_paths: List[str]
    lifecycle_phases: List[str]
    canonical_projects: Dict[str, str]
