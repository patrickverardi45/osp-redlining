# TrueLine Pilot Token Runbook

Operator reference for minting, delivering, and revoking pilot JWTs during private beta.

---

## 1. Purpose

Pilot tokens are signed JWTs that identify a tenant and gate all authenticated API endpoints. Each company in the private beta receives one token. The token is pasted by an operator or end-user at the `/auth/token` page in the web app; the app stores it in `localStorage` and attaches it as `Authorization: Bearer <token>` on every backend request.

There are no user accounts, no OAuth flow, and no database of credentials. The token **is** the credential.

---

## 2. Prerequisites

| Requirement | Details |
|---|---|
| `TRUELINE_JWT_SECRET` | Must be set in the shell before running the script. Same value the backend server uses. Never commit this value. |
| Python venv active | `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Unix) from `backend/` |
| PyJWT installed | Included in `requirements.txt`; present if venv is current |

Verify the secret is loaded:

```bash
# Should print a non-empty string
echo $TRUELINE_JWT_SECRET        # Unix
$env:TRUELINE_JWT_SECRET         # PowerShell
```

---

## 3. Minting Tokens

Run from the repo root with the backend venv active:

```bash
# Company A — 30-day token (default)
python backend/scripts/issue_pilot_token.py \
  --tenant-id company-a \
  --email ops@company-a.com

# Company B — 60-day token with a user ID
python backend/scripts/issue_pilot_token.py \
  --tenant-id company-b \
  --email ops@company-b.com \
  --user-id beta-001 \
  --ttl-days 60

# Already-expired token for smoke testing
python backend/scripts/issue_pilot_token.py \
  --tenant-id company-a \
  --ttl-days -1
```

The script prints exactly one line (the JWT) to stdout and exits 0. All diagnostics go to stderr. Pipe stdout to your clipboard:

```bash
python backend/scripts/issue_pilot_token.py --tenant-id company-a | pbcopy   # macOS
python backend/scripts/issue_pilot_token.py --tenant-id company-a | clip     # Windows
```

### Tenant slug rules

- Lowercase `a-z`, digits `0-9`, and hyphens only
- No uppercase, no underscores, no spaces
- No leading or trailing hyphen
- Examples: `acme-corp`, `northeast-fiber`, `pilot1`

---

## 4. Tenant Registry

Keep a private record (1Password secure note or equivalent — never in git) of issued tokens:

| Tenant ID | Email | TTL Days | Issued Date | Expires | Notes |
|---|---|---|---|---|---|
| company-a | ops@company-a.com | 30 | 2026-05-12 | 2026-06-11 | Initial beta invite |
| company-b | ops@company-b.com | 60 | 2026-05-12 | 2026-07-11 | Extended pilot |

---

## 5. Secure Delivery

**Allowed channels:**
- 1Password shared vault (preferred)
- Signal or another end-to-end encrypted messenger
- PGP-encrypted or S/MIME-signed email

**Do not send tokens via:**
- Plain email (unencrypted body or attachment)
- SMS
- Unencrypted Slack or Teams messages
- GitHub issues, PRs, or comments
- Any channel that stores plaintext in a server log

If a token is accidentally sent over an insecure channel, treat it as compromised and rotate it immediately (see Section 7).

---

## 6. Four-Case Smoke Test

After minting and deploying a token, verify the four critical paths:

| Case | How to test | Expected result |
|---|---|---|
| **No token** | Open the app in a private/incognito window | Redirected to `/auth/token` paste page |
| **Valid token** | Paste a freshly minted token at `/auth/token` | Redirected to `/`, app loads normally, API calls succeed (check Network tab: `Authorization: Bearer ...` present, responses `200`) |
| **Expired token** | Mint with `--ttl-days -1`, paste it | App clears the token and redirects to `/auth/token` immediately after load |
| **Wrong tenant** | Use a valid token for `tenant-b` against a session created by `tenant-a` | Backend returns `403`; app surfaces an error |

---

## 7. Token Rotation / Revocation

Tokens cannot be individually revoked without a token blocklist (not yet implemented). To cut off a compromised or expired tenant:

1. Rotate `TRUELINE_JWT_SECRET` (invalidates **all** tokens for all tenants)
2. Redeploy the backend with the new secret
3. Re-mint fresh tokens for all active tenants and re-deliver via secure channel

If only one tenant needs to be cut off without disrupting others, contact the development team to implement a per-tenant blocklist before that beta stage.

---

## 8. Stop Conditions

Halt the beta and rotate all credentials if any of the following occur:

- `TRUELINE_JWT_SECRET` is found in a git commit, log file, or any unencrypted channel
- A pilot token is sent over an insecure channel (plain email, SMS, etc.)
- An API response includes data belonging to a different tenant (`tenant_id` mismatch visible in a response payload)
- A `403` is triggered by normal usage (potential cross-tenant probe)
- Any participant reports receiving another company's data

---

## 9. Related Files

| File | Purpose |
|---|---|
| `backend/app/auth.py` | `issue_pilot_token()`, `get_current_tenant()`, JWT constants |
| `backend/scripts/issue_pilot_token.py` | Operator CLI — this runbook's primary tool |
| `web/src/lib/pilotToken.ts` | Frontend token storage, expiry check |
| `web/src/app/auth/token/page.tsx` | Token paste gate UI |
| `web/src/components/AuthGuard.tsx` | Boot guard — redirects unauthenticated sessions |
| `web/src/lib/apiFetch.ts` | Injects `Authorization` header on all API calls |
