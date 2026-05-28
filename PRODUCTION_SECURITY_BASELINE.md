# Production Security Baseline

This app should only be treated as a real student-information workflow tool when all of the following are in place:

## Identity and access

- Staff accounts use school-managed identities wherever possible.
- Staff and admin accounts use multi-factor authentication.
- Shared staff accounts are not allowed.
- New staff access requires approval from a designated school owner.
- Departed staff accounts are disabled on the same day access ends.

## Hosting

- Production runs with `DJANGO_DEBUG=False`.
- Production uses HTTPS only.
- Production uses a managed database service rather than local SQLite.
- Backups are encrypted, tested, and stored separately from the application host.
- Secrets are managed as environment variables or through a secrets manager.
- Public `/media/` mappings are not used for sensitive student files.

## Operational controls

- Access reviews happen at least monthly.
- Security logs are reviewed regularly by an assigned owner.
- Export and backup activity is reviewed and justified.
- Incident response contacts are documented and current.

## Data handling

- The school defines what information belongs here versus in the official SIS/LMS.
- Retention and deletion rules are documented.
- Real student data is not used in non-production environments.

## Release controls

- Changes are tested before release.
- Security validation runs automatically on repository changes.
- Production changes are documented with who approved them and when they were deployed.
