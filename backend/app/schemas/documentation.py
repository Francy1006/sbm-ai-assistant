from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.contexts.models import RetrievedContextChunk


class DocumentationExportRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        arbitrary_types_allowed=True,
    )

    project_name: str = Field(min_length=1)
    workflow: Literal["documentation-deploy"]
    project_root: str = Field(min_length=1)
    documentation_root: str = Field(min_length=1)
    format_context_path: str = Field(min_length=1)
    system_prompt_path: str = Field(min_length=1)
    output_directory: str = Field(min_length=1)
    change_summary: Optional[str] = None
    changed_files: Optional[List[str]] = None
    git_diff: Optional[str] = None
    qa_results: Optional[str] = None
    retrieved_context_chunks: Optional[List[RetrievedContextChunk]] = None

    @field_validator(
        "project_root",
        "documentation_root",
        "format_context_path",
        "system_prompt_path",
        "output_directory",
    )
    @classmethod
    def validate_required_path(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError("path value must not be empty")

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

    @field_validator("retrieved_context_chunks")
    @classmethod
    def validate_retrieved_context_chunks(
        cls,
        value: Optional[List[RetrievedContextChunk]],
    ) -> Optional[List[RetrievedContextChunk]]:
        if value is None:
            return None

        point_ids = [chunk.point_id for chunk in value]

        if len(point_ids) != len(set(point_ids)):
            raise ValueError(
                "retrieved_context_chunks must not "
                "contain duplicate point_id values"
            )

        return value


class DocumentationExportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["completed"]
    project_name: str = Field(min_length=1)
    workflow: Literal["documentation-deploy"]
    documentation_zip_path: str = Field(min_length=1)
    indexed_source_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    collection_name: Literal["sbm_documentation"]
    errors: List[str] = Field(default_factory=list)


class DocumentationUpgradeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_name: str = Field(min_length=1)
    workflow: Literal["documentation-upgrade"]
    updated_files: List[str]
    backup_directory: str = Field(min_length=1)
    commit_message_file: str
    executive_readme_file: str
    input_cleaned: bool
    errors: List[str] = Field(default_factory=list)

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
