"""Worked example: monthly payroll on top of backdate.

Salaries, FTE and state are effective-dated facts on ``employee:<id>``.
Withholding rates are facts on ``taxrate:<state>``. Gross pay and
withholding for a month are derivations, so a backdated raise or rate
change restates every month it touches.
"""
