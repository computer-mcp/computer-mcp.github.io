#!/usr/bin/env python3
"""Commit one verified catalog before Pages upload, rejecting concurrent source updates."""

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
BRANCH = "refs/heads/main"
REMOTE = "https://github.com/computer-mcp/computer-mcp.github.io"


def git(root, *arguments, data=None, environment=None):
    result = subprocess.run(["git", "-C", str(root), *arguments], input=data,
                            capture_output=True, timeout=60, env=environment)
    catalog.require(result.returncode == 0, f"Git {arguments[0]} failed; Pages must not deploy")
    catalog.require(len(result.stdout) <= catalog.MAX_INDEX + 1024, "Git response exceeds catalog budget")
    return result.stdout


def remote_head(root):
    fields = git(root, "ls-remote", "--exit-code", "origin", BRANCH).decode().split()
    catalog.require(len(fields) == 2 and fields[1] == BRANCH
                    and re.fullmatch(r"[0-9a-f]{40}", fields[0]), "Invalid remote main identity")
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


def publish_commit(root, expected_head):
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
                    "Remote main changed; reconcile from the current source before deployment")
    if current == previous:
        return expected_head
    # Construct the tree from the verified bytes and parent, without touching the caller's index
    # or committing unrelated working-tree files. A concurrent remote child rejects this push.
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
                 "-m", f"chore: publish plugin catalog generation {current['generation']}",
                 environment=identity).decode().strip()
    git(root, "push", "--porcelain", "origin", commit + ":" + BRANCH)
    catalog.require(remote_head(root) == commit, "Catalog commit changed before Pages upload")
    return commit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--check-seed", action="store_true",
                        help="Verify committed seed before reconciliation, without publication")
    args = parser.parse_args()
    try:
        catalog.require(os.environ.get("GITHUB_ACTIONS") == "true"
                        and os.environ.get("GITHUB_REPOSITORY_ID") == "1353589608"
                        and os.environ.get("GITHUB_REF") == BRANCH,
                        "Publication requires the official website main workflow")
        origin = git(ROOT, "remote", "get-url", "origin").decode().strip()
        catalog.require(origin in (REMOTE, REMOTE + ".git"), "Unexpected publication repository")
        if args.check_seed:
            snapshot = verify_seed(ROOT, args.expected_head)
            print(f"Verified committed catalog seed: generation {snapshot['generation']}")
            return
        commit = publish_commit(ROOT, args.expected_head)
        if output := os.environ.get("GITHUB_OUTPUT"):
            with open(output, "a", encoding="utf-8") as file:
                file.write(f"commit={commit}\n")
        print(f"Verified catalog source for Pages: {commit}")
    except (catalog.CatalogError, OSError, ValueError, subprocess.SubprocessError) as error:
        message = str(error) if isinstance(error, catalog.CatalogError) else type(error).__name__
        print(f"Catalog publication failed: {message}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
