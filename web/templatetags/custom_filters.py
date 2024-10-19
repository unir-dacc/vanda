from django import template

register = template.Library()


@register.filter
def split(value, delimiter=":", index=0):
    parts = value.split(delimiter)
    try:
        return parts[index]
    except IndexError:
        return ""
