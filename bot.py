import os
import re
import asyncio
import calendar
import logging
from datetime import datetime, timedelta, timezone

import swisseph as swe
from telegram import Update, InlineKeyboardButton as Btn, InlineKeyboardMarkup, BotCommand
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
from keep_alive import keep_alive  # Keeps Render awake!

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("astrobot")

# ═══════════════════════ 🔑 BOT TOKEN ═══════════════════════
# Option 1 (recommended on Render): add an Environment Variable named
#          TELEGRAM_TOKEN   with the token you got from @BotFather
# Option 2 (local testing only): paste the token between the quotes below.
TOKEN = os.environ.get("TELEGRAM_TOKEN", "YOUR_TELEGRAM_TOKEN")
# ═════════════════════════════════════════════════════════════

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
RASHI = ["Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
         "Tula", "Vrishchika", "Dhanu", "Makara", "Kumbha", "Meena"]
# Classical Moon-based Gochar: houses (counted from Janma Rashi) favourable for each planet
GOOD_HOUSES = {
    "Sun": [3, 6, 10, 11], "Moon": [1, 3, 6, 7, 10, 11], "Mars": [3, 6, 11],
    "Mercury": [2, 4, 6, 8, 10, 11], "Jupiter": [2, 5, 7, 9, 11],
    "Venus": [1, 2, 3, 4, 5, 8, 9, 11, 12], "Saturn": [3, 6, 11],
    "Rahu": [3, 6, 10, 11], "Ketu": [3, 6, 11],
}
SIGN_LORD = ["Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury",
             "Venus", "Mars", "Jupiter", "Saturn", "Saturn", "Jupiter"]

EMOJI = {"Sun": "☀️", "Moon": "🌙", "Mars": "🔴", "Mercury": "🟢", "Jupiter": "🟡",
         "Venus": "💖", "Saturn": "🪐", "Rahu": "🌪️", "Ketu": "☄️"}
BODIES = {"Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS, "Mercury": swe.MERCURY,
          "Jupiter": swe.JUPITER, "Venus": swe.VENUS, "Saturn": swe.SATURN,
          "Rahu": swe.TRUE_NODE}
ORDER = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]
NODES = ("Rahu", "Ketu")

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

LEGEND = "<i>R = Retrograde · C = Combust</i>"


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


def fmt_date(dt):
    return f"{dt.day:02d} {dt.strftime('%b')} {dt.year}"


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


def parse_latlon(text):
    nums = re.findall(r"-?\d+(?:\.\d+)?", text)
    if len(nums) < 2:
        return None
    lat, lon = float(nums[0]), float(nums[1])
    up = text.upper()
    if re.search(r"\d\s*°?\s*S\b", up) and lat > 0:
        lat = -lat
    if re.search(r"\d\s*°?\s*W\b", up) and lon > 0:
        lon = -lon
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


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


# ───────────────────────── ASTRO ENGINE (Vedic / Lahiri) ─────────────────────────
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


def is_retro(name, speed):
    return speed < 0 or name in NODES


def combust_info(name, lon, speed, sun_lon):
    """Returns None if combustion doesn't apply, else (is_combust, distance_from_sun, limit)."""
    if name not in COMBUST:
        return None
    limit = COMBUST[name]
    if speed < 0 and name == "Mercury":
        limit = 12
    if speed < 0 and name == "Venus":
        limit = 8
    dist = ang_diff(lon, sun_lon)
    return dist <= limit, dist, limit


def flags_of(name, lon, speed, sun_lon):
    out = []
    if is_retro(name, speed):
        out.append("R")
    ci = combust_info(name, lon, speed, sun_lon)
    if ci and ci[0]:
        out.append("C")
    return out


def label_of(name, lon, speed, sun_lon):
    fl = flags_of(name, lon, speed, sun_lon)
    return name + (f" ({'/'.join(fl)})" if fl else "")


def planet_block(name, lon, speed, sun_lon):
    sign = int(lon // 30)
    deg = lon % 30
    nak = int(lon / NAK_SPAN)
    pada = int((lon % NAK_SPAN) / (NAK_SPAN / 4)) + 1

    tags = []
    if EXALT.get(name) == sign:
        tags.append("⬆️ Exalted")
    elif (EXALT.get(name, -10) + 6) % 12 == sign:
        tags.append("⬇️ Debilitated")
    elif sign in OWN.get(name, []):
        tags.append("🏠 Own sign")

    r = " <b>(R)</b>" if is_retro(name, speed) else ""
    out = (
        f"<b>{EMOJI[name]} {name}</b>{r}  {SIGN_SYM[sign]} <b>{ZODIAC[sign]}</b>\n"
        f"↳ <b>{fmt_deg(deg)}</b>  ·  Lord: {SIGN_LORD[sign]}\n"
        f"↳ {NAKSHATRAS[nak]} Pada {pada}  ·  Nak Lord: {VIM[nak % 9]}\n"
        f"↳ Speed: {speed:+.3f}°/day"
    )
    if tags:
        out += "\n↳ " + "  ".join(tags)
    ci = combust_info(name, lon, speed, sun_lon)
    if ci:
        c, dist, limit = ci
        if c:
            out += f"\n↳ 🔥 <b>C – Combust</b> ({fmt_deg(dist)} from Sun, limit {limit}°)"
        else:
            out += f"\n↳ ✅ Not combust ({fmt_deg(dist)} from Sun)"
    return out + "\n"


def build_positions(dt, tz, planet="All", live=False, view="d"):
    pos = calc_positions(to_jd(dt, tz))
    sun = pos["Sun"][0]
    badge = "🔴 LIVE" if live else "📅"
    u = dt - timedelta(minutes=tz)
    head = (
        f"✨ <b>Planetary Positions</b> ✨ <i>(Vedic · Lahiri)</i>\n"
        f"{badge} <b>{fmt_dt(dt)}</b> <i>({tz_label(tz)})</i>\n"
        f"🕒 <i>{fmt_date(u)} {u.hour:02d}:{u.minute:02d} UTC</i>\n\n"
    )

    if view == "t":
        rows = [f"{'Planet':<14}{'Sign':<4} {'Deg':<6} Nak"]
        for n in ORDER:
            l, sp = pos[n]
            s, dg = int(l // 30), l % 30
            dd, mm = int(dg), int((dg - int(dg)) * 60)
            rows.append(f"{label_of(n, l, sp, sun):<14}{ZODIAC[s][:3]} {dd:02d}°{mm:02d}' "
                        f"{NAKSHATRAS[int(l / NAK_SPAN)][:4]}")
        return head + "<pre>" + "\n".join(rows) + "</pre>\n" + LEGEND

    names = ORDER if planet == "All" else [planet]
    summary = ""
    if planet == "All":
        retro = [n for n in ORDER if n not in NODES and pos[n][1] < 0]
        comb = [n for n in ORDER if (combust_info(n, pos[n][0], pos[n][1], sun) or (False,))[0]]
        summary = (
            f"🔁 <b>R</b>: {', '.join(retro) if retro else 'None'} <i>(Rahu/Ketu always R)</i>\n"
            f"🔥 <b>C</b>: {', '.join(comb) if comb else 'None'}\n\n"
        )
    blocks = [planet_block(n, pos[n][0], pos[n][1], sun) for n in names]
    return head + summary + "\n".join(blocks) + "\n" + LEGEND


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
    limit = 40 if name == "Moon" else 1800
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


def build_ingresses(dt, tz):
    jd0 = to_jd(dt, tz)
    rows = []
    for n in ORDER:
        res = next_ingress(n, jd0)
        if res:
            rows.append((res[0], n, res[1], res[2]))
    rows.sort()
    head = (f"🔮 <b>Rashi Parivartan</b> <i>(Gochar Ingress)</i>\n"
            f"From <b>{fmt_dt(dt)}</b> <i>({tz_label(tz)})</i>\n\n")
    lines = []
    for jd, n, a, b in rows:
        when = jd_to_local(jd, tz)
        rx = " <b>(R)</b>" if b != (a + 1) % 12 else ""
        lines.append(
            f"{EMOJI[n]} <b>{n}</b>: {SIGN_SYM[a]} {RASHI[a]} → {SIGN_SYM[b]} <b>{RASHI[b]}</b>{rx}\n"
            f"   ↳ {fmt_dt(when)}"
        )
    return head + "\n".join(lines) + "\n\n" + LEGEND


def ordinal(n):
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")


def build_gochar(dt, tz, rashi):
    pos = calc_positions(to_jd(dt, tz))
    sun = pos["Sun"][0]
    lines = [
        f"🔮 <b>Gochar</b> <i>(Transit from Janma Rashi)</i>\n"
        f"🌙 Janma Rashi: {SIGN_SYM[rashi]} <b>{RASHI[rashi]}</b> ({ZODIAC[rashi]})\n"
        f"📅 <b>{fmt_dt(dt)}</b> <i>({tz_label(tz)})</i>\n"
    ]
    good_count = 0
    for n in ORDER:
        l, sp = pos[n]
        sgn = int(l // 30)
        h = (sgn - rashi) % 12 + 1
        good = h in GOOD_HOUSES[n]
        good_count += good
        mark = "✅ Shubh" if good else "⚠️ Ashubh"
        fl = flags_of(n, l, sp, sun)
        tag = f" <b>({'/'.join(fl)})</b>" if fl else ""
        lines.append(
            f"{EMOJI[n]} <b>{n}</b>{tag} in {SIGN_SYM[sgn]} {RASHI[sgn]} {fmt_deg(l % 30)}\n"
            f"   ↳ <b>{ordinal(h)}</b> from Moon · {mark}"
        )
    d = (int(pos["Saturn"][0] // 30) - rashi) % 12
    shani = {
        11: "🪐 <b>Sade Sati – Phase 1</b> (Saturn in 12th, rising)",
        0: "🪐 <b>Sade Sati – Phase 2</b> (Saturn over Moon, peak)",
        1: "🪐 <b>Sade Sati – Phase 3</b> (Saturn in 2nd, setting)",
        7: "🪐 <b>Ashtama Shani</b> (Saturn in 8th from Moon)",
        3: "🪐 <b>Kantaka Shani</b> (Saturn in 4th from Moon)",
    }.get(d, "🪐 Sade Sati / Shani Dosha: <b>Not running</b> ✅")
    lines.append(f"\n{shani}")
    lines.append(f"📊 Shubh transits: <b>{good_count}/9</b>")
    lines.append(f"\n{LEGEND}")
    lines.append("<i>Classical Moon-based Gochar only. A full reading also needs Dasha, Ashtakavarga and Vedha.</i>")
    return "\n".join(lines)


# ───────────── BIRTH CHART DATA ─────────────
NAK_DEITY = [
    "Ashwini Kumaras", "Yama", "Agni", "Brahma", "Soma", "Rudra", "Aditi", "Brihaspati",
    "Nagas", "Pitris", "Bhaga", "Aryaman", "Savitar", "Tvashtar", "Vayu", "Indra-Agni",
    "Mitra", "Indra", "Nirriti", "Apas", "Vishvadevas", "Vishnu", "Vasus", "Varuna",
    "Aja Ekapada", "Ahir Budhnya", "Pushan",
]
NAK_GANA = "DMRMDMDDRRMMDRDRDRRMMDRRMMD"
GANA_NAME = {"D": "Deva (divine)", "M": "Manushya (human)", "R": "Rakshasa (fierce)"}
NAK_SYLL = [
    "Chu Che Cho La", "Li Lu Le Lo", "A I U E", "O Va Vi Vu", "Ve Vo Ka Ki", "Ku Gha Ng Chha",
    "Ke Ko Ha Hi", "Hu He Ho Da", "Di Du De Do", "Ma Mi Mu Me", "Mo Ta Ti Tu", "Te To Pa Pi",
    "Pu Sha Na Tha", "Pe Po Ra Ri", "Ru Re Ro Ta", "Ti Tu Te To", "Na Ni Nu Ne", "No Ya Yi Yu",
    "Ye Yo Bha Bhi", "Bhu Dha Pha Dha", "Bhe Bho Ja Ji", "Khi Khu Khe Kho", "Ga Gi Gu Ge",
    "Go Sa Si Su", "Se So Da Di", "Du Tha Jha Na", "De Do Cha Chi",
]
ABBR = {"Sun": "Su", "Moon": "Mo", "Mars": "Ma", "Mercury": "Me", "Jupiter": "Ju",
        "Venus": "Ve", "Saturn": "Sa", "Rahu": "Ra", "Ketu": "Ke"}
SI_LAYOUT = [[11, 0, 1, 2], [10, None, None, 3], [9, None, None, 4], [8, 7, 6, 5]]


def nav_sign(lon):
    return int(lon * 9 / 30) % 12


def sign_map(pos, fn):
    m = {}
    for n in ORDER:
        m.setdefault(fn(pos[n][0]), []).append(ABBR[n])
    return m


def south_chart(smap, asc_sign, title, subtitle=""):
    """South-Indian style chart (signs fixed in place) as monospace text."""
    W = 8

    def cell(sg, line):
        if line == 0:
            return ZODIAC[sg][:3].center(W)
        items = list(smap.get(sg, []))
        if sg == asc_sign:
            items.insert(0, "As")
        if line == 1:
            txt = " ".join(items[:3])
        elif len(items) <= 6:
            txt = " ".join(items[3:6])
        else:
            txt = " ".join(items[3:5]) + f" +{len(items) - 5}"
        return txt.center(W)

    full = "+" + "+".join(["-" * W] * 4) + "+"
    gap = "+" + "-" * W + "+" + " " * (2 * W + 1) + "+" + "-" * W + "+"
    out = [full]
    for r, row in enumerate(SI_LAYOUT):
        for line in range(3):
            if r in (1, 2):
                centre = ""
                if line == 1:
                    centre = title if r == 1 else subtitle
                out.append("|" + cell(row[0], line) + "|" + centre.center(2 * W + 1) + "|"
                           + cell(row[3], line) + "|")
            else:
                out.append("|" + "|".join(cell(sg, line) for sg in row) + "|")
        out.append(gap if r == 1 else full)
    return "<pre>" + "\n".join(out) + "</pre>"


def chart_data(birth, tz, lat, lon):
    jd = to_jd(birth, tz)
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    pos = calc_positions(jd)
    _, ascmc = swe.houses_ex(jd, lat, lon, b"W", swe.FLG_SIDEREAL)
    return pos, ascmc[0] % 360


def detect_yogas(pos, asc_sign):
    sg = {n: int(pos[n][0] // 30) for n in ORDER}
    house = {n: (sg[n] - asc_sign) % 12 + 1 for n in ORDER}
    yogas, doshas = [], []

    if (sg["Jupiter"] - sg["Moon"]) % 12 in (0, 3, 6, 9):
        yogas.append("🐘 <b>Gaja Kesari Yoga</b>\n   ↳ Jupiter in a Kendra from Moon – wisdom, fame, resilience")
    if sg["Sun"] == sg["Mercury"]:
        yogas.append("📚 <b>Budhaditya Yoga</b>\n   ↳ Sun + Mercury together – sharp intellect")
    if sg["Moon"] == sg["Mars"]:
        yogas.append("💰 <b>Chandra-Mangal Yoga</b>\n   ↳ Moon + Mars together – drive to earn")
    mp = {"Mars": "Ruchaka", "Mercury": "Bhadra", "Jupiter": "Hamsa", "Venus": "Malavya", "Saturn": "Shasha"}
    for n, nm in mp.items():
        if house[n] in (1, 4, 7, 10) and (sg[n] in OWN[n] or sg[n] == EXALT[n]):
            yogas.append(f"👑 <b>{nm} Yoga</b> <i>(Pancha Mahapurusha)</i>\n   ↳ {n} strong in a Kendra")
    if all((sg[n] - sg["Moon"]) % 12 not in (0, 1, 11) for n in ("Mars", "Mercury", "Jupiter", "Venus", "Saturn")):
        doshas.append("🌑 <b>Kemadruma Yoga</b>\n   ↳ No planets near Moon – inner loneliness; often cancelled by other factors")

    mh, mm = house["Mars"], (sg["Mars"] - sg["Moon"]) % 12 + 1
    if mh in (1, 2, 4, 7, 8, 12) or mm in (1, 2, 4, 7, 8, 12):
        src = []
        if mh in (1, 2, 4, 7, 8, 12):
            src.append(f"{ordinal(mh)} from Lagna")
        if mm in (1, 2, 4, 7, 8, 12):
            src.append(f"{ordinal(mm)} from Moon")
        doshas.append(f"🔴 <b>Manglik Dosha</b>\n   ↳ Mars in {' &amp; '.join(src)}")
    else:
        yogas.append("✅ <b>No Manglik Dosha</b>\n   ↳ Mars is clear of the sensitive houses")

    sides = {((pos[n][0] - pos["Rahu"][0]) % 360) < 180
             for n in ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn")}
    if len(sides) == 1:
        doshas.append("🐍 <b>Kaal Sarp Dosha</b>\n   ↳ All planets hemmed between Rahu and Ketu")
    return yogas, doshas


def dasha_page(head, pos, birth, tz):
    moon = pos["Moon"][0]
    idx = int(moon / NAK_SPAN)
    lord = idx % 9
    frac = (moon % NAK_SPAN) / NAK_SPAN
    start = birth - timedelta(days=VIM_YEARS[VIM[lord]] * frac * 365.25)
    now = local_now(tz)
    lines = [head, f"🌀 <b>Vimshottari Dasha</b> <i>(Moon in {NAKSHATRAS[idx]})</i>\n"]
    running = None
    for i in range(9):
        L = VIM[(lord + i) % 9]
        try:
            end = start + timedelta(days=VIM_YEARS[L] * 365.25)
        except OverflowError:
            break
        mark = ""
        if start <= now < end:
            mark = "  👈 <b>running</b>"
            running = (L, start)
        lines.append(f"{EMOJI[L]} <b>{L}</b>: {fmt_date(start)} → {fmt_date(end)}{mark}")
        start = end
    if running:
        L, s = running
        li = VIM.index(L)
        lines.append(f"\n🔹 <b>{L} Mahadasha – Antardasha</b>")
        for j in range(9):
            S = VIM[(li + j) % 9]
            try:
                e = s + timedelta(days=VIM_YEARS[L] * VIM_YEARS[S] / 120 * 365.25)
            except OverflowError:
                break
            mk = "  👈 <b>running</b>" if s <= now < e else ""
            lines.append(f"{EMOJI[S]} {S}: {fmt_date(s)} → {fmt_date(e)}{mk}")
            s = e
    lines.append("\n<i>Dasha years use 365.25-day years.</i>")
    return "\n".join(lines)


def build_chart(ud, tz, page):
    birth, lat, lon = ud["birth"], ud["lat"], ud["lon"]
    pos, asc = chart_data(birth, tz, lat, lon)
    sun = pos["Sun"][0]
    asc_sign = int(asc // 30)
    ud["rashi"] = int(pos["Moon"][0] // 30)  # Janma Rashi used by Gochar
    head = (f"🎂 <b>Birth Chart</b> <i>(Vedic · Lahiri)</i>\n"
            f"📅 <b>{fmt_dt(birth)}</b> <i>({tz_label(tz)})</i>\n"
            f"📍 {lat:.3f}, {lon:.3f}\n")

    if page == "asc":
        mi = int(pos["Moon"][0] / NAK_SPAN)
        mpada = int((pos["Moon"][0] % NAK_SPAN) / (NAK_SPAN / 4)) + 1
        msign = int(pos["Moon"][0] // 30)
        ai = int(asc / NAK_SPAN)
        rows = []
        for n in ORDER:
            l, sp = pos[n]
            s, dg = int(l // 30), l % 30
            h = (s - asc_sign) % 12 + 1
            rows.append(f"{label_of(n, l, sp, sun):<14}{ZODIAC[s][:3]} {int(dg):02d}°{int((dg % 1) * 60):02d}' H{h}")
        return (
            head + "\n"
            f"⬆️ <b>Lagna:</b> {SIGN_SYM[asc_sign]} {ZODIAC[asc_sign]} ({RASHI[asc_sign]}) {fmt_deg(asc % 30)}\n"
            f"   ↳ {NAKSHATRAS[ai]}\n"
            f"🌙 <b>Rashi:</b> {SIGN_SYM[msign]} {ZODIAC[msign]} ({RASHI[msign]})\n"
            f"⭐ <b>Nakshatra:</b> {NAKSHATRAS[mi]} Pada {mpada}\n"
            f"   ↳ Lord: {VIM[mi % 9]} · Deity: {NAK_DEITY[mi]}\n"
            f"   ↳ Gana: {GANA_NAME[NAK_GANA[mi]]}\n"
            f"   ↳ Name syllables: {NAK_SYLL[mi]}\n\n"
            + south_chart(sign_map(pos, lambda l: int(l // 30)), asc_sign, "RASHI", "D-1")
            + "\n<pre>" + "\n".join(rows) + "</pre>\n" + LEGEND
            + "\n<i>Whole-sign houses (H1 = Lagna).</i>"
        )
    if page == "nav":
        nav_asc = nav_sign(asc)
        return (head + "\n💠 <b>Navamsa (D-9)</b>\n"
                + south_chart(sign_map(pos, nav_sign), nav_asc, "NAVAMSA", "D-9")
                + f"\nNavamsa Lagna: {SIGN_SYM[nav_asc]} {ZODIAC[nav_asc]}")
    if page == "yog":
        yogas, doshas = detect_yogas(pos, asc_sign)
        txt = head + "\n🌟 <b>Yogas</b>\n" + ("\n".join(yogas) if yogas else "None detected")
        txt += "\n\n⚠️ <b>Doshas</b>\n" + ("\n".join(doshas) if doshas else "None detected ✅")
        return txt
    return dasha_page(head, pos, birth, tz)


# ───────────────────────── UI: KEYBOARDS ─────────────────────────
MODE_OF = {"pos": "p", "pan": "n", "ing": "i", "goc": "g"}
MODE_TITLE = {"p": "🪐 Planetary Positions", "n": "🕉 Panchang", "i": "🔮 Rashi Parivartan",
              "g": "🌙 Gochar", "b": "🎂 Birth Chart"}
COMMON_TZ = [("🇮🇳 IST +5:30", 330), ("UTC", 0), ("🇬🇧 BST +1", 60), ("🇦🇪 UAE +4", 240),
             ("🇺🇸 EST −5", -300), ("🇺🇸 PST −8", -480), ("🇸🇬 SGT +8", 480), ("🇦🇺 AEST +10", 600)]


def menu_kb(tz):
    n = local_now(tz)
    return InlineKeyboardMarkup([
        [Btn("🪐 Live Positions", callback_data="pos:now:All:d"),
         Btn("📅 Positions on a date", callback_data=f"cal:p:{n.year}:{n.month}")],
        [Btn("🕉 Panchang", callback_data="pan:now"), Btn("🔮 Rashi Parivartan", callback_data="ing:now")],
        [Btn("🌙 Gochar", callback_data="goc:now"), Btn("🎂 Birth Chart", callback_data="ch:asc")],
        [Btn("🕰 Timezone", callback_data="tz:menu"), Btn("ℹ️ Help", callback_data="help")],
    ])


def calendar_kb(mode, y, m, tz):
    y = max(1800, min(2400, y))
    today = local_now(tz)
    py, pm = (y, m - 1) if m > 1 else (y - 1, 12)
    ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
    rows = [[
        Btn("«", callback_data=f"cal:{mode}:{y - 1}:{m}"),
        Btn("‹", callback_data=f"cal:{mode}:{py}:{pm}"),
        Btn(f"{calendar.month_abbr[m]} {y} ▾", callback_data=f"yrs:{mode}:{y - 5}"),
        Btn("›", callback_data=f"cal:{mode}:{ny}:{nm}"),
        Btn("»", callback_data=f"cal:{mode}:{y + 1}:{m}"),
    ], [Btn(x, callback_data="noop") for x in ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")]]
    for week in calendar.monthcalendar(y, m):
        row = []
        for d in week:
            if d == 0:
                row.append(Btn(" ", callback_data="noop"))
            else:
                lab = f"·{d}·" if (y, m, d) == (today.year, today.month, today.day) else str(d)
                row.append(Btn(lab, callback_data=f"day:{mode}:{y:04d}{m:02d}{d:02d}"))
        rows.append(row)
    last = [Btn("📍 Today", callback_data=f"day:{mode}:{today.year:04d}{today.month:02d}{today.day:02d}")]
    if mode != "b":
        last.append(Btn("🔴 Now", callback_data=f"tm:{mode}:now"))
    last.append(Btn("✖ Close", callback_data="close"))
    rows.append(last)
    return InlineKeyboardMarkup(rows)


def year_kb(mode, start, tz):
    start = max(1800, min(2389, start))
    rows = []
    for r in range(4):
        rows.append([Btn(str(start + r * 3 + c), callback_data=f"ys:{mode}:{start + r * 3 + c}")
                     for c in range(3)])
    n = local_now(tz)
    rows.append([Btn("◀ earlier", callback_data=f"yrs:{mode}:{start - 12}"),
                 Btn("This month", callback_data=f"cal:{mode}:{n.year}:{n.month}"),
                 Btn("later ▶", callback_data=f"yrs:{mode}:{start + 12}")])
    return InlineKeyboardMarkup(rows)


def month_kb(mode, y):
    rows = []
    for r in range(4):
        rows.append([Btn(calendar.month_abbr[r * 3 + c + 1], callback_data=f"cal:{mode}:{y}:{r * 3 + c + 1}")
                     for c in range(3)])
    rows.append([Btn("◀ Years", callback_data=f"yrs:{mode}:{y - 5}")])
    return InlineKeyboardMarkup(rows)


def hour_kb(mode, ds):
    rows = []
    for r in range(4):
        rows.append([Btn(f"{h:02d}", callback_data=f"hr:{mode}:{ds}:{h:02d}") for h in range(r * 6, r * 6 + 6)])
    rows.append([Btn("⏩ Skip (12:00)", callback_data=f"tm:{mode}:{ds}1200"),
                 Btn("◀ Calendar", callback_data=f"cal:{mode}:{int(ds[:4])}:{int(ds[4:6])}")])
    return InlineKeyboardMarkup(rows)


def minute_kb(mode, ds, hh):
    rows = []
    for r in range(2):
        rows.append([Btn(f"{hh}:{mi:02d}", callback_data=f"tm:{mode}:{ds}{hh}{mi:02d}")
                     for mi in range(r * 30, r * 30 + 30, 5)])
    rows.append([Btn("◀ Hours", callback_data=f"day:{mode}:{ds}")])
    return InlineKeyboardMarkup(rows)


def nav_kb(kind, dt, extra="", top=None, bottom=None):
    def cb(d):
        return f"{kind}:{stamp(d)}{extra}"
    rows = list(top or [])
    rows.append([Btn("⏮ 1m", callback_data=cb(add_months(dt, -1))),
                 Btn("◀ 1d", callback_data=cb(dt - timedelta(days=1))),
                 Btn("1d ▶", callback_data=cb(dt + timedelta(days=1))),
                 Btn("1m ⏭", callback_data=cb(add_months(dt, 1)))])
    rows.append([Btn("📅 Pick date", callback_data=f"cal:{MODE_OF[kind]}:{dt.year}:{dt.month}"),
                 Btn("🔴 Now", callback_data=f"{kind}:now{extra}")])
    rows.extend(bottom or [])
    rows.append([Btn("🏠 Menu", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def chart_kb():
    n = datetime.now()
    return InlineKeyboardMarkup([
        [Btn("🔮 Rashi", callback_data="ch:asc"), Btn("💠 Navamsa", callback_data="ch:nav"),
         Btn("🌟 Yogas", callback_data="ch:yog"), Btn("🌀 Dasha", callback_data="ch:das")],
        [Btn("🔄 New birth data", callback_data=f"cal:b:{n.year - 30}:{n.month}")],
        [Btn("🏠 Menu", callback_data="menu")],
    ])


# ───────────────────────── UI: VIEW BUILDERS ─────────────────────────
def build_view(kind, ud, tz, st, args):
    dt = parse_stamp(st, tz)
    if kind == "pos":
        planet = args[0] if args else "All"
        view = args[1] if len(args) > 1 else "d"
        if planet != "All" and planet not in ORDER:
            planet = "All"
        text = build_positions(dt, tz, planet, live=(st == "now"), view=view)
        row1 = [Btn("All", callback_data=f"pos:{st}:All:{view}")]
        row1 += [Btn(EMOJI[n], callback_data=f"pos:{st}:{n}:{view}") for n in ORDER[:4]]
        row2 = [Btn(EMOJI[n], callback_data=f"pos:{st}:{n}:{view}") for n in ORDER[4:]]
        toggle = (Btn("📋 Degree table", callback_data=f"pos:{st}:All:t") if view == "d"
                  else Btn("📖 Detailed", callback_data=f"pos:{st}:All:d"))
        kb = nav_kb("pos", dt, f":{planet}:{view}", top=[row1, row2], bottom=[[toggle]])
        return text, kb
    if kind == "pan":
        return build_panchang(dt, tz), nav_kb("pan", dt)
    if kind == "ing":
        return build_ingresses(dt, tz), nav_kb("ing", dt)
    # Gochar
    rashi = ud.get("rashi")
    if rashi is None:
        return rashi_picker(ud, st)
    kb = nav_kb("goc", dt, bottom=[[Btn("🌙 Change Rashi", callback_data=f"rs:menu:{st}")]])
    return build_gochar(dt, tz, rashi), kb


def rashi_picker(ud, st):
    rows = []
    for r in range(4):
        rows.append([Btn(f"{SIGN_SYM[i]} {RASHI[i]}", callback_data=f"rs:{i}:{st}")
                     for i in range(r * 3, r * 3 + 3)])
    if "birth" in ud:
        rows.append([Btn("🎂 Use my birth chart Moon", callback_data=f"rs:b:{st}")])
    rows.append([Btn("🏠 Menu", callback_data="menu")])
    return ("🌙 <b>Select your Janma Rashi</b> (Moon sign)\nNeeded for Gochar. "
            "Tip: create a birth chart and it's picked automatically."), InlineKeyboardMarkup(rows)


HELP = (
    "🕉 <b>Vedic Astro Bot</b> <i>(Sidereal · Lahiri)</i>\n\n"
    "🪐 /now – live planetary degrees\n"
    "📅 /date – pick any date from a calendar\n"
    "🕉 /panchang – tithi, nakshatra, yoga, karana\n"
    "🔮 /ingress – upcoming sign changes\n"
    "🌙 /gochar – transits from your Moon sign\n"
    "🎂 /birth – birth chart, Navamsa, yogas, dasha\n"
    "🕰 /tz – set timezone (default IST)\n\n"
    "💡 You can also just <b>type a date</b>: <code>14 may 2030</code>, "
    "<code>2030-05-14 18:30</code>, <code>+10</code>, <code>-3m</code>, <code>tomorrow</code>\n\n"
    "<b>R</b> = Retrograde · <b>C</b> = Combust"
)


# ───────────────────────── TELEGRAM HELPERS ─────────────────────────
CALC_LOCK = asyncio.Lock()  # swisseph keeps global state, so run calculations one at a time


async def run_calc(fn, *a):
    async with CALC_LOCK:
        return await asyncio.to_thread(fn, *a)


async def deliver(update, text, kb=None):
    q = update.callback_query
    try:
        if q:
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb,
                                      disable_web_page_preview=True)
        else:
            await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML,
                                                      reply_markup=kb, disable_web_page_preview=True)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            log.exception("deliver failed")
            raise


async def show_view(update, ctx, kind, st="now", args=()):
    tz = get_tz(ctx)
    try:
        text, kb = await run_calc(build_view, kind, ctx.user_data, tz, st, list(args))
    except Exception:
        log.exception("view failed")
        await deliver(update, "⚠️ Couldn't calculate that date. Try another one.", None)
        return
    await deliver(update, text, kb)


async def show_chart(update, ctx, page="asc"):
    ud = ctx.user_data
    if "birth" not in ud or "lat" not in ud:
        await start_birth(update, ctx)
        return
    try:
        text = await run_calc(build_chart, ud, get_tz(ctx), page)
    except Exception:
        log.exception("chart failed")
        await deliver(update, "⚠️ Couldn't build the chart. Check your birth data with /birth.", None)
        return
    await deliver(update, text, chart_kb())


async def start_birth(update, ctx):
    tz = get_tz(ctx)
    n = local_now(tz)
    ctx.user_data.pop("await", None)
    await deliver(update, "🎂 <b>Birth Chart</b>\nPick your <b>birth date</b> "
                          "(tap the month ▾ to jump to a year):",
                  calendar_kb("b", n.year - 30, n.month, tz))


# ───────────────────────── COMMANDS ─────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("await", None)
    await update.message.reply_text(HELP, parse_mode=ParseMode.HTML, reply_markup=menu_kb(get_tz(ctx)))


async def cmd_now(update, ctx):
    await show_view(update, ctx, "pos", "now", ("All", "d"))


async def cmd_date(update, ctx):
    tz = get_tz(ctx)
    n = local_now(tz)
    await update.message.reply_text(
        f"{MODE_TITLE['p']}\n📅 Pick a date (tap the month ▾ to jump to another year):",
        parse_mode=ParseMode.HTML, reply_markup=calendar_kb("p", n.year, n.month, tz))


async def cmd_panchang(update, ctx):
    await show_view(update, ctx, "pan", "now")


async def cmd_ingress(update, ctx):
    await show_view(update, ctx, "ing", "now")


async def cmd_gochar(update, ctx):
    await show_view(update, ctx, "goc", "now")


async def cmd_birth(update, ctx):
    await start_birth(update, ctx)


async def cmd_tz(update, ctx):
    if ctx.args:
        v = parse_tz(" ".join(ctx.args))
        if v is None:
            await update.message.reply_text("❌ Use e.g. /tz +5:30, /tz -8 or /tz IST")
            return
        ctx.user_data["tz"] = v
        await update.message.reply_text(f"✅ Timezone set to <b>{tz_label(v)}</b>", parse_mode=ParseMode.HTML)
        return
    await tz_menu(update, ctx)


async def tz_menu(update, ctx):
    rows = []
    for i in range(0, len(COMMON_TZ), 2):
        rows.append([Btn(t, callback_data=f"tz:{v}") for t, v in COMMON_TZ[i:i + 2]])
    rows.append([Btn("✏️ Custom", callback_data="tz:custom"), Btn("🏠 Menu", callback_data="menu")])
    await deliver(update, f"🕰 <b>Timezone</b>\nCurrent: <b>{tz_label(get_tz(ctx))}</b>\nChoose one:",
                  InlineKeyboardMarkup(rows))


async def cmd_cancel(update, ctx):
    ctx.user_data.pop("await", None)
    await update.message.reply_text("Cancelled. /start for the menu.")


# ───────────────────────── CALLBACKS ─────────────────────────
async def on_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    p = q.data.split(":")
    k = p[0]
    tz = get_tz(ctx)
    ud = ctx.user_data

    if k == "noop":
        return
    if k == "close":
        try:
            await q.message.delete()
        except BadRequest:
            pass
        return
    if k == "menu":
        await deliver(update, HELP, menu_kb(tz))
        return
    if k == "help":
        await deliver(update, HELP, menu_kb(tz))
        return

    if k == "cal":
        mode, y, m = p[1], int(p[2]), int(p[3])
        y = max(1800, min(2400, y))
        sub = "birth date" if mode == "b" else "date"
        await deliver(update, f"{MODE_TITLE[mode]}\n📅 Pick a <b>{sub}</b> "
                              f"(tap the month ▾ to jump to another year):", calendar_kb(mode, y, m, tz))
        return
    if k == "yrs":
        mode, start = p[1], int(p[2])
        await deliver(update, f"{MODE_TITLE[mode]}\n🗓 Pick a <b>year</b>:", year_kb(mode, start, tz))
        return
    if k == "ys":
        mode, y = p[1], int(p[2])
        await deliver(update, f"{MODE_TITLE[mode]}\n🗓 <b>{y}</b> – pick a <b>month</b>:", month_kb(mode, y))
        return
    if k == "day":
        mode, ds = p[1], p[2]
        d = datetime(int(ds[:4]), int(ds[4:6]), int(ds[6:8]))
        await deliver(update, f"{MODE_TITLE[mode]}\n📅 <b>{fmt_date(d)}</b>\n🕒 Pick the <b>hour</b> (24h):",
                      hour_kb(mode, ds))
        return
    if k == "hr":
        mode, ds, hh = p[1], p[2], p[3]
        d = datetime(int(ds[:4]), int(ds[4:6]), int(ds[6:8]))
        await deliver(update, f"{MODE_TITLE[mode]}\n📅 <b>{fmt_date(d)}</b> · <b>{hh}:__</b>\n"
                              f"⏱ Pick the <b>minute</b>:\n<i>Need an exact time? Just type it, "
                              f"e.g. {d.day:02d}/{d.month:02d}/{d.year} {hh}:37</i>",
                      minute_kb(mode, ds, hh))
        return
    if k == "tm":
        mode, st = p[1], p[2]
        if mode == "b":
            dt = parse_stamp(st, tz)
            ud["birth"] = dt
            ud["await"] = "loc"
            rows = []
            if "lat" in ud:
                rows.append([Btn("📍 Use my saved place", callback_data="ch:asc")])
            await deliver(update, f"🎂 Birth: <b>{fmt_dt(dt)}</b> <i>({tz_label(tz)})</i>\n\n"
                                  "Now send your <b>birth place</b>:\n"
                                  "• attach a 📍 <b>location pin</b>, or\n"
                                  "• type <code>latitude, longitude</code> e.g. <code>19.076, 72.877</code> "
                                  "(use minus for S/W)\n\n"
                                  "<i>Wrong timezone for your birth place? Use /tz first.</i>",
                          InlineKeyboardMarkup(rows) if rows else None)
            return
        kind = {"p": "pos", "n": "pan", "i": "ing", "g": "goc"}[mode]
        await show_view(update, ctx, kind, st, ("All", "d") if kind == "pos" else ())
        return

    if k in ("pos", "pan", "ing", "goc"):
        await show_view(update, ctx, k, p[1], p[2:])
        return

    if k == "rs":
        what, st = p[1], p[2]
        if what == "menu":
            text, kb = rashi_picker(ud, st)
            await deliver(update, text, kb)
            return
        if what == "b":
            try:
                pos = await run_calc(lambda: calc_positions(to_jd(ud["birth"], tz)))
                ud["rashi"] = int(pos["Moon"][0] // 30)
            except Exception:
                await deliver(update, "⚠️ Create your birth chart first (/birth).", None)
                return
        else:
            ud["rashi"] = int(what)
        await show_view(update, ctx, "goc", st)
        return

    if k == "ch":
        await show_chart(update, ctx, p[1])
        return

    if k == "tz":
        if p[1] == "menu":
            await tz_menu(update, ctx)
        elif p[1] == "custom":
            ud["await"] = "tz"
            await deliver(update, "✏️ Type your offset, e.g. <code>+5:30</code>, <code>-8</code>, <code>IST</code>", None)
        else:
            ud["tz"] = int(p[1])
            await deliver(update, f"✅ Timezone set to <b>{tz_label(ud['tz'])}</b>", menu_kb(ud["tz"]))
        return


# ───────────────────────── MESSAGES ─────────────────────────
async def on_location(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ud = ctx.user_data
    if ud.get("await") != "loc" or "birth" not in ud:
        await update.message.reply_text("Use /birth first, then send your birth place.")
        return
    loc = update.message.location
    ud["lat"], ud["lon"] = loc.latitude, loc.longitude
    ud.pop("await", None)
    await show_chart(update, ctx, "asc")


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ud = ctx.user_data
    txt = update.message.text.strip()
    tz = get_tz(ctx)
    aw = ud.get("await")

    if aw == "loc" and "birth" in ud:
        ll = parse_latlon(txt)
        if not ll:
            await update.message.reply_text("❌ Send as <code>lat, lon</code> e.g. <code>28.61, 77.21</code> "
                                            "or share a 📍 pin. /cancel to stop.", parse_mode=ParseMode.HTML)
            return
        ud["lat"], ud["lon"] = ll
        ud.pop("await", None)
        await show_chart(update, ctx, "asc")
        return

    if aw == "tz":
        v = parse_tz(txt)
        if v is None:
            await update.message.reply_text("❌ Try <code>+5:30</code>, <code>-8</code> or <code>IST</code>",
                                            parse_mode=ParseMode.HTML)
            return
        ud["tz"] = v
        ud.pop("await", None)
        await update.message.reply_text(f"✅ Timezone set to <b>{tz_label(v)}</b>", parse_mode=ParseMode.HTML)
        return

    dt = parse_when(txt, tz)
    if dt is None:
        await update.message.reply_text("🤔 Didn't get that. Try /date for the calendar, or type a date like "
                                        "<code>14 may 2030</code>.", parse_mode=ParseMode.HTML)
        return
    await show_view(update, ctx, "pos", stamp(dt), ("All", "d"))


async def post_init(app: Application):
    await app.bot.set_my_commands([
        BotCommand("start", "Menu"), BotCommand("now", "Live planetary degrees"),
        BotCommand("date", "Pick a date from calendar"), BotCommand("panchang", "Panchang"),
        BotCommand("ingress", "Upcoming sign changes"), BotCommand("gochar", "Transits from Moon sign"),
        BotCommand("birth", "Birth chart & dasha"), BotCommand("tz", "Set timezone"),
        BotCommand("cancel", "Cancel current input"),
    ])


def main():
    if not TOKEN or TOKEN == "8792120272:AAHvhMHbQNqg5lwAnwPXtPuf3R1mTVTHQUc":
        raise SystemExit("❌ Bot token missing! Set the TELEGRAM_TOKEN environment variable "
                         "(or edit the TOKEN line near the top of this file).")
    keep_alive()
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    for name, fn in [("start", cmd_start), ("help", cmd_start), ("now", cmd_now), ("date", cmd_date),
                     ("panchang", cmd_panchang), ("ingress", cmd_ingress), ("gochar", cmd_gochar),
                     ("birth", cmd_birth), ("chart", cmd_birth), ("tz", cmd_tz), ("cancel", cmd_cancel)]:
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(CallbackQueryHandler(on_cb))
    app.add_handler(MessageHandler(filters.LOCATION, on_location))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    log.info("Vedic astro bot running…")
    app.run_polling()


if __name__ == "__main__":
    main()
