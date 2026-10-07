import swisseph as swe
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from keep_alive import keep_alive # Keeps Render awake!

NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", 
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", 
    "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", 
    "Anuradha", "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha", 
    "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada", 
    "Uttara Bhadrapada", "Revati"
]

ZODIAC_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", 
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

# A master dictionary we can pull specific planets from
PLANET_MAP = {
    "Sun": ("☀️ Sun", swe.SUN),
    "Moon": ("🌙 Moon", swe.MOON),
    "Mars": ("🔴 Mars", swe.MARS),
    "Mercury": ("🟢 Mercury", swe.MERCURY),
    "Jupiter": ("🟡 Jupiter", swe.JUPITER),
    "Venus": ("💖 Venus", swe.VENUS),
    "Saturn": ("🪐 Saturn", swe.SATURN),
    "Rahu": ("🌪️ Rahu", swe.TRUE_NODE)
}

def get_astro_data(target_planet=None, offset_days=0):
    target_time = datetime.now(timezone.utc) + timedelta(days=offset_days)
    julian_day = swe.julday(target_time.year, target_time.month, target_time.day, target_time.hour + target_time.minute/60.0)
    
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL
    
    # Decide if we are calculating one planet or all of them
    items_to_calc = []
    if target_planet and target_planet in PLANET_MAP:
        items_to_calc.append(PLANET_MAP[target_planet])
    else:
        items_to_calc = list(PLANET_MAP.values())
        
    results = []
    for name, planet_id in items_to_calc:
        response = swe.calc_ut(julian_day, planet_id, flags)
        lon = response[0][0]
        speed = response[0][3]
        
        sign_index = int(lon / 30)
        deg = lon % 30
        mins = int((deg - int(deg)) * 60)
        
        nak_index = int(lon / (360 / 27))
        nak_name = NAKSHATRAS[nak_index]
        pada = int((lon % (360/27)) / (360/108)) + 1
        retro = " (Rx)" if speed < 0 else ""
        
        results.append(
            f"<b>{name}{retro}</b>\n"
            f"↳ {ZODIAC_SIGNS[sign_index]} at {int(deg)}°{mins}'\n"
            f"↳ {nak_name} (Pada {pada})\n"
        )
        
    time_str = target_time.strftime("%B %d, %Y - %H:%M UTC")
    header = f"✨ <b>Planetary Positions (Lahiri)</b> ✨\n📅 <i>{time_str}</i>\n\n"
    return header + "\n".join(results)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✨ AstroBot is Live ✨\nSend /planets to open the dashboard.")

async def planets_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends the initial message with the inline keyboard grid."""
    # Build the 2-column button grid
    keyboard = [
        [InlineKeyboardButton("☀️ Sun", callback_data="planet_Sun"), InlineKeyboardButton("🌙 Moon", callback_data="planet_Moon")],
        [InlineKeyboardButton("🔴 Mars", callback_data="planet_Mars"), InlineKeyboardButton("🟢 Mercury", callback_data="planet_Mercury")],
        [InlineKeyboardButton("🟡 Jupiter", callback_data="planet_Jupiter"), InlineKeyboardButton("💖 Venus", callback_data="planet_Venus")],
        [InlineKeyboardButton("🪐 Saturn", callback_data="planet_Saturn"), InlineKeyboardButton("🌪️ Rahu", callback_data="planet_Rahu")],
        [InlineKeyboardButton("🌌 View All Planets", callback_data="planet_All")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("🔭 <b>Choose a planet to calculate its live position:</b>", reply_markup=reply_markup, parse_mode="HTML")

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the user clicking one of the inline buttons."""
    query = update.callback_query
    
    # Telegram requires you to 'answer' the query to stop the loading icon on the button
    await query.answer()
    
    # query.data contains the string we put in 'callback_data' (e.g., "planet_Mars")
    data = query.data 
    
    if data.startswith("planet_"):
        planet_name = data.split("_")[1] # Extracts "Mars" or "All"
        
        # Pass the choice to the math engine
        if planet_name == "All":
            result_text = get_astro_data(target_planet=None)
        else:
            result_text = get_astro_data(target_planet=planet_name)
            
        # Edit the original message to replace the buttons with the final math
        await query.edit_message_text(text=result_text, parse_mode="HTML")

if __name__ == "__main__":
    print("🚀 Bot is spinning up... Press CTRL+C to stop.")
    
    # Start the 24/7 keep-alive web server
    keep_alive()
    
    app = Application.builder().token("8792120272:AAHvhMHbQNqg5lwAnwPXtPuf3R1mTVTHQUc").build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("planets", planets_menu))
    
    # This handler listens specifically for inline button clicks
    app.add_handler(CallbackQueryHandler(button_click))
    
    app.run_polling()