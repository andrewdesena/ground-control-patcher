# gc-modder

Prose-lint wired automatically for this project.

<!-- BEGIN:writing-style -->
# Writing style (client-facing and public content)

- **No em-dashes (—).** Do not use em-dashes in client-facing or public-facing content:
  web copy, marketing pages, docs, emails to clients, proposals, blog posts. They read as
  AI-generated in 2026. Use a hyphen or restructure the sentence instead.
  - Em-dashes ARE fine in internal notes and chat between Drew and Scarlet. This rule is
    about anything a client or the public will read.
- **Limit the word "actually".** Avoid it in public-facing copy. It reads pretentious.
  Restructure the sentence instead. (Context-dependent: fine in casual internal chat.)

## Enforcement

- Before finishing any content work, run the style linter:
  `npm run lint:style` (or `bash scripts/prose-lint.sh <files-or-dir>`).
- Fix anything it flags before delivering client-facing content.
- The linter is a proofreader, not a judge: review each hit and decide. It does not auto-edit.
<!-- END:writing-style -->
