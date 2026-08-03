# Clean History Migration

## Safety record

The source state was backed up before constructing the clean branch:

- Git bundle: `/root/RagBot-before-clean-root.bundle`
  - size: 3,312,468 bytes
  - SHA-256: `c6cf1e4e10f16e239db3bb1f95fe08ba58f641a8207ae375d5d2dd848ca5b58`
- Working-tree archive: `/root/RagBot-before-clean-root-working-tree.tar.gz`
  - size: 112,647,209 bytes
  - SHA-256: `74ccc53918f044081f24b973d2057c01822ff23a75442ecb1f7e8859bd55e5a1`

Both archives were verified before history work began. The archive excludes
`.git/`, does not dereference symlinks, and preserves local data. The bundle
contains the local `main` and `origin/main` refs and complete reachable history.

At capture time:

- old local/remote main: `b64b5a5e38062596b19f97bfccb1aee26c77a08e`
- old local main history: 26 commits, root
  `d42c689b603958bc242f962f6bccc2de85b983e3`
- remote: `ssh://git@ssh.github.com:443/Hooman1996/RagBot.git`
- GitHub repository: public, default branch `main`, one branch, no tags.

The requested `git ls-files --ignored --exclude-standard` command was recorded
as invalid because Git requires either cached or others mode. The valid
equivalent `git ls-files --others --ignored --exclude-standard` was also run.

## Remote-main audit before replacement

The verified old remote tip contains 1,347 files and a 5,441,930-byte tree. It
does not contain `.env`, `.env.server_git`, `.qdrant-initialized`, `.idea/`,
`t -q`, root data exports, `DOCUMENTS/General_FAQ.csv`, runtime storage, or raw
benchmark output at its tip. It does contain 1,109 generated General FAQ text
chunks. Previous rewritten/unreachable GitHub history cannot be proven absent
from the current refs; credentials exposed in any earlier history must still be
rotated.

## Manual replacement

Review the clean branch and `scripts/replace_remote_with_clean_history.sh`.
The script verifies the branch, history, remote URL, prohibited paths, and
high-confidence secret patterns; fetches `origin/main`; shows both SHAs; and
requires typed confirmation before using force-with-lease.

Do not push until repository owners approve the complete tree diff and notify
all collaborators. After replacement, old clones must be discarded and
recloned because their object databases retain the old history.

## Rollback before or after a mistaken push

The retained local `main` branch and bundle both identify the old tip. Inspect
before acting:

```bash
git show --no-patch --oneline main
git bundle verify /root/RagBot-before-clean-root.bundle
git ls-remote origin refs/heads/main
```

If restoration is authorized, first fetch the current remote SHA and use a
lease that protects against overwriting someone else's subsequent work:

```bash
git fetch origin main
git push --force-with-lease=refs/heads/main:$(git rev-parse origin/main) \
  origin b64b5a5e38062596b19f97bfccb1aee26c77a08e:main
```

If the retained branch is unavailable, recover it from the bundle in a separate
clone:

```bash
git clone /root/RagBot-before-clean-root.bundle /tmp/RagBot-rollback-review
git -C /tmp/RagBot-rollback-review show --no-patch --oneline main
```

Do not restore the working-tree archive over the live server. Extract it only
into a new, empty review directory when file recovery is required.

## Post-push verification plan

```bash
git fetch origin main
test "$(git rev-parse clean-main)" = "$(git rev-parse origin/main)"
test "$(git rev-list --count origin/main)" -eq 1
git ls-tree -r --name-only origin/main | sort
git ls-tree -r --name-only origin/main | grep -E \
  '(^\.env($|\.)|General_FAQ_[0-9]+\.txt$|General_FAQ\.csv$|^\.idea/|^(storage|qdrant_storage)/)' \
  && exit 1 || true
```

Verify on GitHub that `main` shows one commit, README renders, and the document,
chunk, and benchmark-result directories contain only their expected `.gitkeep`
files. Confirm expected source files such as `main.py`, `mobile_api.py`,
`agent_graph.py`, `utils/RagSystem.py`, tests, scripts, and documentation exist.

Then test a clean clone without touching the live checkout:

```bash
review_dir="$(mktemp -d /tmp/RagBot-clean-clone.XXXXXX)"
git clone ssh://git@ssh.github.com:443/Hooman1996/RagBot.git "$review_dir"
test -d "$review_dir/data_insertion_chunks/DOCUMENTS"
test -d "$review_dir/data_insertion_chunks/CHUNKS/General_FAQ"
test -d "$review_dir/benchmarks/results"
python3 -m compileall -q "$review_dir"
```

Run the documented tests available in the review environment. Never run
connectivity or load tests against production.
