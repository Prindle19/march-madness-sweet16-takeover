import streamlit as st
import requests
import pandas as pd
import json
import os

# --- SECRETS & API CONFIG ---
ODDS_API_KEY = st.secrets.get("API_KEY", "MISSING_KEY")
ODDS_URL = "https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds/"

LOCKED_ODDS_FILE = "locked_odds.json"

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

# --- ODDS LOCKING SYSTEM ---
def load_locked_odds():
    if os.path.exists(LOCKED_ODDS_FILE):
        with open(LOCKED_ODDS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_locked_odds(odds_dict):
    with open(LOCKED_ODDS_FILE, "w") as f:
        json.dump(odds_dict, f)

# --- QUOTA-SAVVY FETCHING ---
@st.cache_data(ttl=60) # ESPN is free, refresh every 60s
def get_espn_scores():
    primary = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates=20260326-20260329&limit=100"
    scores = requests.get(primary).json()
    if not scores.get('events'):
        scores = requests.get("https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard").json()
    return scores

@st.cache_data(ttl=900) # SHARED CACHE: 15 minutes! Protects your quota.
def get_draftkings_odds():
    if ODDS_API_KEY == "MISSING_KEY": return []
    params = {
        'apiKey': ODDS_API_KEY, 
        'regions': 'us', 
        'markets': 'spreads,h2h', # Both markets returned
        'bookmakers': 'draftkings', # Isolated to DK
        'oddsFormat': 'american'
    }
    return requests.get(ODDS_URL, params=params).json()

def calculate_win_prob(odds):
    if odds == 0: return 0.50
    if odds > 0: return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)

def process_pool(espn_data, odds_data):
    current_owners = INITIAL_MAP.copy()
    takeover_logs, match_list = [], []
    
    locked_odds = load_locked_odds()
    odds_were_updated = False
    
    events = espn_data.get('events', [])
    for event in events:
        try:
            competitions = event.get('competitions', [{}])[0]
            teams = competitions.get('competitors', [])
            if len(teams) < 2: continue
            
            home = next(t for t in teams if t['homeAway'] == 'home')
            away = next(t for t in teams if t['homeAway'] == 'away')
            
            h_name, a_name = home['team']['displayName'], away['team']['displayName']
            matchup_id = f"{a_name}_at_{h_name}"
            
            h_key = next((k for k in INITIAL_MAP.keys() if k.lower() in h_name.lower()), h_name)
            a_key = next((k for k in INITIAL_MAP.keys() if k.lower() in a_name.lower()), a_name)
            
            h_seed = TEAM_INFO.get(h_key, {}).get("Seed", "—")
            a_seed = TEAM_INFO.get(a_key, {}).get("Seed", "—")
            
            h_score, a_score = int(home.get('score', 0)), int(away.get('score', 0))
            status = event['status']['type']['state']
            
            spread, ml = 0, 0
            if status == 'pre':
                if odds_data and isinstance(odds_data, list):
                    for game in odds_data:
                        if h_name in game.get('home_team', "") or a_name in game.get('home_team', ""):
                            markets = game.get('bookmakers', [{}])[0].get('markets', [])
                            
                            m_spread = next((m for m in markets if m['key'] == 'spreads'), None)
                            if m_spread: spread = m_spread['outcomes'][0]['point']
                                
                            m_h2h = next((m for m in markets if m['key'] == 'h2h'), None)
                            if m_h2h: ml = m_h2h['outcomes'][0]['price']
                                
                            locked_odds[matchup_id] = {"spread": spread, "ml": ml}
                            odds_were_updated = True
                            break
            else:
                locked = locked_odds.get(matchup_id, {"spread": 0, "ml": 0})
                spread = locked.get("spread", 0)
                ml = locked.get("ml", 0)

            h_win_prob = calculate_win_prob(ml)
            h_owner, a_owner = current_owners.get(h_key, "N/A"), current_owners.get(a_key, "N/A")
            
            cover_status = "—"
            if status == 'in':
                if (h_score + spread) > a_score:
                    cover_status = f"✅ {h_name} Covering" if h_score < a_score else "Leader Covering"
                else:
                    cover_status = f"✅ {a_name} Covering" if a_score < h_score else "Leader Covering"

            match_list.append({
                "Matchup": f"({a_seed}) {a_name} @ ({h_seed}) {h_name}",
                "Status": event['status']['type']['shortDetail'],
                "Score": f"{a_score} - {h_score}",
                "Favorite": f"⭐ {h_name}" if spread < 0 else f"⭐ {a_name}",
                "Away Owner": a_owner,
                "Home Owner": h_owner,
                "Locked Spread": f"{h_name} {spread}",
                "Win Prob": f"{h_name} {h_win_prob:.1%}",
                "Live Cover": cover_status
            })

            if status == 'post':
                winner = h_name if h_score > a_score else a_name
                new_owner = h_owner if (h_score + spread) > a_score else a_owner
                winner_key = next((k for k in INITIAL_MAP.keys() if k.lower() in winner.lower()), winner)
                if current_owners[winner_key] != new_owner:
                    takeover_logs.append(f"🔄 **{new_owner}** took over **{winner}** (Closing Spread: {spread})")
                current_owners[winner_key] = new_owner
        except: continue
        
    if odds_were_updated:
        save_locked_odds(locked_odds)
        
    return current_owners, match_list, takeover_logs

# --- UI ---
st.title("🏀 Sweet 16 Takeover Pool")

try:
    scores = get_espn_scores()
    odds = get_draftkings_odds()
    owners, matches, logs = process_pool(scores, odds)

    st.header("🕒 Matchups & Live Coverage", help="Odds are fetched from DraftKings and refresh every 15 mins. Once a game tips off, the line permanently locks.")
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
