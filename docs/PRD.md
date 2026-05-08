# FinSight — Product Requirements Document (PRD)

> **Version:** 0.1 (Draft for Midterm Report — Week 7)
> **Status:** In review
> **Course:** UTEC — Capstone Project
> **Repository:** https://github.com/bylenz/finsight

---

## 1. Executive summary

**FinSight** is a web-based personal finance tracker with conversational AI in Spanish, built for the Latin American market. Users record expenses by **voice, text, or CSV**, the AI **categorizes them automatically**, detects spending patterns, and emits budget alerts. The application is **privacy-first** (no banking credentials required) and supports **multi-currency** (PEN, USD) and **multi-user households**.

Unlike existing solutions (Mint, YNAB, Fintonic), FinSight is optimized for local vocabulary, payment methods (Yape, Plin), and tax context (freelancer mode for SUNAT).

---

## 2. Goals and success metrics

### 2.1 Product goals

- G1. Reduce average expense entry time to **under 5 seconds** vs. traditional apps (~30 s).
- G2. Achieve **≥ 85 % auto-categorization accuracy** on the validation set.
- G3. Drive users to review weekly insights **at least once a week**.

### 2.2 Metrics (post-MVP)

- DAU/MAU > 0.25 (recurring use).
- Week-4 retention ≥ 30 %.
- Manually corrected categorizations < 15 % of expenses.

---

## 3. Personas

### P1 — Young independent professional

- **Persona:** Camila, 26, UX designer in Lima.
- **Pain points:** runs out of money each month with no clue where it went; uses Excel half-heartedly.
- **Key need:** fast capture and a clear monthly view.

### P2 — Freelancer / contractor

- **Persona:** Diego, 31, frontend dev, invoices via RHP.
- **Pain points:** mixes personal and business expenses; tax season is painful.
- **Key need:** tag expenses as `business` and export a SUNAT-friendly report.

### P3 — Household / couple

- **Persona:** Ana and Luis, 34 and 36, share an apartment in Surco.
- **Pain points:** two people spending against one budget, frequent disagreements.
- **Key need:** shared budget with clear visibility of who spent what.

### P4 — Expat / multi-currency

- **Persona:** Mariana, 29, Venezuelan in Lima, paid in USD.
- **Pain points:** mentally converts everything; can't see real spending in a single currency.
- **Key need:** record in source currency, view totals in a chosen base currency.

---

## 4. Scope

### 4.1 In-scope (MVP — Midterm Report, Week 7)

- User authentication (email + password, JWT).
- Expenses CRUD (create, list, update, delete).
- Auto-categorization via LLM (with manual override).
- Monthly budget per category.
- Dashboard with: month total, spend by category, spend by week.
- Alerts at 80 % and 100 % of budget.
- CSV export.

### 4.2 In-scope (v1 — Final Report, Week 16)

- Voice expense entry (Whisper API).
- Multi-currency (PEN, USD) with daily FX rate.
- Multi-user households (roles: owner, contributor, viewer).
- Freelancer mode (`business` tag, tax report).
- Weekly LLM-generated insights (e.g. "you spend 40 % more on Fridays").
- CSV import for Yape, Plin, BCP, Interbank.

### 4.3 Out-of-scope (explicit)

- Direct integration with banking APIs (Plaid, Belvo).
- Investment, crypto, or stock tracking.
- Recommendations of financial products.
- Native mobile app (responsive web is sufficient).
- OCR of paper receipts (post-v1).

---

## 5. Functional requirements (MoSCoW)

> ID convention: `FR-{module}-{n}`.

### 5.1 Authentication and users

| ID         | Requirement                                                           | Priority |
| ---------- | --------------------------------------------------------------------- | -------- |
| FR-AUTH-01 | The system shall allow registration with email and password.          | Must     |
| FR-AUTH-02 | The system shall authenticate users and issue a JWT with 24 h expiration. | Must |
| FR-AUTH-03 | The system shall allow logout, invalidating the token.                | Must     |
| FR-AUTH-04 | The system shall support password recovery via email.                 | Should   |

### 5.2 Expense management

| ID        | Requirement                                                                   | Priority |
| --------- | ----------------------------------------------------------------------------- | -------- |
| FR-EXP-01 | The system shall allow recording an expense with amount, date, description, and currency. | Must |
| FR-EXP-02 | The system shall auto-categorize expenses using an LLM.                       | Must     |
| FR-EXP-03 | The user shall be able to override the suggested category.                    | Must     |
| FR-EXP-04 | The system shall allow editing and deleting the authenticated user's expenses. | Must    |
| FR-EXP-05 | The system shall allow voice expense entry (audio → text → category).         | Should   |
| FR-EXP-06 | The system shall allow flagging an expense as `business` for freelancer mode. | Could    |

### 5.3 Budgets

| ID        | Requirement                                                  | Priority |
| --------- | ------------------------------------------------------------ | -------- |
| FR-BUD-01 | The user shall be able to set a total monthly budget.        | Must     |
| FR-BUD-02 | The user shall be able to set per-category budgets.          | Must     |
| FR-BUD-03 | The system shall alert when 80 % of a budget is reached.     | Must     |
| FR-BUD-04 | The system shall alert when 100 % of a budget is exceeded.   | Must     |

### 5.4 Dashboard and insights

| ID         | Requirement                                                            | Priority |
| ---------- | ---------------------------------------------------------------------- | -------- |
| FR-DASH-01 | The dashboard shall show the current month's total spend.              | Must     |
| FR-DASH-02 | The dashboard shall render a category breakdown chart (pie / bar).     | Must     |
| FR-DASH-03 | The dashboard shall render a daily/weekly spend chart.                 | Must     |
| FR-DASH-04 | The system shall produce a natural-language weekly insight.            | Should   |

### 5.5 Multi-currency and multi-user

| ID        | Requirement                                                               | Priority |
| --------- | ------------------------------------------------------------------------- | -------- |
| FR-MUL-01 | The system shall store the source currency of each expense.               | Must     |
| FR-MUL-02 | The system shall convert to the base currency using the FX rate of the expense date. | Should |
| FR-MUL-03 | The system shall support households with multiple users and roles.        | Should   |

### 5.6 Import / export

| ID       | Requirement                                                      | Priority |
| -------- | ---------------------------------------------------------------- | -------- |
| FR-IO-01 | The system shall export expenses to CSV.                         | Must     |
| FR-IO-02 | The system shall import expenses from CSV with column mapping.   | Should   |
| FR-IO-03 | The system shall offer import templates for Yape, Plin, BCP, Interbank. | Could |

---

## 6. Non-functional requirements

| ID     | Category        | Requirement                                                                |
| ------ | --------------- | -------------------------------------------------------------------------- |
| NFR-01 | Performance     | Dashboard shall load in < 1.5 s with up to 1 000 expenses.                 |
| NFR-02 | Performance     | LLM categorization shall return in < 2 s at p95.                           |
| NFR-03 | Availability    | 99 % uptime target in production (not enforced in evaluation).             |
| NFR-04 | Security        | Passwords stored with bcrypt (cost ≥ 12).                                  |
| NFR-05 | Security        | All private routes require a valid JWT.                                    |
| NFR-06 | Security        | No sensitive data (tokens, passwords, individual amounts) in production logs. |
| NFR-07 | Privacy         | The system shall never request banking credentials.                        |
| NFR-08 | Maintainability | ≥ 80 % test coverage on domain modules.                                    |
| NFR-09 | Maintainability | Linter (ruff) and formatter (black) enforced via pre-commit and CI.        |
| NFR-10 | Portability     | The application shall start with `docker compose up` with no manual steps. |
| NFR-11 | i18n            | UI defaults to Spanish, structured for English (i18n-ready).               |
| NFR-12 | Accessibility   | Main components shall meet WCAG 2.1 level AA.                              |

---

## 7. Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for diagrams and module map.

---

## 8. Release plan

| Release                          | Week         | Scope                                                                           |
| -------------------------------- | ------------ | ------------------------------------------------------------------------------- |
| **v0.1 — Skeleton**              | 5            | Repo, CI, Docker Compose, auth, data model.                                     |
| **v0.2 — MVP**                   | 7 (midterm)  | Expenses CRUD, AI categorization, basic budget, dashboard, CSV export. ≥ 9 tests. |
| **v0.3 — Voice + multi-currency** | 10           | Whisper, FX conversion, CSV import.                                            |
| **v0.4 — Households + freelancer** | 13          | Multi-user households, `business` tag, tax report.                              |
| **v1.0 — AI insights**           | 16 (final)   | Weekly LLM insights, smart alerts, polish.                                      |

---

## 9. Acceptance criteria for the Midterm Report

The MVP is considered delivered when:

- [ ] Public GitHub repo with README, `tests/`, automation script.
- [ ] ≥ 9 commits in Conventional Commits format.
- [ ] Branching strategy documented (GitFlow or Trunk-Based).
- [ ] ≥ 1 Pull Request merged with review.
- [ ] ≥ 9 unit tests passing, with execution evidence.
- [ ] Working `Dockerfile` and `docker-compose.yml`.
- [ ] App starts with `docker compose up` and responds on `localhost`.
- [ ] PDF report covering the brief's minimum content.
