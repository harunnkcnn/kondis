from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def kg(value) -> str:
    """12.50 -> 12,5 / 80.00 -> 80 (Turkish-style decimal comma handled by l10n elsewhere)."""
    if value in (None, ""):
        return ""
    number = Decimal(str(value)).normalize()
    text = format(number, "f")
    return text


@register.filter
def get_item(mapping, key):
    return mapping.get(key)


@register.simple_tag
def sparkline(points, width=280, height=64):
    """Inline SVG polyline for a list of (date, value) pairs."""
    values = [float(v) for _, v in points]
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    step = width / (len(values) - 1)
    coords = " ".join(f"{i * step:.1f},{height - 6 - (v - lo) / span * (height - 12):.1f}" for i, v in enumerate(values))
    from django.utils.html import format_html

    return format_html(
        '<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none" role="img" aria-label="{label}">'
        '<polyline points="{c}" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/></svg>',
        w=width,
        h=height,
        c=coords,
        label=f"{values[0]:g} → {values[-1]:g} kg",
    )


@register.filter
def plate(weight) -> str:
    """Load bracket shown as a bumper-plate colour: 100+ red, 60+ blue, 40+ yellow, 20+ green, else white."""
    w = Decimal(str(weight or 0))
    for limit, colour in ((100, "25"), (60, "20"), (40, "15"), (20, "10")):
        if w >= limit:
            return colour
    return "5"
