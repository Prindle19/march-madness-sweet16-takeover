import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# --- SECRETS & API CONFIG ---
try:
    API_KEY = st.secrets["API_KEY"]
except KeyError:
    st.error("Missing API_KEY in Secrets! Please add it to your Streamlit App Settings.")
    st.stop()

# ESPN is free/unlimited; The Odds API is precious
ESPN_API = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"
ODDS_URL = "https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds/"

st.set_page_config(page_title="Sweet 16 Takeover", page_icon="🏀", layout="wide")

# --- INITIAL HAT PULL (From your provided image) ---
INITIAL_MAP = {
    "Michigan": "Greg Doc", "Houston": "Ryan Doc", "UConn": "Joe Doc", "Michigan State": "DOB",
    "Texas": "Schroller", "Tennessee": "Jimmy A", "Purdue": "Jim Henry", "Iowa": "EJ",
    "Iowa State": "Sean W", "Arizona": "Wenzel", "Arkansas": "Burgess", "Illinois": "Seitz",
    "St. John's": "Nick", "Nebraska": "Ken", "Alabama": "Burgess dude", "Duke": "Tom"
}

# --- QUOTA-SAVVY DATA FETCHING ---
@st.cache_data(ttl=60) # ESPN is free, refresh scores every minute
def get_espn_scores():
    return requests.get(ESPN_API).json()

@st.cache_data(ttl=900) # CACHE ODDS FOR 15 MINS to save quota
def get_combined_odds(_api_key):
    # Combine spreads and h2h (moneyline) into ONE API call
    params = {
        'apiKey': _api_key,
        'regions': 'us',
        'markets': 'spreads,h2h',
        'oddsFormat': 'american'
    }
    return requests.get(ODDS_URL, params=params).json()

def calculate_win_prob(odds):
    """Converts American odds to percentage"""
    if odds > 0: return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)

def process_pool(espn_data, odds_data):
    current_owners = INITIAL_MAP.copy()
    takeover_logs, upcoming, team_stats = [], [], {}
    
    events = espn_data.get('events', [])
    for event in events:
        try:
            teams = event['competitions'][0]['competitors']
            home = next(t for t in teams if t['homeAway'] == 'home')
            away = next(t for t in teams if t['homeAway'] == 'away')
            h_name, a_name = home['team']['displayName'], away['team']['displayName']
            status = event['status']['type']['state']
            
            # Match Combined Odds
            spread, h_win_prob = 0, 0.5
            for game in odds_data:
                if h_name in game['home_team'] or a_name in game['home_team']:
                    # Extract spread
                    spread_market = next((m for m in game['bookmakers'][0]['markets'] if m['key'] == 'spreads'), None)
                    if spread_market:
                        spread = spread_market['outcomes'][0]['point']
                    # Extract moneyline for win prob
                    ml_market = next((m for m in game['bookmakers'][0]['markets'] if m['key'] == 'h2h'), None)
                    if ml_market:
                        h_odds = ml_market['outcomes'][0]['price']
                        h_win_prob = calculate_win_prob(h_odds)
                    break

            h_seed, a_seed = home.get('curatedRank', 'N/A'), away.get('curatedRank', 'N/A')
            
            if status in ['pre', 'in']:
                upcoming.append({
                    "Matchup": f"({a_seed}) {a_name} @ ({h_seed}) {h_name}",
                    "Away Owner": current_owners.get(a_name, "N/A"),
                    "Home Owner": current_owners.get(h_name, "N/A"),
                    "Spread": f"{h_name} {spread}",
                    "Win Prob": f"{h_name} {h_win_prob:.1%}",
                    "Status": event['status']['type']['shortDetail']
                })

            if status == 'post':
                h_score, a_score = int(home['score']), int(away['score'])
                winner = h_name if h_score > a_score else a_name
                new_owner = current_owners.get(h_name) if (h_score + spread) > a_score else current_owners.get(a_name)
                
                winner_key = next((k for k in INITIAL_MAP.keys() if k in winner), winner)
                if current_owners[winner_key] != new_owner:
                    takeover_logs.append(f"🔄 **{new_owner}** took over **{winner}** (Spread: {spread})")
                current_owners[winner_key] = new_owner
        except Exception: continue
    return current_owners, upcoming, takeover_logs

# --- UI ---
st.title("🏀 Sweet 16 Takeover: Live Odds Edition")
st.caption(f"Scores update every 60s | Odds update every 15m")

try:
    scores_json = get_espn_scores()
    odds_json = get_combined_odds(API_KEY)
    owners, matches, logs = process_pool(scores_json, odds_json)

    st.header("🕒 Matchups & Live Probabilities", 
              help="Spread is for the Takeover rule. Win Prob is the live chance to win outright.")
    st.dataframe(pd.DataFrame(matches), hide_index=True, use_container_width=True)

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.header("✅ Owners Still Alive")
        alive_list = []
        for team, owner in owners.items():
            # Check if team is still in an active or upcoming event
            is_alive = any(team in e['name'] for e in scores_json.get('events', []) if e['status']['type']['state'] in ['pre', 'in'])
            if is_alive:
                alive_list.append({"Owner": owner, "Holding Team": team})
        
        if alive_list:
            df_alive = pd.DataFrame(alive_list)
            df_alive.index = range(1, len(df_alive) + 1)
            st.table(df_alive)
        else:
            st.info("Tournament final stages pending...")

    with col2:
        st.header("📜 Takeover Logs")
        if logs:
            for log in logs: st.info(log)
        else:
            st.write("No takeovers recorded yet.")

except Exception as e:
    st.error(f"App Error: {e}")
