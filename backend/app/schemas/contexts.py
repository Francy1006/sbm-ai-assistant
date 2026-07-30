from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ContextExportRequest(BaseModel):
    project_name: str = Field(min_length=1)
    workflow: Literal["context-deploy"]
    project_root: str = Field(min_length=1)
    source_context_root: str = Field(min_length=1)
    output_directory: str = Field(min_length=1)
    change_summary: Optional[str] = None
    changed_files: Optional[list[str]] = None
    git_diff: Optional[str] = None
    qa_results: Optional[str] = None


class ContextExportResponse(BaseModel):
    status: Literal["completed"]
    project_name: str
    workflow: Literal["context-deploy"]
    context_zip_path: str
    indexed_source_count: int
    chunk_count: int
    collection_name: Literal["sbm_contexts"]
    errors: list[str]


class ContextUpgradeResponse(BaseModel):
    project_name: str
    workflow: Literal["context-upgrade"]
    updated_files: list[str]
    backup_directory: str
    commit_message_file: str
    executive_readme_file: str
    input_cleaned: bool
    errors: list[str]
