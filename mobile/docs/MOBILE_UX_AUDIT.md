# Mobile UX / accessibility audit (Expo / React Native app)

Scope: `mobile/` (Login, Voice, Admin, Connector Settings, navigation, `src/lib`).
Method: static review of the code against HCI / mobile basics (touch targets, labels, keyboards, states, contrast, dynamic type, safe areas, announcements) and the behaviour of the already-modernised web app (`frontend/docs/UI_UX_AUDIT.md`), then fixes plus automated tests.

Status legend: **Done** = implemented and covered by a Jest test; **Done (not device-verified)** = implemented but only checkable on a device/screen reader; **Not done** = deliberately left, with reason.

Severity: **High** = blocks users or risks data loss, **Medium** = real usability/accessibility barrier, **Low** = polish.

## 1. Findings and fixes

### Correctness / data-safety (found while auditing)

| # | Finding | Why it matters | Fix | Sev. | Status |
|---|---------|----------------|-----|------|--------|
| 1 | `api.js` called `.replace` on `process.env.EXPO_PUBLIC_API_URL` at import time. Without the variable the whole app crashed on start. | White screen on any build missing the variable. | `resolveBaseURL()` trims, strips trailing slashes and falls back to `http://localhost:5000` (documented in `src/lib/api.js`; use the LAN IP or `10.0.2.2` on devices/emulators). | High | Done |
| 2 | Editing an organization always sent `connector_config` (`org.connector_config \|\| {}` is truthy), so saving a name change wiped the stored credentials. The code comment even said it should be omitted. | Silent data loss. | Same rule as the web admin: `connector_config` is sent only when a value was typed or the type changed; masked values (`********`) are always stripped (`stripMaskedFields`). | High | Done |
| 3 | Connector Settings sent the form as-is. | Would write the literal mask back as the new secret. | Loads the stored (masked) config via `GET /organizations/:id`, strips masked fields before `PATCH`. | High | Done |
| 4 | A 401 only cleared storage; the user stayed on a screen that could no longer work. | Dead-end session after token expiry. | Interceptor clears the session and notifies `AppNavigator`, which resets navigation to Login. 401 on `/login` (wrong password) is not treated as an expired session. | High | Done (reset call unit-tested with a stubbed navigation ref; real navigator not exercised) |
| 5 | `ConnectorFields` was declared **inside** `AdminScreen`, so every keystroke remounted the inputs and dismissed the keyboard. | Cannot type a connector value on a phone. | Moved to a module-level component (`src/components/ConnectorFields.jsx`). | High | Done (behaviour verified structurally; keyboard behaviour needs a device) |
| 6 | Create-user allowed "None" for organization, but the backend answers `org_id is required`. Validation was only "email and password non-empty". | Avoidable server error; no password rule. | Mirrors the web `validateNewUser` (email format, password >= 6, organization required). | Medium | Done |
| 7 | Corrupted/absent `user` JSON crashed in three screens (`JSON.parse` in effects). | Crash loop after a bad write. | `getStoredUser()` returns `null` for missing/corrupt/non-object data; `AppNavigator` falls back to Login. | Medium | Done |
| 8 | Error text came from `err.response?.data?.error \|\| err.message` in 10 places (leaks axios internals such as "Request failed with status code 500"). | Unhelpful, inconsistent messages. | Single `getErrorMessage(err, fallback)` (backend `error`/`msg`, "Cannot reach the server", fallback) shared with the web app semantics. | Medium | Done |
| 9 | Admin feedback (including errors) disappeared after 3 s, and errors raised inside an open modal were hidden behind it. | Errors unreadable, especially with a screen reader. | Errors persist until the next action; success clears after 4 s; modal errors are shown inside the modal (and not duplicated behind it). | Medium | Done |
| 10 | No logging of tokens/user data was found (`console.*` is absent); ESLint `no-console: error` now guards it. | Privacy. | Lint rule. | Low | Done |

### Touch targets

| # | Finding | Fix | Sev. | Status |
|---|---------|-----|------|--------|
| 11 | Header buttons, card actions (`paddingVertical: 6`), chips (`8`), tabs and Back link were 26-36 pt tall. | Shared `Button` (min height 44, extra `hitSlop`), chips/tabs/back/header buttons `minHeight: 44`; `MIN_TOUCH` and `hitSlopFor()` in `theme.js`. | Medium | Done (sizes asserted via style tokens; not measured on device) |

### Screen reader semantics

| # | Finding | Fix | Sev. | Status |
|---|---------|-----|------|--------|
| 12 | No `accessibilityRole/Label/State/Hint` anywhere. Icon-only buttons (cog, refresh, X) read as "button" or an emoji name. | Roles on every control; labels for icon buttons ("Connector settings", "Retry connecting", "End conversation"); decorative emoji hidden from the accessibility tree; destructive buttons carry the hint "Asks for confirmation first" and name the item ("Delete Acme"). | High | Done (RNTL role/label queries; real TalkBack/VoiceOver not run) |
| 13 | Tab bar and chip selectors had no selected state. | `tablist`/`tab` with `selected`; chips are a `radiogroup` of `radio` items with `selected/checked`. | Medium | Done |
| 14 | Errors, success messages and the connection status were silent. | `Banner` uses `accessibilityRole="alert"` + `accessibilityLiveRegion` (assertive for errors, polite for success); field errors are polite live regions; Voice status and error are live regions; loading indicators are labelled. | High | Done (not device-verified) |
| 15 | Voice screen: the mic button was a plain touchable whose state was only an emoji + "Mute"/"Unmute" text. | Exposed as a `switch` named "Microphone" with `checked` state and a hint; each toggle is announced via `AccessibilityInfo.announceForAccessibility` ("Microphone on/muted", and an error message if toggling fails); transcript bubbles have labels "You: ..." / "Lia: ...". | High | Done (announcement is asserted via a spy; audible output not verified) |
| 16 | Section titles/screen titles were plain text. | `accessibilityRole="header"` on titles, modal headers; modals set `accessibilityViewIsModal`. | Low | Done |

### Forms and keyboards

| # | Finding | Fix | Sev. | Status |
|---|---------|-----|------|--------|
| 17 | Labels were visual only (inputs had no `accessibilityLabel`); required marked only by `*`. | `Field` component: visible label + `accessibilityLabel` ("Email, required"), hint, inline error with `accessibilityRole="alert"`. | Medium | Done |
| 18 | Missing keyboard / autofill hints and no way to move between fields or submit from the keyboard. | `keyboardType`, `autoCapitalize="none"`, `autoCorrect={false}`, `autoComplete` (`email`, `current-password`, `new-password`), `textContentType`, `returnKeyType` (`next`/`go`/`done`) with focus chaining and `onSubmitEditing` submit on Login, user, password-reset and connector forms. Third-party credentials use `autoComplete="off"` so they are not offered to the OS password manager. | Medium | Done |
| 19 | Inline validation: only a single generic banner. | Per-field messages from `src/lib/validation.js` (same rules and wording as the web); the first invalid state is announced because errors are live regions. | Medium | Done |
| 20 | `secureTextEntry` | Already used for passwords and secret connector fields; retained and unit-tested. | - | Done |
| 21 | Double submit: only some forms disabled their button; text inputs stayed editable while saving. | Buttons are `disabled` + `busy` while a request runs, handlers ignore re-entry, inputs become non-editable. | Medium | Done |
| 22 | Keyboard covered inputs on Admin/Connector forms and in modals. | `KeyboardAvoidingView` + `ScrollView keyboardShouldPersistTaps="handled"` on Login (kept), Admin tabs, Connector Settings and all modals. | Medium | Done (not device-verified) |

### States, lists and confirmations

| # | Finding | Fix | Sev. | Status |
|---|---------|-----|------|--------|
| 23 | Lists were `ScrollView`+`map`, no empty state, no pull-to-refresh; dashboard failure had no retry. | `FlatList` with `RefreshControl`, empty-state texts, dashboard error banner with Retry; the refresh button shows a busy state. | Medium | Done |
| 24 | Delete confirmations existed (`Alert.alert`) but had no tests and generic titles. | Kept, wording consistent, covered by tests (cancel does nothing; only the destructive button calls the API). | Medium | Done |
| 25 | Loading states: spinner without label; Connector Settings had none for the initial fetch. | Labelled, live-region spinners; button spinners get labels. | Low | Done |

### Visual design

| # | Finding | Fix | Sev. | Status |
|---|---------|-----|------|--------|
| 26 | Colours were hard-coded in six files (`#666`, `#555` placeholders, `#888` text, white on `#667eea`). Computed contrast: `#555` on `#0f0f1a` ~2.6:1, `#666` ~3.3:1, white on `#667eea` ~3.7:1. | New `src/theme.js` with semantic tokens (text `#fff`/`#c4c4d8`/`#9a9ab8`, placeholder `#8a8aa8`, button fill `#4f5fd6`, danger `#f87171`, success `#34d399`). All pairs >= 4.5:1; `theme.test.js` recomputes the ratios so edits cannot regress. | Medium | Done |
| 27 | Font sizes 11-13 px and fixed-height controls; `allowFontScaling` left default with no cap. | Minimum text size 12-14, controls use `minHeight` (grow with text), `applyFontScaleCap()` keeps scaling enabled and caps it at 1.6x. | Low | Done (layout at max scale not visually checked) |
| 28 | Safe areas: screens already used `SafeAreaView`/`SafeAreaProvider`. | Kept; `StatusBar style="light"` added for the dark theme. | Low | Done |

### Not done / out of scope

| # | Item | Reason | Sev. |
|---|------|--------|------|
| 29 | Light theme / `userInterfaceStyle` is fixed to dark in `app.json`. | Product decision; tokens are centralised so a light palette is now cheap. | Low |
| 30 | `react/prop-types` ESLint rule is off. | The app is plain JS without PropTypes (and `prop-types` is not a direct dependency); adding it would be a new runtime dependency. | Low |
| 31 | Reduced-motion handling for the waveform animation. | Needs `AccessibilityInfo.isReduceMotionEnabled` plumbing; low value because the waveform is decorative and hidden from screen readers. | Low |
| 32 | Landscape / tablet layouts (`orientation: portrait` in `app.json`). | Out of scope. | Low |
| 33 | Real-device verification (TalkBack, VoiceScreen with a live LiveKit room, keyboard behaviour, measured touch sizes, visual regression). | No emulator/device was run for this change. | - |

## 2. Code structure changes

- `src/theme.js` (tokens, `MIN_TOUCH`, `hitSlopFor`, contrast helpers), `src/lib/validation.js`, `src/lib/connector.js`, `src/lib/fontScaling.js`.
- `src/components/ui.jsx` (`Button`, `Field`, `Banner`, `ChoiceChips`) and `ConnectorFields.jsx`.
- `AdminScreen.jsx` (595 lines, 5 inline modals/forms) is now ~300 lines of state + handlers, with `screens/admin/{OrganizationForm,UserForm,ResetPasswordModal,FormModal,Tabs}.jsx`. API calls, payloads and endpoints are unchanged except for fixes 2 and 6.
- API contract unchanged: `/login`, `/getToken`, `/admin/*`, `/organizations/:id` (GET, new read-only call in Connector Settings), `/organizations/:id/connector` (PATCH).

## 3. Tooling

- `npm test` (Jest, `jest-expo` preset, `@testing-library/react-native` with its built-in matchers), `npm run test:coverage` (global thresholds 90/80/85/90 for statements/branches/functions/lines; `*.styles.js` excluded), `npm run lint` (ESLint 9 flat config with `eslint-plugin-react`, `react-hooks`, `no-console`).
- Native modules are mocked in `jest.setup.js` (AsyncStorage official mock, safe-area-context official mock, `react-native-get-random-values`) and inside `VoiceScreen.test.jsx` (`@livekit/react-native`, `livekit-client`), so LiveKit's native rendering internals are not exercised by tests.
