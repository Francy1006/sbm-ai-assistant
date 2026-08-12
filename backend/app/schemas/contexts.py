from __future__ import annotations

from datetime import date
import hashlib
import re
from typing import Annotated, Dict, List, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


_OBJECTIVE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_BRANCH_PATTERN = re.compile(
    r"^(FEATURE|BUGFIX|HOTFIX)-[a-z0-9]+(?:-[a-z0-9]+){0,3}$"
)


class ContextObjective(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    objective_id: str = Field(min_length=1)
    objective: Optional[str] = None
    status: Optional[Literal["active", "pending"]] = None
    priority: Optional[int] = Field(default=None, ge=0, le=5)
    target_date: Optional[str] = None
    branch: Optional[str] = None

    @field_validator("objective_id")
    @classmethod
    def validate_objective_id(cls, value: str) -> str:
        if not _OBJECTIVE_ID_PATTERN.fullmatch(value):
            raise ValueError("objective_id contains invalid characters")
        return value

    @field_validator("objective")
    @classmethod
    def validate_objective(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("objective must not be empty")
        return value

    @field_validator("target_date")
    @classmethod
    def validate_target_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if value == "N/A":
            return value
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                "target_date must be YYYY-MM-DD or N/A"
            ) from exc
        return value

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not _BRANCH_PATTERN.fullmatch(value):
            raise ValueError(
                "branch must match FEATURE|BUGFIX|HOTFIX-<slug-max-4-words>"
            )
        return value


class ContextQADecision(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    status: Literal["passed", "failed", "not-applicable"]
    applicable: bool
    workflow_path: Literal["scripts/qa-check.sh"]
    evidence_file: Literal["qa-results.md"]
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_status_applicability(self):
        expected_applicable = self.status != "not-applicable"
        if self.applicable != expected_applicable:
            raise ValueError(
                f"qa status {self.status} requires applicable="
                f"{str(expected_applicable).lower()}"
            )
        return self


class ContextExportRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    project_name: str = Field(min_length=1)
    workflow: Literal["context-deploy"]
    lifecycle_phase: Literal[
        "planning-activation",
        "objective-activation",
        "implementation-progress",
        "implementation-closure",
    ]
    execution_mode: Literal["evidence", "user-guided"] = "evidence"
    objectives: List[ContextObjective] = Field(min_length=1)
    change_summary: Optional[str] = None
    changed_files: Optional[List[str]] = None
    git_diff: Optional[str] = None
    qa_results: Optional[
        Annotated[str, StringConstraints(strip_whitespace=False)]
    ] = None
    qa: Optional[ContextQADecision] = None
    user_prompt: Optional[str] = None

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
    def validate_objectives(self):
        has_user_prompt = bool(
            self.user_prompt and self.user_prompt.strip()
        )
        expected_execution_mode = (
            "user-guided" if has_user_prompt else "evidence"
        )
        if self.execution_mode != expected_execution_mode:
            raise ValueError(
                "execution_mode must be user-guided when user_prompt is "
                "present and evidence when user_prompt is absent"
            )

        if self.lifecycle_phase == "implementation-closure":
            if self.qa is None:
                raise ValueError(
                    "implementation-closure requires structured qa"
                )
            if self.qa.status == "failed":
                raise ValueError(
                    "implementation-closure is blocked by failed qa"
                )
            qa_results = self.qa_results or ""
            evidence_sha256 = hashlib.sha256(
                qa_results.encode("utf-8")
            ).hexdigest()
            if self.qa.evidence_sha256 != evidence_sha256:
                restored_qa_results = f"{qa_results}\n"
                restored_sha256 = hashlib.sha256(
                    restored_qa_results.encode("utf-8")
                ).hexdigest()
                if self.qa.evidence_sha256 != restored_sha256:
                    raise ValueError(
                        "qa evidence_sha256 must match qa_results"
                    )
                self.qa_results = restored_qa_results
        elif self.qa is not None:
            raise ValueError(
                "qa is allowed only for implementation-closure"
            )

        objective_ids = [
            objective.objective_id for objective in self.objectives
        ]
        if len(objective_ids) != len(set(objective_ids)):
            raise ValueError("objectives must not contain duplicate objective_id values")

        if self.lifecycle_phase in {
            "planning-activation",
            "objective-activation",
        }:
            required_fields = (
                "objective",
                "status",
                "priority",
                "target_date",
                "branch",
            )
            for index, objective in enumerate(self.objectives, start=1):
                missing = [
                    field
                    for field in required_fields
                    if getattr(objective, field) is None
                ]
                if missing:
                    lifecycle_label = (
                        "planning"
                        if self.lifecycle_phase == "planning-activation"
                        else "activation"
                    )
                    raise ValueError(
                        f"objectives[{index}] is missing required "
                        f"{lifecycle_label} fields: "
                        + ", ".join(missing)
                    )
        if self.lifecycle_phase == "objective-activation":
            if len(self.objectives) != 1:
                raise ValueError(
                    "objective-activation requires exactly one objective"
                )
            if self.objectives[0].status != "active":
                raise ValueError(
                    "objective-activation requested status must be active"
                )
        elif self.lifecycle_phase != "planning-activation" and len(
            self.objectives
        ) != 1:
            raise ValueError(
                f"{self.lifecycle_phase} currently supports exactly one objective"
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
        "objective-activation",
        "implementation-progress",
        "implementation-closure",
    ]
    execution_mode: Literal["evidence", "user-guided"]
    objectives: List[ContextObjective] = Field(min_length=1)
    context_zip_path: str = Field(min_length=1)
    upload_zip_path: str = Field(min_length=1)
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
