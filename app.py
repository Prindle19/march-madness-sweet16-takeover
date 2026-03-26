import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# --- CONFIG & SECRETS ---
# Ensure you have API_KEY = "your_key" in Streamlit Cloud Secrets
try:
    ODDS_API_KEY = st.secrets["API_KEY"]
except KeyError:
    st.error("Missing API_KEY in Secrets! Please add it to your Streamlit App Settings.")
    st.stop()

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"

st.set_page_config(page_title="Sweet 16 Takeover", page_icon="🏀", layout="wide")

# --- INITIAL HAT PULL ---
# Manual starting assignments for the Sweet 16
INITIAL_MAP = {
    "Arizona": "User 1", "Arkansas": "User 2", "Purdue": "User 3", "Texas": "User 4",
    "Nebraska": "User 5", "Iowa": "User 6", "Houston": "User 7", "Illinois": "User 8",
    "Duke": "User 9", "St. John's": "User 10", "UConn": "User 11", "Michigan State": "User 12",
    "Michigan": "User 13", "Alabama": "User 14", "Iowa State": "User 15", "Tennessee": "User 16"
}

# --- DATA FETCHING ---
@st.cache_data(ttl=60) # Refresh scores every 60 seconds
def get_live_data():
    # Scores from ESPN (Free)
    score_res = requests.get(ESPN_SCOREBOARD).json()
    # Spreads from Odds API (Uses Credits)
    odds_url = f"https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds/?apiKey={ODDS_API_KEY}&regions=us&markets=spreads"
    odds_res = requests.get(odds_url).json()
    return score_res, odds_res

# --- PROCESSING ENGINE ---
def run_takeover_logic(espn_data, odds_data):
    current_owners = INITIAL_MAP.copy()
    history_logs = []
    
    events = espn_data.get('events', [])
    for event in events:
        try:
            # SAFETY: Ensure competitors exist to avoid "Index Out of Range"
            comps = event.get('competitions', [])
            if not comps or len(comps[0].get('competitors', [])) < 2:
                continue
                
            teams = comps[0]['competitors']
            home = next((t for t in teams if t.get('homeAway') == 'home'), teams[0])
            away = next((t for t in teams if t.get('homeAway') == 'away'), teams[1])
            
            h_name = home['team'].get('displayName', "Unknown")
            a_name = away['team'].get('displayName', "Unknown")
            status = event['status']['type']['state'] # 'in' = live, 'post' = final
            
            # Find the spread for this specific game
            spread = 0
            for game_odds in odds_data:
                # Flexible name match to link ESPN names to Odds API names
                if h_name in game_odds.get('home_team', "") or game_odds.get('home_team', "") in h_name:
                    if game_odds.get('bookmakers'):
                        # Use the first bookmaker's spread
                        spread = game_odds['bookmakers'][0]['markets'][0]['outcomes'][0]['point']
                    break

            # Only finalize ownership if the game is OVER
            if status == 'post':
                h_score = int(home.get('score', 0))
                a_score = int(away.get('score', 0))
                actual_winner = h_name if h_score > a_score else a_name
                
                h_owner = current_owners.get(h_name, "N/A")
                a_owner = current_owners.get(a_name, "N/A")
                
                # RULE: (Home Score + Spread) vs Away Score
                if (h_score + spread) > a_score:
                    new_owner = h_owner
                else:
                    new_owner = a_owner
                
                # Record the takeover and update the map
                if current_owners.get(actual_winner) != new_owner:
                    history_logs.append(f"🔄 **{new_owner}** took over **{actual_winner}** (Spread was {spread})")
                current_owners[actual_winner] = new_owner
                
        except (KeyError, IndexError, ValueError):
            # Skip malformed games to prevent app crash
            continue
            
    return current_owners, history_logs

# --- UI LAYOUT ---
st.title("🏀 Sweet 16 Takeover Pool")
st.caption(f"Last sync: {datetime.now().strftime('%I:%M:%S %p')} ET")

try:
    scores_json, odds_json = get_live_data()
    final_ownership, takeover_logs = run_takeover_logic(scores_json, odds_json)

    col1, col2 = st.columns([2, 1])

    with col1:
        st.header("Current Ownership")
        # Identify teams still active on the scoreboard
        active_teams = []
        for e in scores_json.get('events', []):
            for t in e['competitions'][0]['competitors']:
                active_teams.append(t['team']['displayName'])
        
        # Display only teams that are still "alive"
        live_list = [{"Team": t, "Owner": o} for t, o in final_ownership.items() if t in active_teams]
        if live_list:
            st.table(pd.DataFrame(live_list))
        else:
            st.info("No active games found on the ESPN scoreboard.")

    with col2:
        st.header("Activity Log")
        if takeover_logs:
            for log in takeover_logs:
                st.write(log)
        else:
            st.write("No takeovers recorded yet.")
            
        st.divider()
        st.subheader("Payout Tracker")
        st.write("💰 **1st:** $900")
        st.write("💰 **2nd:** $400")
        st.write("🎟️ **Final 4 Losers:** $100 back")

except Exception as e:
    st.error(f"Critical Error: {e}")
    st.info("Ensure your API_KEY is correctly set in Streamlit Secrets.")
