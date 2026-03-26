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

ESPN_API = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"
ODDS_URL = "https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds/"

st.set_page_config(page_title="Sweet 16 Takeover", page_icon="🏀", layout="wide")

# --- INITIAL HAT PULL ---
INITIAL_MAP = {
    "Michigan": "Greg Doc", "Houston": "Ryan Doc", "UConn": "Joe Doc", "Michigan State": "DOB",
    "Texas": "Schroller", "Tennessee": "Jimmy A", "Purdue": "Jim Henry", "Iowa": "EJ",
    "Iowa State": "Sean W", "Arizona": "Wenzel", "Arkansas": "Burgess", "Illinois": "Seitz",
    "St. John's": "Nick", "Nebraska": "Ken", "Alabama": "Burgess dude", "Duke": "Tom"
}

@st.cache_data(ttl=60)
def get_espn_scores():
    return requests.get(ESPN_API).json()

@st.cache_data(ttl=900)
def get_combined_odds(_api_key):
    params = {'apiKey': _api_key, 'regions': 'us', 'markets': 'spreads,h2h', 'oddsFormat': 'american'}
    return requests.get(ODDS_URL, params=params).json()

def calculate_win_prob(odds):
    if odds > 0: return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)

def process_pool(espn_data, odds_data):
    current_owners = INITIAL_MAP.copy()
    takeover_logs, upcoming = [], []
    
    events = espn_data.get('events', [])
    for event in events:
        try:
            teams = event['competitions'][0]['competitors']
            home = next(t for t in teams if t['homeAway'] == 'home')
            away = next(t for t in teams if t['homeAway'] == 'away')
            h_name, a_name = home['team']['displayName'], away['team']['displayName']
            status = event['status']['type']['state']
            
            # IMPROVED NAME MATCHING: Check if INITIAL_MAP key is IN the ESPN name
            def get_owner_by_match(full_name):
                for team_key in INITIAL_MAP.keys():
                    if team_key.lower() in full_name.lower():
                        return current_owners[team_key]
                return "N/A"

            h_owner = get_owner_by_match(h_name)
            a_owner = get_owner_by_match(a_name)

            spread, h_win_prob = 0, 0.5
            for game in odds_data:
                if any(k.lower() in game['home_team'].lower() for k in INITIAL_MAP.keys()):
                    m_spread = next((m for m in game['bookmakers'][0]['markets'] if m['key'] == 'spreads'), None)
                    if m_spread: spread = m_spread['outcomes'][0]['point']
                    m_ml = next((m for m in game['bookmakers'][0]['markets'] if m['key'] == 'h2h'), None)
                    if m_ml: h_win_prob = calculate_win_prob(m_ml['outcomes'][0]['price'])
                    break

            if status in ['pre', 'in']:
                upcoming.append({
                    "Matchup": f"{a_name} @ {h_name}",
                    "Away Owner": a_owner,
                    "Home Owner": h_owner,
                    "Spread": f"{h_name} {spread}",
                    "Win Prob": f"{h_name} {h_win_prob:.1%}",
                    "Status": event['status']['type']['shortDetail']
                })

            if status == 'post':
                h_score, a_score = int(home['score']), int(away['score'])
                winner = h_name if h_score > a_score else a_name
                new_owner = h_owner if (h_score + spread) > a_score else a_owner
                
                winner_key = next((k for k in INITIAL_MAP.keys() if k.lower() in winner.lower()), winner)
                if current_owners[winner_key] != new_owner:
                    takeover_logs.append(f"🔄 **{new_owner}** took over **{winner}** (Spread: {spread})")
                current_owners[winner_key] = new_owner
        except: continue
    return current_owners, upcoming, takeover_logs

# --- UI ---
st.title("🏀 Sweet 16 Takeover: Live Odds Edition")

try:
    scores, odds = get_espn_scores(), get_combined_odds(API_KEY)
    owners, matches, logs = process_pool(scores, odds)

    st.header("🕒 Matchups & Live Probabilities")
    st.dataframe(pd.DataFrame(matches), hide_index=True, use_container_width=True)

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.header("✅ Owners Still Alive")
        # Find who is alive: either their team hasn't played, is playing, or won
        alive_list = []
        for team_key, owner_name in owners.items():
            # If team is still in events, or it's the start of the tournament
            alive_list.append({"Owner": owner_name, "Holding Team": team_key})
        
        df_alive = pd.DataFrame(alive_list)
        df_alive.index = range(1, len(df_alive) + 1)
        st.table(df_alive)

    with col2:
        st.header("💰 Pool Money & Payouts")
        st.metric("Total Pot", "$1,600")
        st.write("---")
        st.subheader("1st Place: $900")
        st.subheader("2nd Place: $400")
        st.write("Final Four Losers: $100 back (x2)")
        
        st.divider()
        st.header("📜 Takeover Logs")
        if logs:
            for log in logs: st.info(log)
        else:
            st.write("No takeovers recorded yet.")

except Exception as e:
    st.error(f"App Error: {e}")
