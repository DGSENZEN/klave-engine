## 2026-10-27 · Every auth screen uses the split frame with the pond, not only sign-in
- Decided by: Claude (default)
- Why: AuthFrame exists so a person recovering a password meets the same layout they signed in with; giving only /bienvenida the pond would break that.
- Rejected: pond on /bienvenida alone, because it makes recovery, reset, invitation and verification look like a different product.
- Rests on: apps/web/app/(acceso)/layout.tsx doc comment; request to put the pond on the side with the login panel on the other.

## 2026-10-27 · Koi are drawn in Klave's tokens (ink bodies, cobalt markings), not upstream orange
- Decided by: Claude (default)
- Why: the interface is deliberately near-monochrome with one cobalt accent; orange koi would be a second accent on the first screen anyone sees.
- Rejected: upstream red-orange palette; a separate hand-picked koi palette, because raw colours belong only in globals.css.
- Rests on: app/globals.css header; "less colours, less distraction, sharp and expensive" direction for the web revamp.

## 2026-10-27 · Below 1024 px the pond is not shown
- Decided by: Claude (default)
- Why: on a phone the form needs the whole width, and an animation loop behind a login costs battery on the oldest devices for no task value.
- Rejected: a short pond band above the form on phones.
- Rests on: apps/web/app/(acceso)/layout.tsx (`lg:flex` aside).

## 2026-10-27 · Sign-up is its own route (/registro), not a tab on sign-in
- Decided by: Claude (default)
- Why: a route can be linked to directly and survives the back button; a tab could not.
- Rejected: keeping Entrar / Crear cuenta tabs in one card.
- Rests on: apps/web/app/(acceso)/registro/page.tsx; apps/web/app/(acceso)/bienvenida/page.tsx.

## 2026-10-27 · Every new-password field in the web asks for 10 characters
- Decided by: Claude (default)
- Why: the API rejects anything shorter on register and reset, while the reset and first-admin forms said 8, so a 9-character password passed the form and failed on the server.
- Rejected: leaving each form's own number.
- Rests on: apps/api/auth/passwords.py (MIN_LENGTH = 10); PASSWORD_MIN in apps/web/lib/session.ts.

## 2026-10-27 · The access screens share one layout, so the pond survives navigation
- Decided by: the designer
- Why: each page rendered its own frame, so every move between sign in, sign up and recovery started a new pond.
- Rejected: keeping the frame per page and caching pond state between mounts.
- Rests on: apps/web/app/(acceso)/layout.tsx; request that the pond stop re-rendering.

## 2026-10-27 · Sign-in and sign-up are one click apart through an Entrar / Crear cuenta switch, with no subtitles
- Decided by: the designer
- Why: the request asked for less text and an easier way to just sign in or sign up.
- Rejected: an email-first screen that decides sign-in or sign-up by whether the address exists, because it tells anyone which emails have accounts.
- Rests on: AuthSwitch in apps/web/components/AuthFrame.tsx.

## 2026-10-27 · Recovery is "¿No puedes entrar?": an emailed link first, then Google and an admin-issued link
- Decided by: the designer
- Why: losing access is not always a forgotten password; the page offers every way back in that the product supports.
- Rejected: telling people an admin can change their email, because Equipo can only issue a recovery link.
- Rests on: apps/web/app/(acceso)/recuperar/page.tsx; apps/web/app/equipo/page.tsx (issueRecoveryLink).

## 2026-10-27 · New-password forms have one field with show/hide, not a repeat field
- Decided by: Claude (default)
- Why: the show/hide toggle lets people check what they typed, which is what the repeat field was for, at the cost of one less field.
- Rejected: keeping "Repite la contraseña" on reset and invitation.
- Rests on: PasswordField in apps/web/components/AuthFields.tsx.

## 2026-10-27 · Accepting an invitation applies the same password policy as register and reset
- Decided by: the designer
- Why: invitation accept only checked 8 characters and skipped the common-password and own-email checks.
- Rejected: leaving invitations on the looser rule.
- Rests on: apps/api/auth/invitations.py; tests/test_auth_loop.py::test_invitation_accept_applies_the_password_policy.
