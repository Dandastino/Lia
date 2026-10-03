# Lia frontend: UI/UX and accessibility audit

Scope: `frontend/src` (Login, Admin, ConnectorSettings, VoiceInterface, App) and all CSS, reviewed against WCAG 2.2 AA and common HCI heuristics. Each finding lists the problem, why it matters, the fix and its severity. "Status" says whether the fix was implemented in this change set.

Severity scale: **Critical** (blocks use or breaks the build/security), **High** (serious barrier or data risk), **Medium** (clear usability/consistency problem), **Low** (polish).

## 1. Structure and navigation

| # | Problem | Why it matters | Fix | Severity | Status |
|---|---|---|---|---|---|
| 1.1 | `src/lib/api.js` was imported by every component but is not in git: the root `.gitignore` contains `lib/` (Python pattern) which also swallowed `frontend/src/lib/`. A clean checkout could not build. | Build and CI break on any fresh clone; the base-URL logic was invisible to review. | Created `src/lib/api.js` and un-ignored `src/lib/` in `frontend/.gitignore`. | Critical | Done |
| 1.2 | Every screen was a bare `<div>`; no `<main>`, `<header>`, `<nav>`; the admin tab strip was a row of buttons with no landmark. | Screen-reader users cannot jump between regions; no skip link. | Semantic landmarks on all screens, `<nav aria-label>` with `aria-current="page"` for the active tab, "Skip to main content" link, `<main tabIndex=-1>` as the skip target. | High | Done |
| 1.3 | Navigation is `useState` only: refresh always restores the same view, Back button leaves the app, no deep links. | Expected browser behaviour is broken, but changing to a router is a logic change. | Left as is (out of scope: "do not change app logic"). `document.title` now changes per view so history/tab titles are meaningful. `react-router-dom` was listed but never used and carried 2 audit advisories, so it was removed. | Medium | Partly (title); router left as a recommendation |
| 1.4 | `Admin.jsx` was a 900-line component with 7 tabs, 5 forms and duplicated markup for create/edit. | Hard to maintain and test; duplicated validation/ids. | Split into `Admin.jsx` (state + API) and `admin/` components: `DashboardTab`, `UsersTab`, `OrganizationsTab`, `OrganizationForm`, `UserForm`, `ResetPasswordDialog`, `ConnectorConfigForm`, `Field`, `DataState`; shared `Modal` and `ConfirmDialog`. | Medium | Done |
| 1.5 | `VoiceInterface` had a single "tab" (`activeTab`) with a never-rendered tab bar CSS, and the whole LiveKit bundle (~420 kB) loaded on the login page. | Dead code, slow first load. | Removed dead tab state/CSS; `VoiceInterface` is lazy-loaded (main bundle 633 kB -> 217 kB). | Low | Done |

## 2. Visual hierarchy, consistency, typography, spacing

| # | Problem | Why it matters | Fix | Severity | Status |
|---|---|---|---|---|---|
| 2.1 | Four stylesheets redefined `.form-group`, `.error-message`, `.alert`, `.submit-btn`, `.tab-btn`, `.tab-content`, `@keyframes fadeIn/slideUp` with different values; which one won depended on import order. | Inconsistent look between screens, accidental overrides. | One source of truth in `index.css` (tokens + shared components); screen CSS files only keep screen-specific rules (Voice). | High | Done |
| 2.2 | Mixed units (rem in some files, `px` and magic numbers like `margin: 0 -40px` in media queries), hard-coded hex colours next to CSS variables. | Spacing and colour drift; hard to theme. | Tokens for colour, spacing, radius, type scale, shadow, focus and target size; rules use tokens. | Medium | Done |
| 2.3 | Buttons: ALL-CAPS tracking text, three different button systems (`.submit-btn`, `.btn`, `.voice-header-btn`, `.logout-btn`), hover "lift" transforms. | Uppercase hurts readability, inconsistent affordances. | One `.btn` system (primary, secondary, danger, warning, ghost, sm); sentence case. | Medium | Done |
| 2.4 | Headings: Admin and Voice pages had `h1` and then `h3`/`h4` jumps ("Total Organizations" h3 before any h2 in the cards, `h4` for config group); Login used `h2` for a subtitle. | Broken outline for assistive tech. | Logical `h1` > `h2` > `h3`; subtitle is a paragraph. | Medium | Done |
| 2.5 | Copy inconsistency: "Logout" vs "Log out", "Logged in as" vs "Signed in", Title Case labels mixed with sentence case, "Loading..." with no context. | Weak polish and trust. | Sentence case everywhere, "Log out", "Signed in as", contextual loading text ("Loading users..."). | Low | Done |

## 3. Colour and contrast (WCAG 1.4.3, 1.4.11)

| # | Problem | Why it matters | Fix | Severity | Status |
|---|---|---|---|---|---|
| 3.1 | White text on `#667eea` gradient start (about 3.6:1) for buttons, headers, stat cards. | Fails 4.5:1 for normal text. | Primary `#4f46e5` / gradient to `#6d28d9` (>= 6.3:1 with white). | High | Done |
| 3.2 | `--color-text-muted: #9ca3af` (2.5:1 on white) used for helper text; `rgba(255,255,255,.7)` tab labels on the gradient; `#64748b` on `#fafafa`. | Unreadable for low-vision users. | Muted `#6b7280` (4.8:1), secondary `#4b5563` (7.6:1); tab labels fully white on a darkened header band. | High | Done |
| 3.3 | Reconnect button `#3b82f6` on a purple gradient, logout hover `#ef4444` on the gradient, warning button white on `#f59e0b` (2.1:1), green device button white on `#10b981` (2.5:1), role badge `#4ECDC4` with white text (1.9:1). | Several controls effectively invisible. | Header actions use a translucent white-on-dark ghost button; warning `#b45309` (5.0:1); green `#047857`; user badge `#0f766e` (5.5:1); danger `#b91c1c` (6.5:1). | High | Done |
| 3.4 | Input borders `#e5e7eb` (1.2:1) on white; focus indicated only by a 10 % tint box-shadow. | Fields' boundaries and focus not perceivable (1.4.11, 2.4.7). | Control border `#6b7280` (4.8:1) and a 3 px focus ring. | High | Done |
| 3.5 | Errors/success differ only by colour and a left border in places (`.alert-*` in Voice had a different, translucent style). | Colour-only cues. | Errors and successes always carry text; shared alert style with dark text on tinted background (>= 7:1). | Medium | Done |
| 3.6 | Status pill in the conversation header: white text on 25 % white overlay over gradient. | Contrast dropped below 4.5:1. | Dark translucent pill (`rgba(0,0,0,.3)`), white indicator dot. | Medium | Done |

## 4. Responsive behaviour

| # | Problem | Why it matters | Fix | Severity | Status |
|---|---|---|---|---|---|
| 4.1 | Admin tabs used `margin: 0 -40px` hack; header stacked in a column with fixed px gaps; tables shrank to 12 px text. | Horizontal overflow and tiny text on phones. | Flex-wrap headers, scrollable tab strip, 0.875 rem table text, `overflow-x:auto` table wrapper; verified by an E2E test at 375 px (no horizontal page scroll). | Medium | Done |
| 4.2 | `min-height: 100vh` only (mobile address bar overflow). | Content hidden under browser chrome on mobile. | `100dvh` where available. | Low | Done |
| 4.3 | Touch targets < 44 px (small table buttons, tab buttons). | Hard to hit on touch screens. | `--target-min: 2.75rem` for primary controls; table row actions 2.25 rem minimum with spacing. | Medium | Done |

## 5. Loading, empty and error states

| # | Problem | Why it matters | Fix | Severity | Status |
|---|---|---|---|---|---|
| 5.1 | One `loading` flag was shared by the dashboard load and every mutation: after each create/update the tables disappeared into "Loading...". | Layout jumps, lost scroll/context. | Separate `loadingData` and `busy`; tables stay mounted during mutations. | Medium | Done |
| 5.2 | A failed dashboard load showed a transient error and an empty UI with no way to retry. | Dead end. | Persistent error with a "Try again" button. | High | Done |
| 5.3 | Empty states: Dashboard tables rendered headers with no rows; organizations list had no empty message. | Unclear whether data is missing or loading. | Explicit empty-state messages with next-step hints. | Medium | Done |
| 5.4 | Loading indicators were plain text without live-region semantics. | Screen readers never learn that work is in progress. | `role="status"` + spinner, `aria-busy` on forms and panels, buttons switch to "Signing in..." / "Saving..." and are disabled. | Medium | Done |
| 5.5 | App crashes (render error) showed a blank white page. | Total loss of the UI. | `ErrorBoundary` with an accessible fallback and reload button (logs only the message). | High | Done |
| 5.6 | ConnectorSettings always opened with placeholder values (`password: "change_me"`); pressing Save would overwrite the real connector with sample data. | Silent data corruption. | Loads the saved connector (`GET /organizations/:id`) and shows it; secrets arrive masked (`********`) and are omitted from the PATCH when unchanged. | High | Done |

## 6. Forms and validation, error messages

| # | Problem | Why it matters | Fix | Severity | Status |
|---|---|---|---|---|---|
| 6.1 | Only native `required` bubbles (browser-dependent, English UI chrome, unstyled, no focus management). | Inconsistent and not announced reliably. | `noValidate` + own validators (`lib/validation.js`): inline `field-error` text, `aria-invalid`, `aria-describedby`, focus moved to the first invalid field. | High | Done |
| 6.2 | Create-user did not check password length (reset-password promised "min 6" only in a placeholder). | Backend rejects late with a generic error. | Client-side minimum (6) with visible hint, org required, email format. | Medium | Done |
| 6.3 | Connector JSON error was a generic banner; arrays/null parsed as valid. | Hard to know what to fix. | Inline error bound to the textarea, object-only check, focus moved to the field. | Medium | Done |
| 6.4 | Required marker `*` was part of the label text and read aloud as "star"; labels used `placeholder` as the only example text; fields lacked `autocomplete`. | Noise for screen readers, password managers misbehave. | CSS-only marker + `aria-required`; `autocomplete` (`username`, `current-password`, `new-password`). | Low | Done |
| 6.5 | Error text came straight from the server or `err.message` (e.g. "Request failed with status code 500", stack-like text), no network-failure message. The backend is moving to generic `{"error": ...}` messages. | Unhelpful or leaky messages. | `getErrorMessage()`: server `error`/`msg` if present, a friendly "cannot reach the server" for network errors, otherwise a context-specific fallback. | Medium | Done |
| 6.6 | Edit organization sent `connector_config: {}` when the admin only changed the name (dashboard does not return the config), which would erase stored credentials. | Data loss. | The config is only sent when the admin entered values or changed the connector type; masked values are never sent. Needs backend support for "key omitted = keep" (already the behaviour of the PUT route). | High | Done |

## 7. Destructive actions

| # | Problem | Why it matters | Fix | Severity | Status |
|---|---|---|---|---|---|
| 7.1 | Deleting users/organizations used `window.confirm`: unstyled, blocks the thread, not testable, no consequences listed beyond text. | Accidental data loss; inconsistent UI. | Accessible `alertdialog` (`ConfirmDialog` on `Modal`): labelled, described, focus starts on Cancel, Tab trapped, Escape closes, focus returns to the trigger, busy state, clear consequence text. | High | Done |
| 7.2 | Password reset modal: overlay `div` with click handlers, no role, no focus management or Escape. | Keyboard and screen-reader users could tab behind the modal. | Same `Modal` component (`role=dialog`, `aria-modal`, focus trap). | High | Done |

## 8. Accessibility details (WCAG 2.1/2.2)

| # | Problem | Why it matters | Fix | Severity | Status |
|---|---|---|---|---|---|
| 8.1 | `outline: none` on inputs/buttons with only a faint box-shadow; no `:focus-visible` anywhere. | Keyboard users lose their place (2.4.7). | Global `:focus-visible` 3 px ring (white on gradient surfaces). | Critical | Done |
| 8.2 | Icon-only buttons (mic, devices, disconnect) had only `title`; state not exposed. | No accessible name/state (4.1.2). | `aria-label`, `aria-pressed` for mute, `aria-haspopup`/`aria-expanded` for the device picker, `aria-pressed` on the current device, Escape closes the picker; decorative SVGs `aria-hidden`. | High | Done |
| 8.2b | Status text ("Listening...", "Lia is thinking...") and the transcript were silent for screen readers. | Voice app state is invisible to AT users. | Status `role="status"`; transcript `role="log"` + `aria-live="polite"`, focusable for scrolling; emoji avatars hidden, "You:/Lia:" speaker prefix added. | High | Done |
| 8.3 | Error/success banners were inserted into the DOM without live regions. | Changes are not announced (4.1.3). | Persistent `role="alert"` / `role="status"` containers wrap the messages. | High | Done |
| 8.4 | Tables lacked names and `scope`; clickable-looking rows. | Poor table navigation. | `aria-label` per table, `scope="col"`, row-action buttons carry the row in their name ("Delete bob@x.co"). | Medium | Done |
| 8.5 | Emoji used as meaningful icons in labels ("🎤 You are speaking"). | Read aloud inconsistently. | Removed from labels; kept only as hidden decoration. | Low | Done |
| 8.6 | Animations ran regardless of OS setting. | Vestibular disorders (2.3.3). | `prefers-reduced-motion` neutralises animations and transitions. | Medium | Done |
| 8.7 | Page title was always "Lia"; no `lang` issue (present). | Orientation for screen-reader users. | Per-view `document.title`. | Low | Done |
| 8.8 | `autoFocus` on the reset password field was the only focus management. | See 7.2. | Modal handles initial focus and restore. | Medium | Done (via Modal) |

## 9. Security/privacy-relevant UI findings

| # | Problem | Fix | Severity | Status |
|---|---|---|---|---|
| 9.1 | `console.log` of login responses (including the access token), the user object, the LiveKit token response and request params. | Removed; error logging only emits messages, never payloads. | Critical | Done |
| 9.2 | `JSON.parse(localStorage.getItem('user'))` without try/catch crashes the whole app on corrupted storage; storage access itself can throw. | `lib/storage.js` guards every read/write and validates the shape. | High | Done |
| 9.3 | Expired/invalid tokens left the user on a screen full of failing requests. | Axios response interceptor: on 401 (except `/login`) clear the session and emit an event; `App` returns to the login screen. | High | Done |
| 9.4 | Connector secrets will be returned as `********`; the old form would have saved that literal value back. | `stripMaskedFields` is applied before saving (ConnectorSettings, Admin create/edit). | High | Done |
| 9.5 | Token is kept in `localStorage` (readable by any XSS). | Not changed (needs an httpOnly-cookie backend change); noted as a risk. | Medium | Open |

## 10. API base URL (behaviour kept)

The missing `lib/api.js` was reconstructed to match the deployment files: `VITE_API_URL` (docker-compose: `http://localhost:5000` in development, `https://${DOMAIN_NAME}/api` in production, nginx rewrites `/api/` to the backend). Without `VITE_API_URL` the base is `/api`, which the existing Vite dev proxy forwards (and strips) to `localhost:5001`. The mobile app already uses the same pattern.

## Not done / recommendations

* Replace `useState` navigation with a router so Back/Refresh/deep links work (changes app structure).
* Move the auth token to an httpOnly cookie (backend change).
* Dark-mode theme: tokens are now centralised, so adding `prefers-color-scheme` overrides is straightforward.
* Run a full automated a11y scan (`@axe-core/playwright`) in CI; the E2E suite currently contains hand-written smoke checks only, to avoid a new dependency.
* `three`, `@react-three/fiber`, `@react-three/drei` and `@readyplayerme/visage` are declared in `package.json` but are not imported anywhere in `src`; consider removing them.
