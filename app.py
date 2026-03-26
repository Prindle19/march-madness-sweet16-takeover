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

# --- FETCHING ENGINES ---
@st.cache_data(ttl=60)
def get_espn_scores():
    primary = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?groups=50&limit=100"
    scores = requests.get(primary).json()
    if not scores.get('events'):
        scores = requests.get("https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard").json()
    return scores

@st.cache_data(ttl=900)
def get_live_odds():
    if ODDS_API_KEY == "MISSING_KEY": return []
    params = {
        'apiKey': ODDS_API_KEY, 'regions': 'us', 'markets': 'spreads,h2h',
        'bookmakers': 'draftkings', 'oddsFormat': 'american'
    }
    try:
        res = requests.get(LIVE_ODDS_URL, params=params)
        return res.json() if res.status_code == 200 else []
    except: return []

@st.cache_data(ttl=None) # Cache indefinitely once pulled
def get_historical_odds(target_utc_date):
    if ODDS_API_KEY == "MISSING_KEY": return {}
    params = {
        'apiKey': ODDS_API_KEY, 'regions': 'us', 'markets': 'spreads,h2h',
        'bookmakers': 'draftkings', 'oddsFormat': 'american', 'date': target_utc_date
    }
    try:
        res = requests.get(HISTORICAL_ODDS_URL, params=params)
        return res.json() if res.status_code == 200 else {}
    except: return {}

def calculate_win_prob(odds):
    if odds == 0: return 0.50
    if odds > 0: return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)

def safe_int(val):
    try: return int(val)
    except: return 0

def process_pool(espn_data):
    current_owners = INITIAL_MAP.copy()
    takeover_logs, match_list = [], []
    
    live_odds = get_live_odds()
    
    # Grab the current time directly in Eastern Time
    now_et = pd.Timestamp.utcnow().tz_convert('America/New_York')
    
    events = espn_data.get('events', [])
    for event in events:
        try:
            competitions = event.get('competitions', [{}])[0]
            teams = competitions.get('competitors', [])
            if len(teams) < 2: continue
            
            # 1. Bulletproof Date Parsing using Pandas
            date_str = event.get('date', '2026-01-01T00:00:00Z')
            game_time_et = pd.to_datetime(date_str, utc=True).tz_convert('America/New_York')
            
            # Determine if this game has passed its 4:00 PM lock window
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
            
            h_score = safe_int(home.get('score', 0))
            a_score = safe_int(away.get('score', 0))
            
            status = event.get('status', {}).get('type', {}).get('state', 'pre')
            short_detail = event.get('status', {}).get('type', {}).get('shortDetail', 'TBD')
            
            # 2. Select Odds Source Safely
            spread, ml = 0, 0
            if is_locked:
                # Format exactly to 4:00 PM ET -> UTC String
                lock_time_utc = game_time_et.replace(hour=16, minute=0, second=0).tz_convert('UTC')
                lock_time_utc_str = lock_time_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
                
                hist_response = get_historical_odds(lock_time_utc_str)
                odds_to_search = hist_response.get('data', [])
            else:
                odds_to_search = live_odds

            # 3. Find the lines safely
            if odds_to_search and isinstance(odds_to_search, list):
                for game in odds_to_search:
                    if h_name in game.get('home_team', "") or a_name in game.get('home_team', ""):
                        bms = game.get('bookmakers', [])
                        if not bms: continue
                        markets = bms[0].get('markets', [])
                        
                        m_spread = next((m for m in markets if m.get('key') == 'spreads'), None)
                        if m_spread and m_spread.get('outcomes'): 
                            spread = float(m_spread['outcomes'][0].get('point', 0))
                            
                        m_h2h = next((m for m in markets if m.get('key') == 'h2h'), None)
                        if m_h2h and m_h2h.get('outcomes'): 
                            ml = float(m_h2h['outcomes'][0].get('price', 0))
                        break

            h_win_prob = calculate_win_prob(ml)
            h_owner = current_owners.get(h_key, "N/A")
            a_owner = current_owners.get(a_key, "N/A")
            
            display_spread = f"🔒 {h_name} {spread}" if is_locked else f"{h_name} {spread}"
            
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
            # Now we actually print the error to figure out what broke!
            st.warning(f"Error processing {h_name if 'h_name' in locals() else 'a game'}: {str(e)}")
            continue
            
    return current_owners, match_list, takeover_logs

# --- UI ---
st.title("🏀 Sweet 16 Takeover Pool")

try:
    scores = get_espn_scores()
    owners, matches, logs = process_pool(scores)

    st.header("🕒 Matchups & Live Coverage", help="A 🔒 indicates the game has passed 4:00 PM ET and the historical DraftKings line has been permanently frozen.")
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
