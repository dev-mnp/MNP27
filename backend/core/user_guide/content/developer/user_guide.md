# User Guide

## What this module is

User Guide is the in-app documentation reader. It loads Markdown files from disk and renders them inside the existing app UI.

## Main code files

- View: `core/user_guide/views.py`
- URL: `core/user_guide/urls.py`
- Template: `core/templates/user_guide/user_guide.html`
- End-user Markdown: `core/user_guide/content/enduser/`
- Developer Markdown: `core/user_guide/content/developer/`

## How rendering works

- `GUIDE_MODULES` defines section order, slug, and title.
- For each slug, the view reads one end-user Markdown file and one developer Markdown file.
- `_render_markdown()` supports the simple subset used by these guides: headings, paragraphs, bullet lists, bold text, and inline code.

## Adding a module guide

- Add a slug and title to `GUIDE_MODULES`.
- Create `core/user_guide/content/enduser/<slug>.md`.
- Create `core/user_guide/content/developer/<slug>.md`.
- Run `manage.py check`.

## Debug checklist

- Guide section missing: check `GUIDE_MODULES`.
- Content says Missing Guide: check filename and folder.
- Formatting odd: keep Markdown simple and avoid nested bullets.

## Supported Markdown fields

- `# Heading` renders as main section heading.
- `## Heading` renders as subheading.
- `### Heading` renders as smaller subheading.
- `- Bullet` renders as a bullet list.
- `**text**` renders bold.
- `code` wrapped in backticks renders as inline code.

## Buttons and actions

- Sidebar module links switch between guide sections.
- End User column shows files from `content/enduser`.
- Developer column shows files from `content/developer`.
- No save button exists because files are edited in the codebase.

## Common errors and fixes

- HTML appears escaped incorrectly: check `_inline_markdown()`.
- New markdown file not shown: add the slug to `GUIDE_MODULES`.
- Page starts on wrong section: check default hash in the template script.
