import streamlit as st
import requests
import pandas as pd

# --- SECRETS & API CONFIG ---
ODDS_API_KEY = st.secrets.get("API_KEY", "MISSING_KEY")
LIVE_ODDS_URL = "https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds/"
HISTORICAL_ODDS_URL = "https://api.the-odds-api.com/v4/historical/sports/basketball_ncaab/odds/"

st.set_page_config(page_title="Sweet 16 Takeover", page_icon="🏀", layout="wide")

# --- INITIAL HAT PULL ---
INITIAL_MAP = {
    "Michigan": "Greg Doc", "Houston": "Ryan Doc", "UConn": "Joe Doc", "Michigan State": "DOB",
    "Texas": "Schroller", "Tennessee": "Jimmy A", "Purdue": "Jim Henry", "Iowa": "EJ",
    "Iowa State": "Sean W", "Arizona": "Wenzel", "Arkansas": "Burgess", "Illinois": "Seitz",
    "St. John's": "Nick", "Nebraska": "Ken", "Alabama": "Burgess dude", "Duke": "Tom"
}

# --- HARDCODED TOURNAMENT DATA ---
TEAM_INFO = {
    "Michigan": {"Seed": 1, "Region": "Midwest"}, "Houston": {"Seed": 2, "Region": "South"},
    "UConn": {"Seed": 2, "Region": "East"}, "Michigan State": {"Seed": 3, "Region": "East"},
    "Texas": {"Seed": 11, "Region": "West"}, "Tennessee": {"Seed": 6, "Region": "Midwest"},
    "Purdue": {"Seed": 2, "Region": "West"}, "Iowa": {"Seed": 9, "Region": "South"},
    "Iowa State": {"Seed": 2, "Region": "Midwest"}, "Arizona": {"Seed": 1, "Region": "West"},
    "Arkansas": {"Seed": 4, "Region": "West"}, "Illinois": {"Seed": 3, "Region": "South"},
    "St. John's": {"Seed": 5, "Region": "East"}, "Nebraska": {"Seed": 4, "Region": "South"},
    "Alabama": {"Seed": 4, "Region": "Midwest"}, "Duke": {"Seed": 1, "Region": "East"}
}

def normalize(name):
    """Strips all weird formatting, spaces, and abbreviations for bulletproof matching."""
    return name.lower().replace("state", "st").replace(".", "").strip()

# --- FETCHING ENGINES ---
@st.cache_data(ttl=60)
def get_espn_scores():
    primary = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?groups=50&limit=100"
    scores = requests.get(primary).json()
    if not scores.get('events'):
        scores = requests.get("https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard").json()
    return scores

@st.cache_data(ttl=900)
def get_live_odds(api_key):
    if api_key == "MISSING_KEY": return []
    params = {
        'apiKey': api_key, 'regions': 'us', 'markets': 'spreads,h2h',
        'bookmakers': 'draftkings', 'oddsFormat': 'american'
    }
    try:
        res = requests.get(LIVE_ODDS_URL, params=params)
        return res.json() if res.status_code == 200 else []
    except: return []

@st.cache_data(ttl=None) 
def get_historical_odds(target_utc_date, api_key):
    if api_key == "MISSING_KEY": return {"error": "Missing API Key"}
    params = {
        'apiKey': api_key, 'regions': 'us', 'markets': 'spreads,h2h',
        'bookmakers': 'draftkings', 'oddsFormat': 'american', 'date': target_utc_date
    }
    try:
        res = requests.get(HISTORICAL_ODDS_URL, params=params)
        if res.status_code == 200:
            return res.json()
        else:
            return {"error": f"API Rejected: {res.status_code} - {res.text}"}
    except Exception as e:
        return {"error": str(e)}

def calculate_win_prob(odds):
    if odds == 0: return 0.50
    if odds > 0: return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)

def safe_int(val):
    try: return int(val)
    except: return 0

def process_pool(espn_data):
    current_owners = INITIAL_MAP.copy()
    takeover_logs, match_list, api_errors = [], [], []
    
    live_odds = get_live_odds(ODDS_API_KEY)
    now_et = pd.Timestamp.utcnow().tz_convert('America/New_York')
    
    events = espn_data.get('events', [])
    for event in events:
        try:
            competitions = event.get('competitions', [{}])[0]
            teams = competitions.get('competitors', [])
            if len(teams) < 2: continue
            
            date_str = event.get('date', '2026-01-01T00:00:00Z')
            game_time_et = pd.to_datetime(date_str, utc=True).tz_convert('America/New_York')
            
            is_locked = False
            if now_et.date() > game_time_et.date():
                is_locked = True
            elif now_et.date() == game_time_et.date() and now_et.hour >= 16:
                is_locked = True
            
            home = next((t for t in teams if t.get('homeAway') == 'home'), teams[0])
            away = next((t for t in teams if t.get('homeAway') == 'away'), teams[1])
            
            h_name = home.get('team', {}).get('displayName', 'Unknown')
            a_name = away.get('team', {}).get('displayName', 'Unknown')
            
            h_key = next((k for k in INITIAL_MAP.keys() if k.lower() in h_name.lower()), h_name)
            a_key = next((k for k in INITIAL_MAP.keys() if k.lower() in a_name.lower()), a_name)
            
            h_seed = TEAM_INFO.get(h_key, {}).get("Seed", "—")
            a_seed = TEAM_INFO.get(a_key, {}).get("Seed", "—")
            
            h_score, a_score = safe_int(home.get('score', 0)), safe_int(away.get('score', 0))
            status = event.get('status', {}).get('type', {}).get('state', 'pre')
            short_detail = event.get('status', {}).get('type', {}).get('shortDetail', 'TBD')
            
            spread, ml = 0, 0
            last_update_str = None
            using_fallback = False
            
            if is_locked:
                lock_time_utc = game_time_et.replace(hour=16, minute=0, second=0).tz_convert('UTC')
                lock_time_utc_str = lock_time_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
                
                hist_response = get_historical_odds(lock_time_utc_str, ODDS_API_KEY)
                
                if "error" in hist_response:
                    if hist_response["error"] not in api_errors:
                        api_errors.append(hist_response["error"])
                    odds_to_search = live_odds
                    using_fallback = True
                else:
                    odds_to_search = hist_response.get('data', [])
                    if not odds_to_search:
                        odds_to_search = live_odds
                        using_fallback = True
            else:
                odds_to_search = live_odds

            n_h_key = normalize(h_key)
            n_a_key = normalize(a_key)
            
            if odds_to_search and isinstance(odds_to_search, list):
                for game in odds_to_search:
                    n_odds_home = normalize(game.get('home_team', ''))
                    n_odds_away = normalize(game.get('away_team', ''))
                    
                    if (n_h_key in n_odds_home or n_h_key in n_odds_away) and \
                       (n_a_key in n_odds_home or n_a_key in n_odds_away):
                        
                        bms = game.get('bookmakers', [])
                        if not bms: continue
                        markets = bms[0].get('markets', [])
                        
                        m_spread = next((m for m in markets if m.get('key') == 'spreads'), None)
                        if m_spread and m_spread.get('outcomes'): 
                            last_update_str = m_spread.get('last_update')
                            for out in m_spread['outcomes']:
                                if n_h_key in normalize(out.get('name', '')):
                                    spread = float(out.get('point', 0))
                                    break
                                    
                        m_h2h = next((m for m in markets if m.get('key') == 'h2h'), None)
                        if m_h2h and m_h2h.get('outcomes'): 
                            for out in m_h2h['outcomes']:
                                if n_h_key in normalize(out.get('name', '')):
                                    ml = float(out.get('price', 0))
                                    break
                        break

            h_win_prob = calculate_win_prob(ml)
            h_owner = current_owners.get(h_key, "N/A")
            a_owner = current_owners.get(a_key, "N/A")
            
            # --- VISUAL LOCK FORMATTING WITH DRAFTKINGS TIMESTAMP ---
            lock_info = ""
            if is_locked and not using_fallback and last_update_str:
                try:
                    dt = pd.to_datetime(last_update_str, utc=True).tz_convert('America/New_York')
                    formatted_time = dt.strftime('%I:%M %p').lstrip('0')
                    lock_info = f" (DraftKings @ {formatted_time} ET)"
                except:
                    lock_info = " (DraftKings)"

            display_spread = f"{h_name} {spread}"
            if is_locked and not using_fallback:
                display_spread = f"🔒 {h_name} {spread}{lock_info}"
            elif is_locked and using_fallback:
                display_spread = f"⚠️ {h_name} {spread}"
            
            cover_status = "—"
            if status == 'in':
                if (h_score + spread) > a_score:
                    cover_status = f"✅ {h_name} Covering" if h_score < a_score else "Leader Covering"
                else:
                    cover_status = f"✅ {a_name} Covering" if a_score < h_score else "Leader Covering"

            match_list.append({
                "Matchup": f"({a_seed}) {a_name} @ ({h_seed}) {h_name}",
                "Status": short_detail,
                "Score": f"{a_score} - {h_score}",
                "Favorite": f"⭐ {h_name}" if spread < 0 else f"⭐ {a_name}",
                "Away Owner": a_owner,
                "Home Owner": h_owner,
                "Spread": display_spread,
                "Win Prob": f"{h_name} {h_win_prob:.1%}" if ml != 0 else "—",
                "Live Cover": cover_status
            })

            if status == 'post':
                winner = h_name if h_score > a_score else a_name
                new_owner = h_owner if (h_score + spread) > a_score else a_owner
                winner_key = next((k for k in INITIAL_MAP.keys() if k.lower() in winner.lower()), winner)
                if current_owners[winner_key] != new_owner:
                    takeover_logs.append(f"🔄 **{new_owner}** took over **{winner}** (Closing Spread: {spread})")
                current_owners[winner_key] = new_owner
                
        except Exception as e:
            st.warning(f"Error processing a game: {str(e)}")
            continue
            
    return current_owners, match_list, takeover_logs, api_errors

# --- UI ---
st.title("🏀 Sweet 16 Takeover Pool")

try:
    scores = get_espn_scores()
    owners, matches, logs, api_errors = process_pool(scores)

    if api_errors:
        for err in api_errors:
            st.error(f"Historical Odds Error: {err}. App has fallen back to Live Odds.")

    st.header("🕒 Matchups & Live Coverage", help="A 🔒 indicates the historical DraftKings line has been permanently frozen. The timestamp shows exactly when DraftKings posted that line.")
    if matches:
        st.dataframe(pd.DataFrame(matches), hide_index=True, use_container_width=True)
    else:
        st.info("Waiting for ESPN to populate the active scoreboard. Check back shortly.")

    st.divider()
    col1, col2 = st.columns([1.5, 1])
    
    with col1:
        st.header("✅ Owners Still Alive")
        alive_data = []
        for team, owner in owners.items():
            info = TEAM_INFO.get(team, {"Region": "Unknown", "Seed": 99})
            alive_data.append({
                "Region": info["Region"],
                "Seed": info["Seed"],
                "Owner": owner, 
                "Holding Team": team
            })
            
        df_alive = pd.DataFrame(alive_data)
        df_alive = df_alive.sort_values(by=["Region", "Seed"])
        
        st.dataframe(df_alive, hide_index=True, use_container_width=True)

    with col2:
        st.header("💰 Pool & Payouts")
        st.metric("Total Pot", "$1,600")
        st.write("🏆 **1st Place:** $900")
        st.write("🥈 **2nd Place:** $400")
        st.write("🎟️ **F4 Losers:** $100 back (x2)")
        
        st.divider()
        st.header("📜 Takeover History")
        if logs:
            for log in logs: st.info(log)
        else:
            st.write("No takeovers recorded yet.")

except Exception as e:
    st.error(f"Critical Error: {e}")
