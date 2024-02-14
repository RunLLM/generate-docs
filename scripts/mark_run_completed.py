import argparse
import os

from scripts.client import RunLLMClient

parser = argparse.ArgumentParser(description="Mark an autodoc run as completed.")
parser.add_argument("--server-address", type=str, required=True, help="The address of the RunLLM server")
parser.add_argument("--api-key", type=str, required=True, help="The API key to use for the RunLLM server")
parser.add_argument("--pr-url", type=str, required=True, help="The URL of the pull request")
args = parser.parse_args()

if __name__ == "__main__":
    run_id = os.environ.get("AUTODOC_RUN_ID")
    assert run_id

    client = RunLLMClient(args.server_address, args.api_key)
    client.mark_completed(run_id, args.pr_url)
