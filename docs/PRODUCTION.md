# Production checklist

Do not publish real sermons from the starter configuration until these controls are in place.

## Religious-content quality

- Appoint qualified reviewers for Arabic and every target language.
- Approve an explicit source registry: title, edition, translator, publisher, language, checksum,
  effective date, and retired date.
- Build a gold evaluation set containing Qur'an, hadith, legal terminology, negation, names, dates,
  numbers, rhetorical passages, and known ambiguous phrases.
- Evaluate every provider/model/prompt change before deployment and retain the exact provider/model
  identifiers used for each sermon.
- Add source-version pinning, reviewer identity, approval timestamp, and immutable publication audit.
- Require a second reviewer for segments carrying verifier warnings or Qur'an/hadith quotations.
- Obtain production Quran Foundation credentials and a Sunnah.com API key; monitor their availability
  and treat lookup failures as review blockers, never as permission to invent canonical wording.
- Add a correction/retraction workflow for already published sermons.

## Platform and security

- Use PostgreSQL, Alembic migrations, object storage, a durable job queue, retries, and idempotency keys.
- Put the API behind HTTPS, rate limiting, request-size limits, malware scanning, and centralized
  structured logs with no sermon/API-key leakage.
- Store secrets in a secret manager; rotate JWT and provider keys. Use asymmetric access tokens or an
  external identity provider for a multi-instance deployment.
- Add admin invitation, password reset/recovery, MFA, mosque-admin removal, and session
  revocation. Public self-registration must never create an admin.
- Replace in-memory mobile tokens with a reviewed Keychain/Keystore-backed session design if
  persistent login is required.
- Add backups, restore drills, privacy retention rules, account deletion, incident response, and
  monitoring for stuck or failed translation jobs.
- Run SAST, dependency scanning, API abuse tests, Android lint/tests, iOS build/tests, and an
  independent penetration test before launch.

## Documents and retrieval

- Move the existing local OCR subprocess into an isolated worker/container and add page-level
  confidence. Keep the mandatory reviewer comparison to the original page image.
- Keep PDF/DOCX parsing isolated and add malware scanning before storing production uploads.
- Add page/paragraph coordinates to citations so reviewers can open the exact source location.
- Add multilingual embeddings only after evaluating retrieval recall on the mosque's approved source
  corpus; keep a lexical/exact-match path for Qur'an verses, hadith IDs, and terminology.
- Reject a translation job when required source categories are missing instead of treating any source
  document as sufficient.
