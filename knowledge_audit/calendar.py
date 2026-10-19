"""Jalali civil-date conversion using Borkowski's cycle table.

The start-of-year calculation is adapted from jalaali-js (MIT); see NOTICE.
Only 1200..1600 is supported, within its documented Gregorian/Intl agreement.
"""
from datetime import date, timedelta

from knowledge_audit.privacy import AuditError


def _new_year(year: int) -> date:
    if not 1200 <= year <= 1601:
        raise AuditError("jalali_year_out_of_range")
    breaks = (-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181,
              1210, 1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178)
    previous, leaps = breaks[0], -14
    for boundary in breaks[1:]:
        jump = boundary - previous
        if year < boundary:
            break
        leaps += jump // 33 * 8 + jump % 33 // 4
        previous = boundary
    offset = year - previous
    leaps += offset // 33 * 8 + (offset % 33 + 3) // 4
    if jump % 33 == 4 and jump - offset == 4:
        leaps += 1
    gregorian_year = year + 621
    gregorian_leaps = gregorian_year // 4 - ((gregorian_year // 100 + 1) * 3) // 4 - 150
    return date(gregorian_year, 3, 20 + leaps - gregorian_leaps)


def jalali_date(year: int, month: int, day: int) -> date:
    if not 1200 <= year <= 1600 or not 1 <= month <= 12:
        raise AuditError("invalid_jalali_date")
    start = _new_year(year)
    length = 31 if month <= 6 else 30 if month <= 11 else (_new_year(year + 1) - start).days - 336
    if not 1 <= day <= length:
        raise AuditError("invalid_jalali_date")
    preceding = (month - 1) * 31 if month <= 7 else 186 + (month - 7) * 30
    return start + timedelta(days=preceding + day - 1)
