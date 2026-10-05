#!/usr/bin/env python3
"""Propose one verified catalog for merge and confirm the merged source before Pages upload."""

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import plugin_catalog as catalog


ROOT = Path(__file__).resolve().parent.parent
INDEX = "public/plugins/index.json"
POLICY = "scripts/plugin-catalog-policy.json"
BRANCH = "refs/heads/master"
PROPOSAL = "refs/heads/automation/plugin-catalog"
REMOTE = "https://github.com/computer-mcp/computer-mcp.github.io"


def git(root, *arguments, data=None, environment=None):
    result = subprocess.run(["git", "-C", str(root), *arguments], input=data,
                            capture_output=True, timeout=60, env=environment)
    catalog.require(result.returncode == 0, f"Git {arguments[0]} failed; Pages must not deploy")
    catalog.require(len(result.stdout) <= catalog.MAX_INDEX + 1024, "Git response exceeds catalog budget")
    return result.stdout


def remote_head(root, ref=BRANCH):
    fields = git(root, "ls-remote", "--exit-code", "origin", ref).decode().split()
    catalog.require(len(fields) == 2 and fields[1] == ref
                    and re.fullmatch(r"[0-9a-f]{40}", fields[0]), f"Invalid remote {ref} identity")
    return fields[0]


def committed_snapshot(root, expected_head):
    path = expected_head + ":" + INDEX
    catalog.require(git(root, "cat-file", "-t", path).strip() == b"blob", "Committed catalog seed is required")
    size = int(git(root, "cat-file", "-s", path))
    catalog.require(0 < size <= catalog.MAX_INDEX, "Committed catalog exceeds byte budget")
    data = git(root, "cat-file", "blob", path)
    snapshot = catalog.validate_snapshot(catalog.decode_json(data))
    catalog.require(catalog.canonical(snapshot) == data, "Committed catalog is not canonical")
    return snapshot


def verify_seed(root, expected_head):
    catalog.require(re.fullmatch(r"[0-9a-f]{40}", expected_head) is not None, "Invalid source commit")
    catalog.require(git(root, "rev-parse", "HEAD").decode().strip() == expected_head,
                    "Local source changed before reconciliation")
    previous = committed_snapshot(root, expected_head)
    catalog.require(catalog.read_json_bytes(root / INDEX) == catalog.canonical(previous),
                    "Catalog seed differs from committed authority")
    return previous


def propose_commit(root, expected_head):
    catalog.require(re.fullmatch(r"[0-9a-f]{40}", expected_head) is not None, "Invalid source commit")
    catalog.require(git(root, "rev-parse", "HEAD").decode().strip() == expected_head,
                    "Local source changed during publication")
    changes = git(root, "status", "--porcelain=v1", "--untracked-files=normal", "-z")
    catalog.require(changes in (b"", b" M " + INDEX.encode() + b"\0"),
                    "Only the generated catalog may differ from the verified source")
    previous = committed_snapshot(root, expected_head)
    data = catalog.read_json_bytes(root / INDEX)
    current = catalog.validate_snapshot(catalog.decode_json(data))
    catalog.require(catalog.canonical(current) == data, "Generated catalog is not canonical")
    policy = catalog.validate_policy(catalog.decode_json(catalog.read_json_bytes(root / POLICY)))
    catalog.validate_policy_snapshot(policy, current)
    catalog.validate_successor(previous, current)
    catalog.require(catalog.read_json_bytes(root / "dist/plugins/index.json") == data,
                    "Pages artifact does not contain the verified catalog bytes")
    catalog.require(remote_head(root) == expected_head,
                    "Remote master changed; reconcile from the current source before deployment")
    if current == previous:
        return expected_head
    # Construct the tree from the verified bytes and parent, without touching the caller's index
    # or committing unrelated working-tree files. Each run replaces any earlier unmerged proposal.
    blob = git(root, "hash-object", "-w", "--stdin", data=data).decode().strip()
    with tempfile.TemporaryDirectory(prefix="computer-mcp-catalog-index-") as directory:
        environment = {**os.environ, "GIT_INDEX_FILE": str(Path(directory) / "index")}
        git(root, "read-tree", expected_head, environment=environment)
        git(root, "update-index", "--add", "--cacheinfo", f"100644,{blob},{INDEX}", environment=environment)
        tree = git(root, "write-tree", environment=environment).decode().strip()
    identity = {**os.environ, "GIT_AUTHOR_NAME": "github-actions[bot]",
                "GIT_COMMITTER_NAME": "github-actions[bot]",
                "GIT_AUTHOR_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com",
                "GIT_COMMITTER_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com"}
    commit = git(root, "-c", "commit.gpgsign=false", "commit-tree", tree, "-p", expected_head,
                 "-m", f"Publish plugin catalog generation {current['generation']}",
                 environment=identity).decode().strip()
    git(root, "push", "--porcelain", "--force", "origin", commit + ":" + PROPOSAL)
    catalog.require(remote_head(root, PROPOSAL) == commit, "Catalog proposal changed before merge")
    return commit


def verify_merged(root, expected_head, proposal):
    for value in (expected_head, proposal):
        catalog.require(re.fullmatch(r"[0-9a-f]{40}", value) is not None, "Invalid source commit")
    git(root, "fetch", "--no-tags", "origin", BRANCH)
    merged = git(root, "rev-parse", "FETCH_HEAD").decode().strip()
    catalog.require(merged != expected_head, "Catalog proposal is not merged")
    catalog.require(git(root, "rev-list", "--parents", "-n", "1", merged).decode().split()
                    == [merged, expected_head],
                    "Master changed before the catalog proposal merged; reconcile from current master")
    catalog.require(git(root, "rev-parse", merged + "^{tree}") == git(root, "rev-parse", proposal + "^{tree}"),
                    "Merged source differs from the verified catalog proposal")
    return merged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--check-seed", action="store_true",
                        help="Verify committed seed before reconciliation, without publication")
    parser.add_argument("--merged", metavar="PROPOSAL",
                        help="Verify that master is the squash merge of this catalog proposal")
    args = parser.parse_args()
    try:
        catalog.require(os.environ.get("GITHUB_ACTIONS") == "true"
                        and os.environ.get("GITHUB_REPOSITORY_ID") == "1353589608"
                        and os.environ.get("GITHUB_REF") == BRANCH,
                        "Publication requires the official website master workflow")
        origin = git(ROOT, "remote", "get-url", "origin").decode().strip()
        catalog.require(origin in (REMOTE, REMOTE + ".git"), "Unexpected publication repository")
        if args.check_seed:
            snapshot = verify_seed(ROOT, args.expected_head)
            print(f"Verified committed catalog seed: generation {snapshot['generation']}")
            return
        if args.merged:
            commit = verify_merged(ROOT, args.expected_head, args.merged)
            output, message = f"commit={commit}", f"Verified merged catalog source for Pages: {commit}"
        elif (commit := propose_commit(ROOT, args.expected_head)) == args.expected_head:
            output, message = f"commit={commit}", f"Verified catalog source for Pages: {commit}"
        else:
            output, message = f"proposal={commit}", f"Proposed catalog generation for merge: {commit}"
        if path := os.environ.get("GITHUB_OUTPUT"):
            with open(path, "a", encoding="utf-8") as file:
                file.write(output + "\n")
        print(message)
    except (catalog.CatalogError, OSError, ValueError, subprocess.SubprocessError) as error:
        message = str(error) if isinstance(error, catalog.CatalogError) else type(error).__name__
        print(f"Catalog publication failed: {message}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
