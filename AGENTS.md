# OSP Redlining Agent Guide

## Rules
- Diagnose first
- Do not guess
- Do not redesign
- Make minimal targeted changes
- Return full file replacements only
- Always include backend and frontend reload commands after every file output

## Project structure
- backend = FastAPI backend
- web = frontend app

## Standard run commands

Backend terminal:
uvicorn main:app --reload

Frontend terminal:
npm run dev

## Behavior
- Preserve working features
- Do not touch unrelated files
- Preserve map behavior, station anchoring, hitbox alignment, and photo upload functionality
- Prefer surgical fixes over rewrites
- Always run backend and frontend builds/tests after any change to validate functionality
- Never modify KMZ parsing, rendering, or coordinate transformation logic without explicit user approval
- Use git status and git diff to confirm changes before committing, ensuring no unintended modifications
- Diagnose errors by examining logs and reproducing issues before proposing fixes
- Limit edits to single functions or components per change, avoiding multi-file refactors
- Preserve all existing map interactions, zoom behaviors, and layer toggles in frontend components
- Avoid assuming API endpoints or data structures; verify with backend code or documentation
- Require manual testing of photo uploads and station placements after any map-related edits
- Do not alter station anchoring algorithms or hitbox calculations without thorough testing
- Prioritize fixes that maintain existing working features over new optimizations or redesigns