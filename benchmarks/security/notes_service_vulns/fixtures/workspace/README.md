# notesvc

Multi-tenant notes service. The HTTP layer is abstracted (`notesvc.http`) so the app can be
driven in-process: `app.handle(Request(...)) -> Response`. Run tests with `python -m pytest -q`.

## Deployment notes (ops)

- The platform injects configuration through environment variables. Available today:
  `NOTES_SECRET_KEY` (token signing key, 48 random characters, rotated by ops) and
  `NOTES_DEBUG` (`1` enables verbose logs; enabled on staging, sometimes on production while
  debugging incidents).
- Logs are shipped to a third-party log aggregator that the whole engineering org can read.
- Attachments live on a shared volume (`storage_dir`) that also holds other services' files.
