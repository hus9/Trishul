"""Universe, thresholds, capital sizing, and feature toggles for Engine I --
the same two-stage momentum idea as MomentumUS (Engine E's sibling on NASDAQ), applied
to NSE/BSE India via Zerodha Kite Connect.
"""

# ---- Universe ------------------------------------------------------------
# NIFTY 500 constituents (as of 2026-08), pulled live from the official NSE Indices CSV
# (niftyindices.com/IndexConstituent/ind_nifty500list.csv). Widened from the original
# NIFTY 200 scope-down now that a full fetch has been requested; historical fetch is
# still rate-limited (~3 req/sec, see data_fetch.py) so a full universe run takes a while.
NIFTY_500 = [
    "360ONE", "3MINDIA", "ABB", "ACC", "ACMESOLAR", "AIAENG", "APLAPOLLO", "AUBANK",
    "AWL", "AADHARHFC", "AARTIIND", "AAVAS", "ABBOTINDIA", "ACE", "ACUTAAS", "ADANIENSOL",
    "ADANIENT", "ADANIGREEN", "ADANIPORTS", "ADANIPOWER", "ATGL", "ABCAPITAL", "ABFRL", "ABLBL",
    "ABREL", "ABSLAMC", "CPPLUS", "AEGISLOG", "AEGISVOPAK", "AFCONS", "AFFLE", "AJANTPHARM",
    "ALKEM", "ABDL", "ARE&M", "AMBER", "AMBUJACEM", "ANANDRATHI", "ANANTRAJ", "ANGELONE",
    "ANTHEM", "ANURAS", "APARINDS", "APOLLOHOSP", "APOLLOTYRE", "APTUS", "ASAHIINDIA", "ASHOKLEY",
    "ASIANPAINT", "ASTERDM", "ASTRAL", "ATHERENERG", "ATUL", "AUROPHARMA", "AIIL", "DMART",
    "AXISBANK", "BEML", "BLS", "BSE", "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BAJAJHLDNG",
    "BAJAJHFL", "BALKRISIND", "BALRAMCHIN", "BANDHANBNK", "BANKBARODA", "BANKINDIA", "MAHABANK", "BATAINDIA",
    "BAYERCROP", "BELRISE", "BERGEPAINT", "BDL", "BEL", "BHARATFORG", "BHEL", "BPCL",
    "BHARTIARTL", "BHARTIHEXA", "BIKAJI", "GROWW", "BIOCON", "BSOFT", "BLUEDART", "BLUEJET",
    "BLUESTARCO", "BBTC", "BOSCHLTD", "FIRSTCRY", "BRIGADE", "BRITANNIA", "MAPMYINDIA", "CCL",
    "CESC", "CGPOWER", "CIEINDIA", "CRISIL", "CANFINHOME", "CANBK", "CANHLIFE", "CAPLIPOINT",
    "CGCL", "CARBORUNIV", "CARTRADE", "CASTROLIND", "CEATLTD", "CEMPRO", "CENTRALBK", "CDSL",
    "CHALET", "CHAMBLFERT", "CHENNPETRO", "CHOICEIN", "CHOLAHLDNG", "CHOLAFIN", "CIPLA", "CUB",
    "CLEAN", "COALINDIA", "COCHINSHIP", "COFORGE", "COHANCE", "COLPAL", "CAMS", "CONCORDBIO",
    "CONCOR", "COROMANDEL", "CRAFTSMAN", "CREDITACC", "CROMPTON", "CUMMINSIND", "CYIENT", "DCMSHRIRAM",
    "DLF", "DOMS", "DABUR", "DALBHARAT", "DATAPATTNS", "DEEPAKFERT", "DEEPAKNTR", "DELHIVERY",
    "DEVYANI", "DIVISLAB", "DIXON", "LALPATHLAB", "DRREDDY", "EIDPARRY", "EIHOTEL", "EICHERMOT",
    "ELECON", "ELGIEQUIP", "EMAMILTD", "EMCURE", "EMMVEE", "ENDURANCE", "ENGINERSIN", "ERIS",
    "ESCORTS", "ETERNAL", "EXIDEIND", "NYKAA", "FEDERALBNK", "FACT", "FINCABLES", "FSL",
    "FIVESTAR", "FORCEMOT", "FORTIS", "GAIL", "GVT&D", "GMRAIRPORT", "GABRIEL", "GALLANTT",
    "GRSE", "GICRE", "GILLETTE", "GLAND", "GLAXO", "GLENMARK", "MEDANTA", "GODIGIT",
    "GPIL", "GODFRYPHLP", "GODREJCP", "GODREJIND", "GODREJPROP", "GRANULES", "GRAPHITE", "GRASIM",
    "GRAVITA", "GESHIP", "FLUOROCHEM", "GMDCLTD", "HEG", "HBLENGINE", "HCLTECH", "HDBFS",
    "HDFCAMC", "HDFCBANK", "HDFCLIFE", "HFCL", "HAVELLS", "HEROMOTOCO", "HEXT", "HSCL",
    "HINDALCO", "HAL", "HINDCOPPER", "HINDPETRO", "HINDUNILVR", "HINDZINC", "POWERINDIA", "HOMEFIRST",
    "HONASA", "HONAUT", "HUDCO", "HYUNDAI", "ICICIBANK", "ICICIGI", "ICICIAMC", "ICICIPRULI",
    "IDBI", "IDFCFIRSTB", "IFCI", "IIFL", "IRB", "IRCON", "ITCHOTELS", "ITC",
    "ITI", "INDGN", "INDIACEM", "INDIAMART", "INDIANB", "IEX", "INDHOTEL", "IOC",
    "IOB", "IRCTC", "IRFC", "IREDA", "IGL", "INDUSTOWER", "INDUSINDBK", "NAUKRI",
    "INFY", "INOXWIND", "INTELLECT", "INDIGO", "IGIL", "IKS", "IPCALAB", "JKCEMENT",
    "JBMA", "JKTYRE", "JMFINANCIL", "JSWCEMENT", "JSWDULUX", "JSWENERGY", "JSWINFRA", "JSWSTEEL",
    "JAINREC", "JPPOWER", "J&KBANK", "JINDALSAW", "JSL", "JINDALSTEL", "JIOFIN", "JUBLFOOD",
    "JUBLINGREA", "JUBLPHARMA", "JWL", "JYOTICNC", "KPRMILL", "KEI", "KPITTECH", "KAJARIACER",
    "KPIL", "KALYANKJIL", "KARURVYSYA", "KAYNES", "KEC", "KFINTECH", "KIRLOSENG", "KOTAKBANK",
    "KIMS", "LTF", "LTTS", "LGEINDIA", "LICHSGFIN", "LTFOODS", "LTM", "LT",
    "LATENTVIEW", "LAURUSLABS", "THELEELA", "LEMONTREE", "LENSKART", "LICI", "LINDEINDIA", "LLOYDSME",
    "LODHA", "LUPIN", "MMTC", "MRF", "MGL", "M&MFIN", "M&M", "MANAPPURAM",
    "MRPL", "MANKIND", "MARICO", "MARUTI", "MFSL", "MAXHEALTH", "MAZDOCK", "MEESHO",
    "MINDACORP", "MSUMI", "MOTILALOFS", "MPHASIS", "MCX", "MUTHOOTFIN", "NATCOPHARM", "NBCC",
    "NCC", "NHPC", "NLCINDIA", "NMDC", "NSLNISP", "NTPCGREEN", "NTPC", "NH",
    "NATIONALUM", "NAVA", "NAVINFLUOR", "NESTLEIND", "NETWEB", "NEULANDLAB", "NEWGEN", "NAM-INDIA",
    "NIVABUPA", "NUVAMA", "NUVOCO", "OBEROIRLTY", "ONGC", "OIL", "OLAELEC", "OLECTRA",
    "PAYTM", "ONESOURCE", "OFSS", "POLICYBZR", "PCBL", "PGEL", "PIIND", "PNBHOUSING",
    "PTCIL", "PVRINOX", "PAGEIND", "PARADEEP", "PATANJALI", "PERSISTENT", "PETRONET", "PFIZER",
    "PHOENIXLTD", "PWL", "PIDILITIND", "PINELABS", "PIRAMALFIN", "PPLPHARMA", "POLYMED", "POLYCAB",
    "POONAWALLA", "PFC", "POWERGRID", "PREMIERENE", "PRESTIGE", "PFOCUS", "PNB", "RRKABEL",
    "RBLBANK", "RECLTD", "RHIM", "RITES", "RADICO", "RVNL", "RAILTEL", "RAINBOW",
    "RKFORGE", "REDINGTON", "RELIANCE", "RPOWER", "SBFC", "SBICARD", "SBILIFE", "SJVN",
    "SRF", "SAGILITY", "SAILIFE", "SAMMAANCAP", "MOTHERSON", "SAPPHIRE", "SARDAEN", "SAREGAMA",
    "SCHAEFFLER", "SCHNEIDER", "SCI", "SHREECEM", "SHRIRAMFIN", "SHYAMMETL", "ENRIN", "SIEMENS",
    "SIGNATURE", "SOBHA", "SOLARINDS", "SONACOMS", "SONATSOFTW", "STARHEALTH", "SBIN", "SAIL",
    "SUMICHEM", "SUNPHARMA", "SUNTV", "SUNDARMFIN", "SUPREMEIND", "SPLPETRO", "SUZLON", "SWANCORP",
    "SWIGGY", "SYNGENE", "SYRMA", "TBOTEK", "TVSMOTOR", "TATACAP", "TATACHEM", "TATACOMM",
    "TCS", "TATACONSUM", "TATAELXSI", "TATAINVEST", "TMCV", "TMPV", "TATAPOWER", "TATASTEEL",
    "TATATECH", "TTML", "TECHM", "TECHNOE", "TEGA", "TEJASNET", "TENNIND", "NIACL",
    "RAMCOCEM", "THERMAX", "TIMKEN", "TITAGARH", "TITAN", "TORNTPHARM", "TORNTPOWER", "TARIL",
    "TRAVELFOOD", "TRENT", "TRIDENT", "TRITURBINE", "TIINDIA", "UCOBANK", "UNOMINDA", "UPL",
    "UTIAMC", "ULTRACEMCO", "UNIONBANK", "UBL", "UNITDSPR", "URBANCO", "USHAMART", "VTL",
    "VBL", "VEDL", "VIJAYA", "VMM", "IDEA", "VOLTAS", "WAAREEENER", "WELCORP",
    "WELSPUNLIV", "WHIRLPOOL", "WIPRO", "WOCKPHARMA", "YESBANK", "ZFCVINDIA", "ZEEL", "ZENTEC",
    "ZENSARTECH", "ZYDUSLIFE", "ZYDUSWELL", "ECLERX",
]
EXCHANGE = "NSE"  # all lookups/fetches go through NSE; BSE listings not included yet

# ---- Stage 1 (EOD screen) thresholds --------------------------------------
MIN_DAILY_GAIN_PCT = 0.02          # close-to-close gain > 2%
CLOSE_NEAR_HIGH_FRACTION = 0.25    # close >= high - 0.25*(high-low)
MIN_RELATIVE_VOLUME = 2.0          # day volume / 20d avg volume

# ---- Stage 2 (intraday confirmation) thresholds ---------------------------
GAP_UP_THRESHOLD = 1.002           # open >= prior_close * this
MIN_FIRST_15MIN_RELATIVE_VOLUME = 1.5
SWING_HIGH_LOOKBACK_DAYS = 5
RSI_PERIOD = 14
RSI_MIN = 45
INTRADAY_HISTORY_DAYS = 60         # Kite Connect free-plan minute-data lookback cap

# ---- Risk / position sizing (ASSUMPTION -- confirm before running live) --
CAPITAL = 300_000                  # INR 3L, same starting figure as the main US project
CAPITAL_PCT_PER_TRADE = 0.10
ATR_STOP_MULT = 1.5
MAX_CONCURRENT_POSITIONS = 3
FORCE_CLOSE_IST = "15:15"          # NSE cash closes 15:30; square off ahead of the close,
                                    # also ahead of most brokers' MIS auto-square-off window

# ---- Swing engine (multi-day, CNC, long-only) -- instruction.md section 4.2 ---------
SWING_CAPITAL = 300_000            # INR 3L, CNC segment, no leverage
SWING_RISK_PER_TRADE = 3_000       # 1% of SWING_CAPITAL, hard cap per trade
SWING_FAST_EMA = 10
SWING_SLOW_EMA = 30
SWING_ATR_PERIOD = 14
SWING_CHANDELIER_MULT = 3          # trailing stop = highest_high - mult * ATR
SWING_MAX_HOLD_DAYS = 5            # instruction.md: 1-5 day holding period

# ---- ORB+VWAP intraday, long/short -- instruction.md section 4.1 primary model ------
OR_BARS = 3                        # 3 x 5-min bars = first 15 minutes of the session
OR_VOLUME_MULT = 2.0               # first-15min volume vs its 5-day average
OR_VOLUME_LOOKBACK_DAYS = 5

# ---- Bollinger/RSI mean-reversion, short only -- instruction.md 4.1 secondary model --
BB_PERIOD = 20
BB_STD = 2.0
BB_RSI_PERIOD = 14
BB_RSI_OVERBOUGHT = 80
BB_ATR_PERIOD = 14
BB_STOP_ATR_MULT = 2.0             # trailing stop = lowest_low_since_entry + mult * ATR

# ---- Camarilla pivot range breakout, long/short -- prototype stock list first -------
CAMARILLA_PROTOTYPE_SYMBOLS = ["RELIANCE", "HDFCBANK", "ICICIBANK"]
CAMARILLA_VOLUME_MULT = 1.5        # breakout bar volume vs its rolling average
CAMARILLA_VOLUME_LOOKBACK_BARS = 20
CAMARILLA_ATR_PERIOD = 14
CAMARILLA_ATR_MULT = 5.0           # starting point -- same value tuned for orb_confluence
