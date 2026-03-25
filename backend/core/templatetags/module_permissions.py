from django import template

register = template.Library()


@register.simple_tag
def has_module_permission(user, module_key, action="view"):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    checker = getattr(user, "has_module_permission", None)
    if not callable(checker):
        return False
    return checker(module_key, action)
