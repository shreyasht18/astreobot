import os
import re
import html
import asyncio
import calendar
import logging
from datetime import datetime, timedelta, timezone

import swisseph as swe
from telegram import Update, InlineKeyboardButton as Btn, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
from keep_alive import keep_alive  # Keeps Render awake!

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("astrobot")

TOKEN = os.environ.get("TELEGRAM_TOKEN", "8792120272:AAHvhMHbQNqg5lwAnwPXtPuf3R1mTVTHQUc")
DEFAULT_TZ_MIN = 330  # IST (UTC+5:30). Users can change it with /tz

# ───────────────────────── DATA ─────────────────────────
NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni",
    "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha",
    "Anuradha", "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha",
    "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada",
    "Uttara Bhadrapada", "Revati",
]
ZODIAC = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
          "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
SIGN_SYM = ["♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓"]
SIGN_LORD = ["Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury",
             "Venus", "Mars", "Jupiter", "Saturn", "Saturn", "Jupiter"]

EMOJI = {"Sun": "☀️", "Moon": "🌙", "Mars": "🔴", "Mercury": "🟢", "Jupiter": "🟡",
         "Venus": "💖", "Saturn": "🪐", "Rahu": "🌪️", "Ketu": "☄️"}
BODIES = {"Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS, "Mercury": swe.MERCURY,
          "Jupiter": swe.JUPITER, "Venus": swe.VENUS, "Saturn": swe.SATURN,
          "Rahu": swe.TRUE_NODE}
ORDER = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]

EXALT = {"Sun": 0, "Moon": 1, "Mars": 9, "Mercury": 5, "Jupiter": 3,
         "Venus": 11, "Saturn": 6, "Rahu": 1, "Ketu": 7}
OWN = {"Sun": [4], "Moon": [3], "Mars": [0, 7], "Mercury": [2, 5], "Jupiter": [8, 11],
       "Venus": [1, 6], "Saturn": [9, 10]}
COMBUST = {"Moon": 12, "Mars": 17, "Mercury": 14, "Jupiter": 11, "Venus": 10, "Saturn": 15}

VIM = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
VIM_YEARS = {"Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
             "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17}

TITHIS = ["Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi",
          "Saptami", "Ashtami", "Navami", "Dashami", "Ekadashi", "Dwadashi",
          "Trayodashi", "Chaturdashi", "Purnima"]
YOGAS = ["Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana", "Atiganda",
         "Sukarma", "Dhriti", "Shula", "Ganda", "Vriddhi", "Dhruva", "Vyaghata",
         "Harshana", "Vajra", "Siddhi", "Vyatipata", "Variyana", "Parigha",
         "Shiva", "Siddha", "Sadhya", "Shubha", "Shukla", "Brahma", "Indra", "Vaidhriti"]
KARANAS = ["Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti"]
VARAS = [("Monday", "Moon"), ("Tuesday", "Mars"), ("Wednesday", "Mercury"),
         ("Thursday", "Jupiter"), ("Friday", "Venus"), ("Saturday", "Saturn"),
         ("Sunday", "Sun")]
MOON_PHASES = ["🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"]

NAK_SPAN = 360 / 27
FLAGS = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED


# ───────────────────────── HELPERS ─────────────────────────
def tz_label(tz):
    sign = "+" if tz >= 0 else "-"
    return f"UTC{sign}{abs(tz) // 60:02d}:{abs(tz) % 60:02d}"


def get_tz(context):
    return context.user_data.get("tz", DEFAULT_TZ_MIN)


def local_now(tz):
    return (datetime.now(timezone.utc) + timedelta(minutes=tz)).replace(tzinfo=None, microsecond=0)


def stamp(dt):
    return f"{dt.year:04d}{dt.month:02d}{dt.day:02d}{dt.hour:02d}{dt.minute:02d}"


def parse_stamp(s, tz):
    if s == "now":
        return local_now(tz)
    return datetime(int(s[0:4]), int(s[4:6]), int(s[6:8]), int(s[8:10]), int(s[10:12]))


def add_months(dt, n):
    total = dt.year * 12 + (dt.month - 1) + n
    y, m = divmod(total, 12)
    m += 1
    day = min(dt.day, calendar.monthrange(y, m)[1])
    return dt.replace(year=y, month=m, day=day)


def fmt_deg(d):
    deg = int(d)
    m = int((d - deg) * 60)
    s = int(((d - deg) * 60 - m) * 60)
    return f"{deg}°{m:02d}'{s:02d}\""


def fmt_dt(dt):
    return f"{dt.strftime('%a')}, {dt.day:02d} {dt.strftime('%b')} {dt.year} {dt.hour:02d}:{dt.minute:02d}"


def to_jd(dt_local, tz):
    u = dt_local - timedelta(minutes=tz)
    return swe.julday(u.year, u.month, u.day, u.hour + u.minute / 60.0 + u.second / 3600.0)


def jd_to_local(jd, tz):
    y, m, d, h = swe.revjul(jd)
    return datetime(y, m, d) + timedelta(hours=h, minutes=tz)


def parse_tz(text):
    t = text.strip().upper().replace("UTC", "").replace("GMT", "")
    if t in ("", "Z"):
        return 0
    if t == "IST":
        return 330
    m = re.fullmatch(r"([+-])(\d{1,2})(?::?(\d{2}))?", t)
    if not m:
        return None
    mins = int(m[2]) * 60 + int(m[3] or 0)
    if mins > 14 * 60:
        return None
    return -mins if m[1] == "-" else mins


TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")
DATE_FORMATS = ["%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y"]


def parse_when(text, tz):
    """Understands: now, today, tomorrow, +10, -3m, +2y, 2030-05-14, 14/05/2030 18:30, 14 may 2030"""
    t = text.strip().lower()
    now = local_now(tz)
    if t in ("now", "today"):
        return now
    if t == "tomorrow":
        return now + timedelta(days=1)
    if t == "yesterday":
        return now - timedelta(days=1)
    try:
        m = re.fullmatch(r"([+-]\d+)\s*([dwmy]?)", t)
        if m:
            n, u = int(m[1]), m[2] or "d"
            if u == "d":
                return now + timedelta(days=n)
            if u == "w":
                return now + timedelta(weeks=n)
            if u == "m":
                return add_months(now, n)
            return add_months(now, 12 * n)
        hh, mm = 12, 0
        tm = TIME_RE.search(t)
        if tm:
            hh, mm = int(tm[1]), int(tm[2])
            t = (t[:tm.start()] + t[tm.end():])
        t = re.sub(r"\s+", " ", t.replace(",", " ")).strip()
        d = None
        m = re.fullmatch(r"(\d{1,4})[-/.](\d{1,2})[-/.](\d{1,4})", t)
        if m:
            a, b, c = m.groups()
            if len(a) == 4:
                d = datetime(int(a), int(b), int(c))
            elif len(c) == 4:
                d = datetime(int(c), int(b), int(a))
        else:
            for f in DATE_FORMATS:
                try:
                    d = datetime.strptime(t, f)
                    break
                except ValueError:
                    pass
        if d is None:
            return None
        return d.replace(hour=hh, minute=mm)
    except (ValueError, OverflowError):
        return None


# ───────────────────────── ASTRO ENGINE ─────────────────────────
def calc_positions(jd):
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    pos = {}
    for name, pid in BODIES.items():
        r = swe.calc_ut(jd, pid, FLAGS)[0]
        pos[name] = (r[0] % 360, r[3])
    rl, rs = pos["Rahu"]
    pos["Ketu"] = ((rl + 180) % 360, rs)
    return pos


def ang_diff(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def planet_block(name, lon, speed, sun_lon):
    sign = int(lon // 30)
    deg = lon % 30
    nak = int(lon / NAK_SPAN)
    pada = int((lon % NAK_SPAN) / (NAK_SPAN / 4)) + 1
    retro = speed < 0 or name in ("Rahu", "Ketu")

    tags = []
    if EXALT.get(name) == sign:
        tags.append("⬆️ Exalted")
    elif (EXALT.get(name, -10) + 6) % 12 == sign:
        tags.append("⬇️ Debilitated")
    elif sign in OWN.get(name, []):
        tags.append("🏠 Own sign")
    if name in COMBUST:
        limit = COMBUST[name]
        if retro and name == "Mercury":
            limit = 12
        if retro and name == "Venus":
            limit = 8
        if ang_diff(lon, sun_lon) <= limit:
            tags.append("🔥 Combust")

    rx = " (Rx)" if retro else ""
    out = (
        f"<b>{EMOJI[name]} {name}{rx}</b>  {SIGN_SYM[sign]} <b>{ZODIAC[sign]}</b>\n"
        f"↳ {fmt_deg(deg)}  ·  Lord: {SIGN_LORD[sign]}\n"
        f"↳ {NAKSHATRAS[nak]} Pada {pada}  ·  Nak Lord: {VIM[nak % 9]}\n"
        f"↳ Speed: {speed:+.3f}°/day"
    )
    if tags:
        out += "\n↳ " + "  ".join(tags)
    return out + "\n"


def build_positions(dt, tz, planet, live=False):
    pos = calc_positions(to_jd(dt, tz))
    names = ORDER if planet == "All" else [planet]
    blocks = [planet_block(n, pos[n][0], pos[n][1], pos["Sun"][0]) for n in names]
    badge = "🔴 LIVE" if live else "📅"
    u = dt - timedelta(minutes=tz)
    head = (
        f"✨ <b>Planetary Positions</b> ✨ <i>(Lahiri)</i>\n"
        f"{badge} <b>{fmt_dt(dt)}</b> <i>({tz_label(tz)})</i>\n"
        f"🕒 <i>{u.day:02d} {u.strftime('%b')} {u.year} {u.hour:02d}:{u.minute:02d} UTC</i>\n\n"
    )
    return head + "\n".join(blocks)


def build_panchang(dt, tz):
    pos = calc_positions(to_jd(dt, tz))
    sun, moon = pos["Sun"][0], pos["Moon"][0]
    elong = (moon - sun) % 360

    tn = int(elong / 12) + 1
    tname = "Amavasya" if tn == 30 else TITHIS[(tn - 1) % 15]
    paksha = "Shukla (Waxing)" if tn <= 15 else "Krishna (Waning)"
    progress = (elong % 12) / 12 * 100
    phase = MOON_PHASES[int(elong / 45) % 8]

    nak = int(moon / NAK_SPAN)
    pada = int((moon % NAK_SPAN) / (NAK_SPAN / 4)) + 1
    yoga = YOGAS[int(((sun + moon) % 360) / NAK_SPAN)]

    k = int(elong / 6)
    if k == 0:
        karana = "Kimstughna"
    elif k >= 57:
        karana = ["Shakuni", "Chatushpada", "Naga"][k - 57]
    else:
        karana = KARANAS[(k - 1) % 7]
    warn = " ⚠️ (Bhadra)" if karana == "Vishti" else ""

    vara, vlord = VARAS[dt.weekday()]
    msm, mss = int(moon // 30), int(sun // 30)
    special = ""
    if tname == "Ekadashi":
        special = "\n🙏 <b>Ekadashi day</b>"
    elif tname == "Purnima":
        special = "\n🌕 <b>Full Moon (Purnima)</b>"
    elif tname == "Amavasya":
        special = "\n🌑 <b>New Moon (Amavasya)</b>"

    return (
        f"🕉 <b>Panchang</b> 🕉\n"
        f"📅 <b>{fmt_dt(dt)}</b> <i>({tz_label(tz)})</i>\n\n"
        f"{phase} <b>Tithi:</b> {paksha.split()[0]} {tname} ({tn if tn <= 15 else tn - 15})\n"
        f"   ↳ {paksha} · {progress:.0f}% elapsed\n"
        f"⭐ <b>Nakshatra:</b> {NAKSHATRAS[nak]} Pada {pada}\n"
        f"   ↳ Lord: {VIM[nak % 9]}\n"
        f"🧿 <b>Yoga:</b> {YOGAS.index(yoga) + 1}. {yoga}\n"
        f"⚡ <b>Karana:</b> {karana}{warn}\n"
        f"📆 <b>Vara:</b> {vara} ({EMOJI[vlord]} {vlord})\n\n"
        f"☀️ Sun in {SIGN_SYM[mss]} {ZODIAC[mss]}\n"
        f"🌙 Moon in {SIGN_SYM[msm]} {ZODIAC[msm]} (Chandra Rashi)"
        f"{special}"
    )


def lon_of(name, jd):
    r = swe.calc_ut(jd, BODIES["Rahu" if name == "Ketu" else name], FLAGS)[0]
    lon = r[0] % 360
    return (lon + 180) % 360 if name == "Ketu" else lon


def next_ingress(name, jd0):
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    step = 0.1 if name == "Moon" else 0.5
    limit = 1800
    prev_jd = jd0
    prev_sign = int(lon_of(name, jd0) // 30)
    t = 0.0
    while t < limit:
        t += step
        cur = jd0 + t
        s = int(lon_of(name, cur) // 30)
        if s != prev_sign:
            lo, hi = prev_jd, cur
            for _ in range(30):
                mid = (lo + hi) / 2
                if int(lon_of(name, mid) // 30) == prev_sign:
                    lo = mid
                else:
                    hi = mid
            return hi, prev_sign, s
        prev_jd = cur
    return None


def compute_ingresses(dt, tz):
    jd0 = to_jd(dt, tz)
    rows = []
    for n in ORDER:
        res = next_ingress(n, jd0)
        if res:
            rows.append((res[0], n, res[1], res[2]))
    rows.sort()
    head = (f"🔮 <b>Upcoming Sign Changes</b>\n"
            f"From <b>{fmt_dt(dt)}</b> <i>({tz_label(tz)})</i>\n\n")
    lines = []
    for jd, n, a, b in rows:
        when = jd_to_local(jd, tz)
        rx = " (Rx)" if b != (a + 1) % 12 else ""
        lines.append(
            f"{EMOJI[n]} <b>{n}</b> → {SIGN_SYM[b]} <b>{ZODIAC[b]}</b>{rx}\n"
            f"   ↳ {fmt_dt(when)}"
        )
    return head + "\n".join(lines)


def build_chart(birth, tz, lat, lon):
    jd = to_jd(birth, tz)
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    pos = calc_positions(jd)
    _, ascmc = swe.houses_ex(jd, lat, lon, b"W", swe.FLG_SIDEREAL)
    asc = ascmc[0] % 360
    asign = int(asc // 30)
    anak = int(asc / NAK_SPAN)

    lines = [
        f"🔮 <b>Birth Chart</b> <i>(Lahiri · Whole-sign houses)</i>\n"
        f"📅 {fmt_dt(birth)} <i>({tz_label(tz)})</i>\n"
        f"📍 {lat:.2f}, {lon:.2f}\n",
        f"⬆️ <b>Lagna:</b> {SIGN_SYM[asign]} {ZODIAC[asign]} {fmt_deg(asc % 30)}\n"
        f"   ↳ {NAKSHATRAS[anak]} · Lord: {SIGN_LORD[asign]}\n",
    ]
    for n in ORDER:
        l, sp = pos[n]
        s = int(l // 30)
        house = (s - asign) % 12 + 1
        rx = " Rx" if (sp < 0 or n in ("Rahu", "Ketu")) else ""
        lines.append(
            f"{EMOJI[n]} <b>{n}</b>{rx}: {SIGN_SYM[s]} {ZODIAC[s]} {fmt_deg(l % 30)} · "
            f"House <b>{house}</b> · {NAKSHATRAS[int(l / NAK_SPAN)]}"
        )
    moon = pos["Moon"][0]
    idx = int(moon / NAK_SPAN)
    lord = idx % 9
    frac = (moon % NAK_SPAN) / NAK_SPAN
    start = birth - timedelta(days=VIM_YEARS[VIM[lord]] * frac * 365.25)
    now = local_now(tz)
    lines.append(f"\n🌀 <b>Vimshottari Mahadasha</b> <i>(Moon: {NAKSHATRAS[idx]})</i>")
    for i in range(9):
        L = VIM[(lord + i) % 9]
        try:
            end = start + timedelta(days=VIM_YEARS[L] * 365.25)
        except OverflowError:
            break
        shown = max(start, birth)
        mark = "  👈 <b>running</b>" if start <= now < end else ""
        lines.append(f"{EMOJI[L]} {L}: {shown.strftime('%b %Y')} → {end.strftime('%b %Y')}{mark}")
        start = end
    return "\n".join(lines)


# ───────────────────────── KEYBOARDS ─────────────────────────
def nav_rows(mode, dt, planet):
    def b(label, new_dt):
        return Btn(label, callback_data=f"{mode}:{stamp(new_dt)}:{planet}")
    try:
        return [
            [b("⏪ -1Y", add_months(dt, -12)), b("◀ -1M", add_months(dt, -1)),
             b("+1M ▶", add_months(dt, 1)), b("+1Y ⏩", add_months(dt, 12))],
            [b("-1H", dt - timedelta(hours=1)), b("◀ -1 Day", dt - timedelta(days=1)),
             b("+1 Day ▶", dt + timedelta(days=1)), b("+1H", dt + timedelta(hours=1))],
        ]
    except (OverflowError, ValueError):
        return []


def view_keyboard(mode, dt, planet):
    rows = nav_rows(mode, dt, planet)
    other = "p" if mode == "v" else "v"
    other_label = "🕉 Panchang" if mode == "v" else "🪐 Planets"
    rows.append([
        Btn("📍 Now", callback_data=f"{mode}:now:{planet}"),
        Btn("📅 Calendar", callback_data=f"c:{stamp(dt)}:{planet}"),
        Btn(other_label, callback_data=f"{other}:{stamp(dt)}:{planet if mode == 'v' else 'All'}"),
    ])
    if mode == "v":
        s = stamp(dt)
        names = ORDER
        for i in range(0, 9, 3):
            rows.append([Btn(f"{EMOJI[n]} {n}", callback_data=f"v:{s}:{n}") for n in names[i:i + 3]])
        rows.append([Btn("🌌 All Planets", callback_data=f"v:{s}:All"),
                     Btn("🏠 Menu", callback_data="menu")])
    else:
        rows.append([Btn("🏠 Menu", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def calendar_keyboard(dt, planet):
    y, m = dt.year, dt.month

    def nav(label, d):
        return Btn(label, callback_data=f"c:{stamp(d)}:{planet}")

    rows = []
    try:
        rows.append([nav("«", add_months(dt, -12)), nav("‹", add_months(dt, -1)),
                     Btn(f"{calendar.month_abbr[m]} {y}", callback_data="noop"),
                     nav("›", add_months(dt, 1)), nav("»", add_months(dt, 12))])
    except (OverflowError, ValueError):
        pass
    rows.append([Btn(d, callback_data="noop") for d in "MTWTFSS"])
    for week in calendar.monthcalendar(y, m):
        row = []
        for d in week:
            if d == 0:
                row.append(Btn(" ", callback_data="noop"))
            else:
                label = f"·{d}·" if d == dt.day else str(d)
                row.append(Btn(label, callback_data=f"v:{stamp(dt.replace(day=d))}:{planet}"))
        rows.append(row)
    rows.append([Btn("🔙 Back", callback_data=f"v:{stamp(dt)}:{planet}"),
                 Btn("🕉 Panchang", callback_data=f"p:{stamp(dt)}:All"),
                 Btn("🏠 Menu", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def menu_keyboard():
    return InlineKeyboardMarkup([
        [Btn("🪐 Live Planets", callback_data="v:now:All"), Btn("🕉 Panchang", callback_data="p:now:All")],
        [Btn("📅 Pick a Date", callback_data="c:now:All"), Btn("🔮 Next Sign Changes", callback_data="t:now")],
        [Btn("🌍 Timezone", callback_data="tzmenu"), Btn("❓ Help", callback_data="help")],
    ])


def back_keyboard(extra=None):
    rows = [extra] if extra else []
    rows.append([Btn("🏠 Menu", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


# ───────────────────────── TEXTS ─────────────────────────
HELP = (
    "❓ <b>How to use AstroBot</b>\n\n"
    "<b>Commands</b>\n"
    "/start – main menu\n"
    "/planets – live planetary positions\n"
    "/panchang – tithi, nakshatra, yoga, karana\n"
    "/date – any date, past or future\n"
    "/transits – upcoming sign changes\n"
    "/chart – birth chart + dasha\n"
    "/tz – set your timezone\n\n"
    "<b>View any date</b>\n"
    "<code>/date 2031-08-15</code>\n"
    "<code>/date 15/08/2031 18:30</code>\n"
    "<code>/date 15 aug 2031</code>\n"
    "<code>/date +90</code> (90 days ahead) · <code>/date -2y</code> · <code>+3m</code> · <code>+1w</code>\n"
    "👉 Or just <b>send a date as a message</b> and I'll show it!\n\n"
    "<b>Birth chart</b>\n"
    "<code>/chart 15-01-2000 14:30 28.61 77.20</code>\n"
    "(date, time, latitude, longitude – East/North positive; optional timezone at the end, e.g. <code>+5:30</code>)\n\n"
    "<b>Timezone</b>\n"
    "<code>/tz +5:30</code> · <code>/tz -8</code>\n\n"
    "<i>Dates without a time use 12:00 noon. Moon moves ~13°/day, so use the ±1H buttons for precise Moon positions.</i>"
)


def start_text(name, tz):
    return (
        f"✨ <b>Namaste, {html.escape(name)}!</b> ✨\n"
        f"Welcome to <b>AstroBot</b> 🔭 – Vedic (sidereal · Lahiri) astrology in your pocket.\n\n"
        f"• Live planet positions with dignity, combustion &amp; retrograde\n"
        f"• Panchang for any date\n"
        f"• Browse any day, month or year – past or future\n"
        f"• Sign-change (ingress) finder\n"
        f"• Birth chart with Lagna &amp; Vimshottari Dasha\n\n"
        f"🌍 Timezone: <b>{tz_label(tz)}</b> (change with /tz)"
    )


# ───────────────────────── SENDING ─────────────────────────
async def send(update, text, kb=None):
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, reply_markup=kb, parse_mode=ParseMode.HTML)
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
    else:
        await update.effective_message.reply_text(
            text, reply_markup=kb, parse_mode=ParseMode.HTML)


# ───────────────────────── COMMANDS ─────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name if update.effective_user else "friend"
    await send(update, start_text(name, get_tz(context)), menu_keyboard())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send(update, HELP, back_keyboard())


async def planets_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz = get_tz(context)
    dt = local_now(tz)
    await send(update, build_positions(dt, tz, "All", live=True), view_keyboard("v", dt, "All"))


async def panchang_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz = get_tz(context)
    dt = parse_when(" ".join(context.args), tz) if context.args else local_now(tz)
    if dt is None:
        await send(update, "⚠️ Couldn't read that date. Try <code>/panchang 2030-05-14</code>")
        return
    await send(update, build_panchang(dt, tz), view_keyboard("p", dt, "All"))


async def date_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz = get_tz(context)
    if not context.args:
        await send(update, "📅 Send a date, e.g.\n<code>/date 2031-08-15</code>\n"
                           "<code>/date 15/08/2031 18:30</code>\n<code>/date +90</code>",
                   InlineKeyboardMarkup([[Btn("📅 Open Calendar", callback_data="c:now:All")]]))
        return
    dt = parse_when(" ".join(context.args), tz)
    if dt is None:
        await send(update, "⚠️ Couldn't read that date. Try <code>2031-08-15</code>, "
                           "<code>15/08/2031 18:30</code> or <code>+90</code>")
        return
    await send(update, build_positions(dt, tz, "All"), view_keyboard("v", dt, "All"))


async def text_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Plain messages are tried as dates."""
    tz = get_tz(context)
    dt = parse_when(update.message.text, tz)
    if dt is None:
        await update.message.reply_text(
            "🤔 I didn't get that. Send a date like <code>2031-08-15</code> or "
            "<code>15 aug 2031 18:30</code>, or use the menu.",
            parse_mode=ParseMode.HTML, reply_markup=menu_keyboard())
        return
    await send(update, build_positions(dt, tz, "All"), view_keyboard("v", dt, "All"))


async def transits_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz = get_tz(context)
    dt = parse_when(" ".join(context.args), tz) if context.args else local_now(tz)
    if dt is None:
        await send(update, "⚠️ Couldn't read that date.")
        return
    await run_transits(update, dt, tz)


async def run_transits(update, dt, tz):
    if update.callback_query:
        await update.callback_query.answer("Calculating…")
    text = await asyncio.to_thread(compute_ingresses, dt, tz)
    kb = back_keyboard([Btn("🔄 From Now", callback_data="t:now"),
                        Btn("📅 Pick Date", callback_data=f"c:{stamp(dt)}:All")])
    await send(update, text, kb)


async def chart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    a = context.args
    usage = ("🔮 <b>Birth chart</b>\nUsage:\n<code>/chart 15-01-2000 14:30 28.61 77.20</code>\n"
             "date · time · latitude · longitude (optional timezone at the end, e.g. <code>+5:30</code>)")
    if len(a) < 4 or not TIME_RE.fullmatch(a[1]):
        await send(update, usage)
        return
    tz = get_tz(context)
    try:
        lat, lon = float(a[2]), float(a[3])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError
        if len(a) > 4:
            tz = parse_tz(a[4])
            if tz is None:
                raise ValueError
        birth = parse_when(f"{a[0]} {a[1]}", tz)
        if birth is None:
            raise ValueError
    except ValueError:
        await send(update, "⚠️ Something's off with the details.\n\n" + usage)
        return
    try:
        text = build_chart(birth, tz, lat, lon)
    except Exception:
        log.exception("chart failed")
        await send(update, "😵 Couldn't compute that chart. Check the values and try again.")
        return
    await send(update, text, back_keyboard())


async def tz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        tz = parse_tz(context.args[0])
        if tz is None:
            await send(update, "⚠️ Try <code>/tz +5:30</code> or <code>/tz -8</code>")
            return
        context.user_data["tz"] = tz
        await send(update, f"✅ Timezone set to <b>{tz_label(tz)}</b>", back_keyboard())
        return
    await send(update, f"🌍 Current timezone: <b>{tz_label(get_tz(context))}</b>\nPick one or send "
                       f"<code>/tz +5:30</code>", tz_keyboard())


def tz_keyboard():
    zones = [("🇮🇳 IST +5:30", 330), ("🌐 UTC", 0), ("🇺🇸 EST -5", -300), ("🇺🇸 PST -8", -480),
             ("🇬🇧 BST +1", 60), ("🇪🇺 CET +1", 60), ("🇦🇪 GST +4", 240), ("🇵🇰 PKT +5", 300),
             ("🇧🇩 BST +6", 360), ("🇸🇬 SGT +8", 480), ("🇯🇵 JST +9", 540), ("🇦🇺 AEST +10", 600)]
    rows = []
    for i in range(0, len(zones), 2):
        rows.append([Btn(l, callback_data=f"tz:{m}") for l, m in zones[i:i + 2]])
    rows.append([Btn("🏠 Menu", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


# ───────────────────────── BUTTONS ─────────────────────────
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    tz = get_tz(context)
    parts = data.split(":")
    kind = parts[0]

    if kind == "t":
        await run_transits(update, parse_stamp(parts[1], tz), tz)
        return
    await q.answer()

    try:
        if kind == "noop":
            return
        if kind == "menu":
            await send(update, start_text(q.from_user.first_name, tz), menu_keyboard())
        elif kind == "help":
            await send(update, HELP, back_keyboard())
        elif kind == "tzmenu":
            await send(update, f"🌍 Current timezone: <b>{tz_label(tz)}</b>\nPick one or send "
                               f"<code>/tz +5:30</code>", tz_keyboard())
        elif kind == "tz":
            context.user_data["tz"] = int(parts[1])
            await send(update, f"✅ Timezone set to <b>{tz_label(int(parts[1]))}</b>", menu_keyboard())
        elif kind == "v":
            dt = parse_stamp(parts[1], tz)
            planet = parts[2] or "All"
            await send(update, build_positions(dt, tz, planet, live=parts[1] == "now"),
                       view_keyboard("v", dt, planet))
        elif kind == "p":
            dt = parse_stamp(parts[1], tz)
            await send(update, build_panchang(dt, tz), view_keyboard("p", dt, "All"))
        elif kind == "c":
            dt = parse_stamp(parts[1], tz)
            planet = parts[2] or "All"
            await send(update, "📅 <b>Pick a date</b>\n<i>Use ‹ › for months and « » for years. "
                               "Tap a day to see the sky.</i>", calendar_keyboard(dt, planet))
    except (ValueError, OverflowError):
        await send(update, "⚠️ That date is out of range.", back_keyboard())


async def on_error(update, context: ContextTypes.DEFAULT_TYPE):
    log.error("Update caused error", exc_info=context.error)


# ───────────────────────── MAIN ─────────────────────────
if __name__ == "__main__":
    print("🚀 Bot is spinning up... Press CTRL+C to stop.")
    keep_alive()  # 24/7 keep-alive web server

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("planets", planets_menu))
    app.add_handler(CommandHandler("panchang", panchang_cmd))
    app.add_handler(CommandHandler("date", date_cmd))
    app.add_handler(CommandHandler("transits", transits_cmd))
    app.add_handler(CommandHandler("chart", chart_cmd))
    app.add_handler(CommandHandler("tz", tz_cmd))
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, text_date))
    app.add_error_handler(on_error)

    app.run_polling()
