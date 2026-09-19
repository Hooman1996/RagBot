# Publishing the co-located projects

The parent RagBot repository remains the development source of truth. Keep
`evaluation_system/backend`, `evaluation_system/frontend`, and
`evaluation_system/deployment` in place, and do not create nested `.git`
directories, submodules, clones, or copied project trees.

For a release, create temporary history-only branches with `git subtree split`
from the RagBot repository root:

```bash
git subtree split \
  --prefix=evaluation_system/backend \
  -b publish/eval-backend

git push <backend-remote> \
  publish/eval-backend:main

git subtree split \
  --prefix=evaluation_system/frontend \
  -b publish/eval-frontend

git push <frontend-remote> \
  publish/eval-frontend:main
```

Review each split branch before pushing. The split rewrites the selected prefix
as repository root: for example, `evaluation_system/backend/README.md`,
`Dockerfile`, and `app/` become `README.md`, `Dockerfile`, and `app/`. The same
applies to frontend files and its root-relative `.github/workflows/ci.yml`.

After a verified push, optionally delete only the temporary publishing branches:

```bash
git branch -D publish/eval-backend
git branch -D publish/eval-frontend
```

Those branch deletions do not remove project files. No remote push is part of
normal development or release-readiness validation.
