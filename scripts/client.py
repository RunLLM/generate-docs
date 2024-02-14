import requests

from enum import Enum
from datetime import datetime
from pydantic import BaseModel
from typing import List, Dict, Any
from urllib.parse import urlencode


class AutodocOutputMode(Enum):
    # The output will be the original source code, augmented with inline function docstrings.
    INLINE = "inline"

    # The output willl be an OpenAPI specification, generated from the source code,
    # which is assumed to describe a Restful API.
    OPENAPI = "openapi"


class RepositoryResponse(BaseModel):
    id: int
    owner_id: str
    # Format: owner/repo (eg. RunLLM/commons)
    name: str
    created_at: datetime
    updated_at: datetime


class RegisterAutodocRunResponse(BaseModel):
    run_id: int

    # These are all the supported paths we can generate documentation for.
    file_path_to_language: Dict[str, str]


class GenerateAutodocResponse(BaseModel):
    documented_content: str
    tokens_used: int


class ExplainAutodocResponse(BaseModel):
    explanation: str
    tokens_used: int


class RunLLMClient:
    def __init__(self, server_address: str, api_key: str):
        self.server_address = server_address
        self.api_key = api_key

    def _check_for_error(self, resp: Any) -> None:
        if resp.status_code != 200:
            raise Exception(f"Request failed with status code {resp.status_code}. Response: {resp.text}")

    def _get_default_headers(self) -> Dict[str, str]:
        return {
            'Content-Type': 'application/json',
            "x-api-key": self.api_key,
        }

    def list_repositories(self) -> List[RepositoryResponse]:
        resp = requests.get(
            self.server_address + "/api/repositories",
            headers=self._get_default_headers(),
            )
        self._check_for_error(resp)
        return [
            RepositoryResponse(
                **repo_dict
            ) for repo_dict in resp.json()
        ]

    def create_repository(self, name: str) -> RepositoryResponse:
        resp = requests.post(
            self.server_address + "/api/repository",
            headers=self._get_default_headers(),
            json={"name": name},
            )
        self._check_for_error(resp)
        return RepositoryResponse(**resp.json())

    def create_autodoc_run(self, repo_id: int, gh_action_url: str, changed_file_paths: List[str]) -> RegisterAutodocRunResponse:
        resp = requests.post(
            self.server_address + "/api/autodoc",
            headers=self._get_default_headers(),
            json={
                "repo_id": repo_id,
                "gh_action_url": gh_action_url,
                "file_paths": changed_file_paths,
            }
        )
        self._check_for_error(resp)
        return RegisterAutodocRunResponse(**resp.json())

    def generate_inline_documentation(self, run_id: int, file_path: str, file_content: str, language: str, diff: str) -> GenerateAutodocResponse:
        query_params = urlencode({'file_path': file_path})
        resp = requests.post(
            self.server_address + f"/api/autodoc/{run_id}?{query_params}",
            headers=self._get_default_headers(),
            json={
                "output_mode": AutodocOutputMode.INLINE.value,
                "file_content": file_content,
                "language": language,
                "changes": diff,
            }
        )
        self._check_for_error(resp)
        return GenerateAutodocResponse(**resp.json())

    def generate_openapi_spec(self, run_id: int, file_path: str, original_openapi_spec: str, language: str) -> GenerateAutodocResponse:
        query_params = urlencode({'file_path': file_path})
        resp = requests.post(
            self.server_address + f"/api/autodoc/{run_id}?{query_params}",
            headers=self._get_default_headers(),
            json={
                "output_mode": AutodocOutputMode.OPENAPI.value,
                "file_content": original_openapi_spec,
                "language": language,
            }
        )
        self._check_for_error(resp)
        return GenerateAutodocResponse(**resp.json())

    def generate_explanation(self, run_id: int, mode: AutodocOutputMode, diff: str) -> ExplainAutodocResponse:
        resp = requests.post(
            self.server_address + f"/api/autodoc/{run_id}/explanation",
            headers=self._get_default_headers(),
            json={
                "output_mode": mode.value,
                "changes": diff,
            }
        )
        self._check_for_error(resp)
        return ExplainAutodocResponse(**resp.json())

    def mark_completed(self, run_id: int, pull_request_url: str) -> None:
        resp = requests.put(
            self.server_address + f"/api/autodoc/{run_id}",
            headers=self._get_default_headers(),
            json={
                "status": "Succeeded",
                "pull_request_url": pull_request_url,
            }
        )
        self._check_for_error(resp)

    def mark_failed(self, run_id: int, error: str) -> None:
        resp = requests.put(
            self.server_address + f"/api/autodoc/{run_id}",
            headers=self._get_default_headers(),
            json={
                "status": "Failed",
                "error": error,
            }
        )
        self._check_for_error(resp)
