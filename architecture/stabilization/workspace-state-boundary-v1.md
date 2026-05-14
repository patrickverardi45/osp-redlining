\# TrueLine — Workspace State Boundary V1



\## Root Finding



GitNexus exposed `rememberSessionFromResponse` as a critical orchestration coupling hub.



Current architecture couples:

\- uploads

\- resets

\- photos

\- current-state

\- exports

\- diagnostics

\- walk flows

\- office flows



through shared session propagation and UI orchestration behavior.



This creates:

\- fragile refreshes

\- hidden rebuild triggers

\- state ghosts

\- inconsistent reset behavior

\- workflow instability after auth changes



\---



\# Current Problematic Pattern



UI action

→ RedlineMap orchestration

→ rememberSessionFromResponse

→ shared mutation path

→ ad hoc refresh/rebuild logic



\---



\# Stabilization Goal



Create a canonical workspace state boundary.



Rules:

\- current-state becomes canonical source of truth

\- uploads do not mutate arbitrary session ownership

\- reset becomes deterministic

\- export reads canonical state only

\- refresh behavior becomes explicit

\- UI stops coordinating session mutation directly



\---



\# Critical Coupling Nodes



\## Session Layer

\- rememberSessionFromResponse

\- saveSessionId

\- appendSessionId



\## RedlineMap

\- fetchState

\- handleReset

\- handleEngineeringPlansUpload

\- handleDesignUpload

\- handleBoreUpload



\## ModernHeroMap

\- fetchStationPhotos

\- handleStationPhotoUpload

\- savePhotoAdjustment



\## DesignSetupPanel

\- fetchCurrentState

\- handleConfirmActiveRoute



\## Walk

\- uploadStationPhotoFilesNonBlocking

\- saveEntry

\- handlePhotoEvidenceSelected



\---



\# Non-Negotiables



DO NOT:

\- rewrite backend/main.py

\- rewrite auth

\- rewrite KMZ parsing/rendering

\- rewrite map systems

\- create broad refactors



DO:

\- isolate workspace state ownership

\- reduce hidden session propagation

\- create deterministic workflow refreshes

\- improve observability around state mutation



\---



\# Next Architecture Tasks



1\. Define canonical workspace/session lifecycle

2\. Define reset contract

3\. Define upload mutation rules

4\. Define current-state ownership

5\. Define export read-only guarantees

6\. Add state transition observability

7\. Add workflow mutation audit trail



\---



\# Tooling Stack



\- GitNexus → architecture graph + blast radius

\- ECC → observability + workflow audit concepts

\- QA Harness → real workflow truth system

\- Claude Opus → architecture/diagnosis

\- Claude Sonnet → surgical implementation

\- Nova/ChatGPT → stabilization coordination



\---



\# Implementation Status (Tasks 1–6 complete)



\## What was done



\- **Task 1:** Added peekSessionId, appendSessionIdReadOnly, acceptSessionFromMutation, and the

session transition ring buffer to session.ts. Deprecated rememberSessionFromResponse.



\- **Task 2:** Migrated read paths (fetchState, fetchCurrentState, fetchStationPhotos, submitBugNote)

from appendSessionId + rememberSessionFromResponse to appendSessionIdReadOnly + peekSessionId.



\- **Task 3:** Migrated write paths (handleReset, handleDesignUpload, handleBoreUpload,

handleEngineeringPlansUpload, handleStationPhotoUpload, savePhotoAdjustment,

handleConfirmActiveRoute) from rememberSessionFromResponse to acceptSessionFromMutation.



\- **Task 4:** Pinned walk session. uploadStationPhotoFilesNonBlocking now guards adoption

with peekSessionId === null so fire-and-forget photo uploads cannot rotate a walk session.



\- **Task 5:** Added qa/tests/workflows/session-boundary.spec.ts with static grep tests

(always run) and ring buffer browser tests (auth-gated). Static tests verify zero

rememberSessionFromResponse callers, acceptSessionFromMutation only in write-path files,

and read-path components export appendSessionIdReadOnly.



\- **Task 6:** Codified the three caller tiers (read / write / telemetry) in a module-level

JSDoc in session.ts and a read-only guard comment in CloseoutPacket.tsx.



\## Final caller graph



\- rememberSessionFromResponse: 0 callers in app code (definition only, deprecated)

\- acceptSessionFromMutation: 10 callers — all confirmed write paths

\- peekSessionId / appendSessionIdReadOnly: used on all read paths

\- window.__truelineSessionLog: ring buffer exposed in dev builds for observability

