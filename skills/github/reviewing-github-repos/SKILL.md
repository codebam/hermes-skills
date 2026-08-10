---
name: reviewing-github-repos
description: Review GitHub profiles/repos by cloning and checking builds.
---

# Reviewing a GitHub repo or user's projects

Use when the user asks to "open/summarize <user>'s GitHub profile", "what does this repo do", or "is this project functional". The user explicitly permits cloning to read code (`clone projects to look at the code if necessary`).

## Workflow

1. **Profile first via the browser** (or `gh api users/<name>` when logged in): load the profile page, note repo count, and open the Repositories tab. A recent/empty account often has a single freshly-created repo with no README — the repo description line is your first hint.
2. **Descriptions are unreliable.** Do NOT report what a repo "is" from its one-line description alone. Read the code to verify.
3. **Clone it** (`git clone --depth 1 <url>` into /tmp works well; `--depth 1` keeps it fast).
4. **Read the "identity" files first** — they tell you stack + purpose fast:
   - `package.json` (or `Cargo.toml` / `pyproject.toml` / `go.mod`): deps, scripts, name. Deps reveal the stack (e.g. `@tailwindcss/vite` + `lucide-react` + `react` = React/Tailwind/Material-ish UI; `@google/genai` = Gemini API applet).
   - `metadata.json` / `.env.example` (Google AI Studio applets carry these): declared name, description, required env keys.
   - `index.html` (`lang`/`dir`/fonts reveal language + RTL/LTR), entry `src/main.*`, `src/types.ts` (core data model), the main context/store file (feature list).
5. **Verify it actually works — never skip this.** Run the real check, don't trust build claims in the description:
   ```
   npm install && npm run build && npm run lint
   ```
   (`lint` for Vite React templates is `tsc --noEmit`; its exit code matters.) A repo whose description says "please make it work" may already build cleanly — report what the build/lint ACTUALLY returned, not what the description implies.
6. **Summarize concretely**: purpose, stack, language/localization, core features (from types + context/store + components), persistence mechanism, and CURRENT build status (from step 5).

## Pitfalls
- Don't clone into the user's working dir; use a throwaway like /tmp and clean up.
- `metadata.json` + a `google-gemini/aistudio-repository-template` link in the About panel means it's an AI Studio applet — explains `.env.example` (GEMINI_API_KEY, APP_URL) and the "server-side Gemini API" capability even if the UI is client-side.
- Check `isWeeklyRecurring`-style domain flags / the week/overdue logic in the store for genuine feature depth — summaries written only from component filenames undersell hand-wired logic.
- Report build/lint exit codes + bundle size as evidence, not just "it compiles."
