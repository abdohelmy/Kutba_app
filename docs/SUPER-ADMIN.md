# Owner dashboard

Open the web app, choose **Mosque sign in**, and use the owner account. The owner
is routed to `#owner`; this dashboard works on phones, tablets, and desktop.
The native apps are for mosque admins and readers; owner controls are web-only.

New mosque accounts are pending until approved. Existing mosque accounts keep
their approval status during migration. The legacy permission password no longer
grants access, including in older installed apps.

## Controls

- Approve/reject requests, rename/suspend/restore mosques, disable individual admins.
- Remove a mosque by archiving it and disabling its accounts. Khutbas and authorship
  are preserved; public readers cannot access archived or suspended mosques.
- Review/edit any translation, hide/show published khutbas, and permanently delete
  khutbas. Deleting English also deletes Danish. Active jobs cannot be deleted.
- Add/edit global glossary definitions, promote mosque entries, remove overrides
  or mosque-specific entries. Removing an override restores the CSV definition.
- Approve or reject mosque-specific entries and post-publication global submissions.
  New or edited submissions are pending and cannot be used until approved.
  Existing entries stay approved during migration. Pending entries appear first.
  Rejected mosque terms can be edited and resubmitted; rejected global submissions
  appear again on the missing-definition screen for correction.
- See translation failures and ongoing jobs, and the last 200 owner actions.
- Issue single-use, 30-minute password-reset links. New links invalidate earlier
  ones; using a link invalidates the account's existing login sessions.

Offline reader copies already downloaded cannot be remotely erased.
Mosque admins can edit their mosque name and city in Settings.

## Initial account

After backend startup has applied migrations, run in the server backend directory:

```sh
/opt/khutba/.venv/bin/python -m app.manage_owner --username abdo --email abdohelmy1995@gmail.com
```

This creates one owner with an unknown random password and prints a one-time
password setup link. It refuses to run if an owner already exists. No public
endpoint can register an owner or assign the owner role.

## Email delivery

Configure these variables in the server's existing backend environment:

```ini
KHUTBA_SMTP_HOST=your-smtp-host
KHUTBA_SMTP_PORT=587
KHUTBA_SMTP_USERNAME=your-smtp-username
KHUTBA_SMTP_PASSWORD=your-smtp-password
KHUTBA_SMTP_FROM=your-verified-sender
KHUTBA_PUBLIC_WEB_URL=https://khutba-reader.abdohelmy1995.chatgpt.site
```

The implementation uses authenticated SMTP with STARTTLS. Restart the API after
configuration. New registration notifications are sent to active owners' contact
emails; password recovery sends to the account's saved email. Without SMTP,
dashboard approvals and manually shared reset links work, but automatic email
notifications and self-service email recovery do not. Never commit SMTP secrets.

The VM's Friday operating schedule also applies to the dashboard and recovery.
Back up the database and changed backend files before deployment.
