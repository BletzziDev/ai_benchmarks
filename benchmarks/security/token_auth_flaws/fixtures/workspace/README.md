# authkit

Shared authentication library used by the Acme web apps: signed access tokens (`TokenService`),
signed session cookies (`SessionCodec`) and password storage (`UserStore`, `register`,
`authenticate`). Run tests with `python -m pytest -q`.

## Operational facts

- Access tokens are presented by browsers and mobile apps over the public internet.
- Session cookies are stored client-side.
- The users table (~2M rows) was imported from the legacy PHP application; those rows still hold
  the legacy hash format. Forcing a password reset for all users is not acceptable to the
  business. Invalidating existing session cookies (users log in again) is acceptable.
- Internal services were moved to mTLS last quarter and now use regular signed tokens.
