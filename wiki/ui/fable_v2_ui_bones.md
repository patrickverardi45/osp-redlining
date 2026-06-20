# Fable v2 UI bones — authoritative web + mobile base

> Lane: `TRUELINE_V2_UI_FABLE_PRESERVE_AND_MOCK_UI_RETIRE` · recorded 2026-06-19.
> This file is the canonical pointer to the **already-built Fable v2 UI repos**. They are the
> authoritative UI / design / function base for the product. Future web integration (Phase 2K+)
> ADAPTS these surfaces to the durable redline-manifest contract — it does **not** rebuild a new UI.

## Key directive (non-negotiable for UI work)

**This is the authoritative v2 UI/design/function base. Future web integration should adapt this
repo/surface to the durable redline manifest contract. Do not rebuild a new replacement UI from
scratch.**

The temporary contract mock UI that previously lived under `truelinev2/contracts/mock_ui/` is
**superseded** by these Fable bones. It remains only as a historical contract fixture (its test still
guards manifest↔fixture fidelity); it is **not** the product UI direction. See its `_DEPRECATED.md`.

## Website — `trueline-web-experience`

| | |
|---|---|
| Repo path | `C:\Nova\projects\trueline-web-experience` |
| Branch | `codex/v2-run-assembly-panel` |
| HEAD | `7e3b392` (`7e3b39239f0807f8728a3b4c0c0f7a7df178bbf7`) |
| Preservation tag | `fable-v2-ui-bones-2026-06-19` → `7e3b392` |
| Working tree at capture | clean |
| Archive bundle | `C:\Nova\archives\trueline_fable_ui_preserve_2026-06-19\trueline-web-experience.git.bundle` |
| Archive metadata | `…\trueline-web-experience.git-head.txt` / `.git-status.txt` / `.git-log.txt` |
| Remote (2026-06-19) | `origin = https://github.com/patrickverardi45/trueline-web-experience` |
| Active branch | `feat/2k-static-bundle-adapter` @ `51dcbf7` (Phase 2K; tracks `origin`, pushed) |

### What the Fable website contains (surfaces)

- **Dashboard**
- **Hero Map**
- **Redline Playback**
- **Plan Viewer**
- **Redline Review**
- **Evidence Explorer**
- **Field Feed**
- **Closeout Readiness**
- **Packet Builder**
- **Settings**

(Contract-first Next.js dashboard; mock API only — the engine plugs in later via the durable
redline-manifest bundle contract. It already has an opt-in live v2 reviewer-reads path and a
run-assembly review-card surface on the recorded branch.)

## Mobile — `trueline-field-mobile`

| | |
|---|---|
| Repo path | `C:\Nova\projects\trueline-field-mobile` |
| Branch | `master` |
| HEAD | `c61b2c3` (`c61b2c34f5f1d762030673fbc611f959162b6796`) |
| Preservation tag | `fable-v2-mobile-bones-2026-06-19` → `c61b2c3` |
| Working tree at capture | clean |
| Archive bundle | `C:\Nova\archives\trueline_fable_ui_preserve_2026-06-19\trueline-field-mobile.git.bundle` |
| Archive metadata | `…\trueline-field-mobile.git-head.txt` / `.git-status.txt` / `.git-log.txt` |

(Independent Expo field-capture app; mock API + shared contracts; camera/GPS gated. Field-capture
product boundary is defined in-repo.)

## Restore-from-bundle (if ever needed)

```sh
git clone C:\Nova\archives\trueline_fable_ui_preserve_2026-06-19\trueline-web-experience.git.bundle restored-web
git clone C:\Nova\archives\trueline_fable_ui_preserve_2026-06-19\trueline-field-mobile.git.bundle restored-mobile
```

Each bundle was created with `git bundle create … --all` and `git bundle verify` reported
*"complete history"*. Bundles contain committed git history only — **no** `node_modules`, build
output, or caches (verified untracked at capture time).

## Boundaries honored by this record

These three repos are **separate** and are **not** merged. This record lives in the engine repo
(`TrueLine_Beta`) purely as a pointer + directive. No deploy, no backend/web bundle-serving wiring,
no engine/render/fixture/census change was made to create it.

## Status — Phase 2K DONE + Fable remote init DONE (2026-06-19)

- **Phase 2K (`TRUELINE_V2_PHASE_2K_FABLE_STATIC_BUNDLE_ADAPTER`) — visually ACCEPTED.** Read-only
  `v2RedlineManifest.ts` adapter + `RedlineManifestPanel` consume the durable bundle on `/redlines`
  (default-OFF gate `NEXT_PUBLIC_TL2_REDLINE_MANIFEST`). No new site, no redesign, no deploy, no Vercel,
  no backend upload/session/MRQ flow. Branch `feat/2k-static-bundle-adapter @ 51dcbf7`; bundle backup
  `C:\Nova\archives\trueline_fable_ui_phase2k_2026-06-19\trueline-web-experience-phase2k-static-bundle-adapter.git.bundle`.
- **Fable remote init (`TRUELINE_V2_FABLE_REMOTE_INIT`) — DONE.** `origin =
  https://github.com/patrickverardi45/trueline-web-experience`; pushed branch
  `feat/2k-static-bundle-adapter @ 51dcbf7` (tracking) + tag `fable-v2-ui-bones-2026-06-19 → 7e3b392`.
  Old local branches (`master`, `codex/*`) intentionally NOT pushed. **Old `osp-redlining`
  repo/project/domain untouched; no Vercel/deploy/domain change.**
- **Next gate (PLANNING, not execution): a NEW Fable Vercel/staging project** on a fresh slug (separate
  from `osp-redlining`), still mock/read-only — NOT a production swap. See
  `trueline_v2_legacy_extraction_and_repo_architecture_plan.md` (P4). Contract:
  `trueline_v2_redline_manifest_contract.md`.
