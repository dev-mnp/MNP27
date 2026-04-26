# User Management

## What this module is

User Management creates users, assigns roles, and controls module-level permissions. The left menu and protected views depend on this permission system.

## Main code files

- Views: `core/user_management/views.py`
- URLs: `core/user_management/urls.py`
- Templates: `core/templates/user_management/`
- Permission mixin: `core/shared/permissions.py`
- User and permission models: `AppUser`, `UserModulePermission`

## Main tables

- `app_users`
- `user_module_permissions`

## Important fields

- `AppUser.id`: UUID primary key.
- `AppUser.email`: login username.
- `AppUser.role`: `admin`, `editor`, or `viewer`.
- `AppUser.status`: active or inactive.
- `UserModulePermission.module_key`: module name such as `dashboard`.
- Permission booleans: `can_view`, `can_create_edit`, `can_delete`, `can_submit`, `can_reopen`, `can_export`, `can_upload_replace`, `can_reset_password`, `can_view_page_2`.

## Permission behavior

- Superusers pass every permission check.
- Inactive users fail permission checks.
- Role defaults are defined in `ROLE_MODULE_PERMISSION_DEFAULTS`.
- Per-user permission rows override role defaults.
- Sidebar visibility is based on resolved module permissions.

## Debug checklist

- User cannot see a menu item: check `user_module_permissions` and role defaults.
- User can see but cannot perform action: check action-specific permission.
- Permissions seem stale: clear cache key `mnp27:user_module_perms:*` or re-login.
- New module missing: add it to `ModuleKeyChoices`, `MODULE_PERMISSION_DEFINITIONS`, sidebar, view mixin, and user guide modules.

## Screen fields

- Email: login id.
- First name and last name: display name.
- Role: admin, editor, or viewer.
- Status: active or inactive.
- Module permissions: one row per menu module.
- Permission checkboxes: view, create/edit, delete, submit, reopen, export, upload/replace, reset password, view page 2.

## Buttons and actions

- Create User adds a new app user.
- Edit changes user details and permissions.
- Reset Password sets a new password for the selected user.
- Delete removes a user where allowed.
- Save Permissions stores module access.

## Common errors and fixes

- User sees old permissions: permission cache may still be active; clear cache or ask user to log out and log in.
- Dashboard missing from options: check `MODULE_PERMISSION_DEFINITIONS`.
- View works but action fails: check action-specific boolean, not only `can_view`.
