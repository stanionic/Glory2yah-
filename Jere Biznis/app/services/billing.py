from calendar import monthrange

def add_months(dt, months):
    m=dt.month-1+months
    y=dt.year+m//12
    m=m%12+1
    return dt.replace(year=y, month=m, day=min(dt.day, monthrange(y,m)[1]))

def amount_for_months(months, price):
    months=int(months)
    if months<1: raise ValueError("months must be >= 1")
    return months*int(price)

def current_status(now, trial_end, expiration):
    if now<trial_end: return "TRIAL"
    if expiration and now<expiration:
        return "EXPIRING_SOON" if (expiration-now).days<=7 else "ACTIVE"
    return "EXPIRED"

def next_expiration(now, trial_end, expiration, months):
    base=expiration if expiration and expiration>now else (trial_end if now<trial_end else now)
    return add_months(base, months)

def login_reminder(now, trial_end, expiration):
    return {
        "required": True,
        "status": current_status(now,trial_end,expiration),
        "days_remaining": max(0,((trial_end if now<trial_end else expiration)-now).days)
            if (now<trial_end or expiration) else 0
    }
