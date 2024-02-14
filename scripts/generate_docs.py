import argparse
import os
import subprocess

from typing import List, Dict, Optional
from collections import defaultdict

from scripts.client import RunLLMClient, AutodocOutputMode

# Map of languages to their file extensions
language_extensions = {
    "python": [".py"],
    "javascript": [".js", ".jsx"],
    "typescript": [".ts", ".tsx"],
    # Add more languages and extensions as needed
}

COST_PER_1K_TOKEN = 0.03


# Calculate Cost
def calculate_cost(total_tokens: int) -> float:
    return (total_tokens / 1000) * COST_PER_1K_TOKEN


def _partition_diff_by_file_name(diff_lines: List[str]) -> Dict[str, str]:
    """Partition the diff into a dictionary of file paths to their individual str diffs."""
    diff_by_file: Dict[str, str] = defaultdict(str)

    # Extract the starting file path from the first line.
    lines = diff_lines
    curr_file_path: Optional[str] = None # only None before the very first iteration.
    for line in lines:
        if curr_file_path is None and not line.startswith("diff --git"):
            raise Exception("Malformed git diff file. Expected a 'diff --git' line.")

        if line.startswith("diff --git"):
            curr_file_path = line.split(" b/")[1]

        assert curr_file_path
        diff_by_file[curr_file_path] += line + "\n"

    return diff_by_file


def _get_or_create_repo_id(client: RunLLMClient) -> int:
    """Get the repo ID from the RunLLM API.

    If the repo doesn't exist for this user, we will create one for them.
    """
    repo_name = os.environ.get('GITHUB_REPO_NAME')
    assert repo_name is not None

    repos = client.list_repositories()
    for repo in repos:
        if repo.name == repo_name:
            return repo.id

    # No repo exists for this user, so we create one.
    return client.create_repository(repo_name).id


def _git_diff(cached: bool = False, file_path: Optional[str] = None) -> str:
    """Run git diff and return the output as a string."""
    cmd = ["git", "diff"]
    if cached:
        cmd.append("--cached")
    if file_path:
        cmd.append(file_path)
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise Exception(f'Failed to run git diff: {result.stderr.decode("utf-8")}')
    return result.stdout.decode("utf-8")


def _git_add(file_path: str) -> None:
    cmd = ["git", "add", file_path]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise Exception(f'Failed to run git add: {result.stderr.decode("utf-8")}')


def update_docs(
        client: RunLLMClient,
        gh_action_url: str,
        mode: AutodocOutputMode,
        diff_by_file_path: Dict[str, str],
        openapi_spec: Optional[str],
) -> int:
    """Update the documentation for the given files in the diff.

    NOTE: For OpenAPI mode, we currently expect to only be processing a single inut file right now.

    Args:
        client (RunLLMClient): The RunLLM API client.
        gh_action_url (str): The URL of the GitHub action that triggered this run.
        mode (AutodocOutputMode): The output mode to generate for.
        diff_by_file_path (Dict[str, str]): A dictionary of file paths to their individual diffs, spliced from the full diff.
        openapi_spec (str): The file path to the OpenAPI spec to generate. Only relevant if mode is AutodocOutputMode.OPENAPI.
    """
    openapi_spec_already_exists = False
    if mode is AutodocOutputMode.OPENAPI:
        openapi_spec_already_exists = os.path.exists(openapi_spec)

    repo_id = _get_or_create_repo_id(client)

    # Create an Autodoc run.
    autodoc_run = client.create_autodoc_run(repo_id, gh_action_url, list(diff_by_file_path.keys()))
    run_id = autodoc_run.run_id

    total_token_count =  0
    try:
        # Enhance documentation for each changed file.
        for file_path in diff_by_file_path.keys():
            if file_path not in autodoc_run.file_path_to_language:
                print(f"Skipping {file_path} as it is not a supported file type.")
                continue
            language = autodoc_run.file_path_to_language[file_path]

            with open(file_path, 'r') as f:
                file_content = f.read()

            if mode is AutodocOutputMode.INLINE:
                doc_resp = client.generate_inline_documentation(run_id, file_path, file_content, language, diff_by_file_path[file_path])
            else:
                assert mode is AutodocOutputMode.OPENAPI
                doc_resp = client.generate_openapi_spec(run_id, file_path, file_content, language)

            gen_token_count = doc_resp.tokens_used
            total_token_count += gen_token_count
            print(f"Tokens used to generate documentation for {file_path}: {gen_token_count}, Cost: ${calculate_cost(gen_token_count):.2f}")

            # Write the documented content back to the file for INLINE mode.
            if mode is AutodocOutputMode.INLINE:
                with open(file_path, "w") as f:
                    f.write(doc_resp.documented_content)
            else:
                assert openapi_spec
                # Write the documented content to the openapi spec file for OPENAPI mode.
                with open(openapi_spec, "w") as f:
                    f.write(doc_resp.documented_content)

        # Get the updates that were made. Note that git diff might not work in OPENAPI mode since we may be creating a new untracked file.
        # But if the spec file existed before, it must be tracked by git.
        if mode is AutodocOutputMode.INLINE or openapi_spec_already_exists:
            diff = _git_diff()
        else:
            assert mode is AutodocOutputMode.OPENAPI
            # Add the untracked file and then diff it.
            _git_add(openapi_spec)
            diff = _git_diff(cached=True, file_path=openapi_spec)

        if len(diff) == 0:
            print("No changes were made. Exiting!")
            return

        # Fetch and record the explanation.
        resp = client.generate_explanation(run_id, mode, diff)
        with open("pr-body.txt", "w") as f:
            f.write(resp.explanation)
        explanation_token_count = resp.tokens_used
        total_token_count += explanation_token_count
        print(f"Tokens used to generate explanation: {explanation_token_count}, Cost: ${calculate_cost(explanation_token_count):.2f}")

    except Exception as e:
        client.mark_failed(run_id, str(e))
        raise

    print(f"Total completion tokens: {total_token_count}, Cost: ${calculate_cost(total_token_count):.2f}")
    return run_id


# Command line argument parsing
parser = argparse.ArgumentParser(description="Generate Documentation")
parser.add_argument("--server-address", type=str, required=True, help="The address of the RunLLM server")
parser.add_argument("--api-key", type=str, required=True, help="The API key to use for the RunLLM server")
parser.add_argument("--input-api-file", type=str, default=None, help="File path to API source code to generate an OpenAPI spec for. Only relevant in OPENAPI mode.")
parser.add_argument("--output-openapi-file", type=str, default=None, help="File path to the OpenAPI spec to generate. Can exist or not. Only relevant in OPENAPI mode.")
parser.add_argument("--mode", type=str, required=True, help="The output mode to generate for ('inline' or 'openapi')")
parser.add_argument("--diffs-file", type=str, default=None, help="File path containing the git diff of changes")
args = parser.parse_args()

if __name__ == "__main__":
    """
    This script is used to generate documentation for a set of changed files.
    
    It will perform the following modifications to the filesystem:
    - For each file that has changed (supported by Autodocs), it will generate documentation and write it back to the file.
    - It will generate an explanation of the changes and write it to `pr-body.txt`.
    
    If an error occurs at any point, the Autodoc run will be terminated with non-zero exit code.
    """
    repo_name = os.environ.get('GITHUB_REPO_NAME')
    gh_action_url = os.environ.get('GH_ACTION_URL')

    if not repo_name: # format: owner/repo
        print("GITHUB_REPO_NAME environment variable must be set to run this script")
        exit(1)
    if not gh_action_url:
        print("GH_ACTION_URL environment variable must be set to run this script")
        exit(1)

    with open(args.diffs_file, 'r') as f:
        diffs_content = f.readlines()
    diffs_content = [line.strip() for line in diffs_content]
    diff_by_file_name = _partition_diff_by_file_name(diffs_content)

    mode = AutodocOutputMode(args.mode)
    if mode is AutodocOutputMode.OPENAPI:
        if not args.input_api_file or not args.output_openapi_file:
            print("Both openapi-spec-source and openapi-spec must be provided for OPENAPI mode.")
            exit(1)

        if args.input_api_file not in diff_by_file_name.keys():
            print("OpenAPI spec source file was not changed. Exiting.")
            exit(1)

        # For OpenAPI spec generation, narrow down files to process to just the source path.
        diff_by_file_name = {
            args.input_api_file: diff_by_file_name[args.input_api_file]
        }
    else:
        raise Exception("Only 'openapi' mode is currently supported!.")

    client = RunLLMClient(args.server_address, args.api_key)
    run_id = update_docs(
        client,
        gh_action_url,
        mode,
        diff_by_file_name,
        args.output_openapi_file,
    )

    # Track the Autodoc Run ID for subsequent GH action steps.
    with open(os.getenv('GITHUB_ENV'), 'a') as env_file:
        env_file.write(f"AUTODOC_RUN_ID={run_id}\n")