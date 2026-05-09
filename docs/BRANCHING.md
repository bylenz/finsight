# Branching strategy — GitFlow

## Long-lived branches

| Branch    | Purpose                                                | Protected |
| --------- | ------------------------------------------------------ | --------- |
| `main`    | Production. Tagged releases only (`v0.2`, `v0.3`, …).  | Yes       |
| `develop` | Integration branch. Default branch during development. | Yes       |

Both `main` and `develop` are **PR-only**. No direct pushes.

## Short-lived branches

| Pattern          | Cuts from  | Merges back into          | Purpose                       |
| ---------------- | ---------- | ------------------------- | ----------------------------- |
| `feature/<name>` | `develop`  | `develop`                 | New feature.                  |
| `release/x.y`    | `develop`  | `main` and `develop`      | Hardening before tagging.     |
| `hotfix/x.y.z`   | `main`     | `main` and `develop`      | Urgent fix on a tagged release. |

Branch names are kebab-case: `feature/auth`, `feature/expenses-crud`, `feature/streamlit-ui`.

## Workflow per feature

```bash
git checkout develop && git pull
git checkout -b feature/<name>

# work ...
git add -p
git commit -m "feat(<scope>): <imperative description>"

git push -u origin feature/<name>
gh pr create --base develop --title "feat(<scope>): ..." --body "..."

# after CI green + 1 review
gh pr merge --squash --delete-branch
```

## Conventional Commits

Every commit message follows the [Conventional Commits 1.0](https://www.conventionalcommits.org/) spec:

```
<type>(<scope>): <imperative subject>

[optional body]

[optional footer(s)]
```

Allowed types: `feat`, `fix`, `chore`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `revert`, `release`.

PR titles are linted by `.github/workflows/pr-title.yml`.

## Pull Request rules

- Targets `develop` (or `release/x.y` for hotfixes against `main`).
- Title is a Conventional Commit.
- CI green: lint + tests + coverage ≥ 80 % on domain.
- ≥ 1 reviewer approval.
- Squash-merged. No merge commits on `develop`.
- Linked PRD requirement IDs in the description (e.g. `FR-AUTH-01`).

## Releases

```bash
# When develop is ready
git checkout -b release/0.2 develop
# fix lint, bump version, update CHANGELOG
gh pr create --base main --title "release: v0.2"
# after merge
git tag v0.2 && git push origin v0.2
git checkout develop && git merge --no-ff release/0.2
```
