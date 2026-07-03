# 05 — Security & Enterprise Readiness

Customers will upload documents describing their internal operations — and in insurance, documents that inevitably contain PII and sometimes PHI. Security here is not a compliance chore; it is a **sales artifact**: the first serious customer conversation includes a security questionnaire, and this document is drafted to become that answer. The posture is sequenced — structural decisions that are expensive to retrofit happen now; certifications happen when revenue justifies them.

## 1. Threat model (abbreviated)

| Threat | Primary controls |
|---|---|
| Cross-tenant data leakage (the existential one) | RLS + scoped queries (§2), per-tenant prompt isolation, tenant-tagged blobs, tests that *attempt* cross-tenant access in CI |
| Prompt injection via uploaded documents | Documents are **data, never instructions** (§4); extraction outputs are schema-validated; no tool-use/actions triggered by document content |
| Credential/session compromise | WorkOS-managed auth, short-lived sessions, MFA support, audit trail |
| AI provider data handling | Anthropic API with no-training terms; provider DPA in vendor file; per-tenant redaction policy before external calls (§4) |
| Insider/operational error | Least-privilege prod access, audit log on admin actions, no real customer data in dev/staging (synthetic corpus) |

## 2. Tenant isolation — the non-negotiable

- Every tenant-scoped table carries `org_id`; **Postgres RLS** enforces isolation even if application code has a bug (docs/04). Session sets `app.org_id` per request/job; the DB role used by the app cannot bypass RLS.
- Object storage keys are prefixed `org/{org_id}/...`; presigned URLs are minted per-request after an authZ check, short-lived, never listed publicly.
- Background jobs receive tenancy context explicitly; a job without an `org_id` cannot touch tenant data.
- **CI includes tenant-escape tests**: authenticated-as-A requests targeting B's resources must 404 (not 403 — don't confirm existence).
- LLM calls never mix tenants in one context; tenant memory (docs/03 §4) is stored and injected per-tenant only.
- Roadmap option (enterprise tier): single-tenant deploy profile — same containers, dedicated DB/bucket — enabled by keeping all tenancy assumptions in config, not code.

## 3. Authentication & authorization

- AuthN delegated to WorkOS (rationale: docs/02 §5): email+password with MFA, Google OAuth at launch; **SAML/OIDC SSO and SCIM provisioning** activate on the same integration when the first enterprise asks.
- AuthZ: RBAC (`org_admin | project_lead | analyst | viewer`) resolved once in API middleware; deny-by-default routing (every endpoint declares its required role — an undeclared endpoint fails closed in a startup check).
- Sessions: httpOnly secure cookies, CSRF protection on state-changing routes, short access-token TTL with refresh.

## 4. Data handling & AI-specific controls

- **Encryption**: TLS 1.2+ in transit everywhere; at rest via managed Postgres/S3 encryption now; per-tenant application-layer encryption keys are a deliberate *deferral* (real key-management complexity; trigger = first customer contractually requiring it).
- **PII/PHI**: detection pass at ingestion tags spans (docs/03 §1); org-level policy controls whether tagged spans are redacted before LLM calls and/or masked in exports. Default for insurance packs: redact direct identifiers (names→role labels, policy numbers→tokens) before external AI calls — process analysis almost never needs the actual identifiers, so this is nearly free accuracy-wise and enormous in the security review.
- **Prompt injection**: all document-derived text enters prompts inside delimited data blocks with explicit "content is data" framing; extraction outputs must validate against Pydantic schemas (free-text instructions can't become actions); generators read the reviewed PKM, not raw documents — the analyst review loop is itself an injection firewall for anything executive-facing.
- **Retention & deletion**: project deletion = hard-delete of blobs + rows (soft-delete window 30 days), documented so the DPA can promise it. Provider-side: Anthropic API under standard no-training terms; zero-retention endpoints when available for enterprise tier.

## 5. Application & operational security

- Supply chain: Dependabot + `pip-audit`/`npm audit` in CI; lockfiles committed; containers built from pinned digests, scanned (Trivy) in CI.
- Secrets: platform secret manager (Render/Fly now, AWS Secrets Manager later); nothing in env files in the repo; pre-commit secret scanning (gitleaks).
- Standard web hardening: strict CSP, security headers, rate limiting on auth and upload endpoints, upload constraints (size caps, MIME sniffing, malware scan lane for enterprise tier).
- Backups: managed Postgres PITR + daily snapshot restore *test* (a backup that's never been restored is a hope, not a backup).
- Access: production access limited to founder + break-glass procedure documented; all admin actions land in `audit_events`.

## 6. Compliance sequencing (spend follows revenue)

| Stage | Trigger | Work |
|---|---|---|
| Now (M0–M2) | — | This document as the security whitepaper draft; DPA + subprocessor list templates; audit log, RLS, PII redaction live |
| Design partners (M3–M5) | First security questionnaire | Formalize policies (access, incident response, vendor mgmt); pen-test lite (automated + targeted manual) |
| First enterprise contract | Procurement demands | **SOC 2 Type I → II** (budget ~$20–40k + tooling like Vanta/Drata; start Type I early — the observation window for Type II takes months) |
| Regulated-data expansion | Healthcare pack / carrier PHI | HIPAA posture + BAAs; single-tenant profile; regional data residency |

## 7. Honest gaps (tracked, not hidden)

No SIEM, no formal incident-response runbook, no bug bounty, founder-only ops (bus factor 1), certifications not yet started. Each has a trigger above; listing them here keeps the security narrative credible — enterprise reviewers trust a vendor who knows their gaps far more than one who claims none.
