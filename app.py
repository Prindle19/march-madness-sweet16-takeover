import streamlit as st
import requests
import pandas as pd

# --- SECRETS & CONFIG ---
# Spread API still needs a key, but Scores come free from ESPN
ODDS_API_KEY = st.secrets["API_KEY"] 
ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"

st.set_page_config(page_title="Sweet 16 Takeover", page_icon="🏀", layout="wide")

# --- INITIAL HAT PULL (Update after your draw!) ---
INITIAL_MAP = {
    "Arizona": "User 1", "Arkansas": "User 2", "Purdue": "User 3", "Texas": "User 4",
    "Nebraska": "User 5", "Iowa": "User 6", "Houston": "User 7", "Illinois": "User 8",
    "Duke": "User 9", "St. John's": "User 10", "UConn": "User 11", "Michigan State": "User 12",
    "Michigan": "User 13", "Alabama": "User 14", "Iowa State": "User 15", "Tennessee": "User 16"
}

@st.cache_data(ttl=300) # Refresh ESPN data every 5 mins
def get_espn_scores():
    # Fetch scores from ESPN (No key needed)
    response = requests.get(ESPN_SCOREBOARD)
    return response.json()

@st.cache_data(ttl=3600) # Spreads change less often, cache for 1 hour
def get_spreads():
    url = f"https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds/?apiKey={ODDS_API_KEY}&regions=us&markets=spreads"
    return requests.get(url).json()

def calculate_state(espn_data, odds_data, initial_map):
    current_owners = initial_map.copy()
    history = []
    
    events = espn_data.get('events', [])
    for event in events:
        status = event['status']['type']['state']
        home = event['competitions'][0]['competitors'][0]
        away = event['competitions'][1]['competitors'][1]
        
        home_name = home['team']['displayName']
        away_name = away['team']['displayName']
        
        if status == "post": # Only process completed games
            h_score = int(home['score'])
            a_score = int(away['score'])
            
            # Find the spread for this game
            spread = 0
            for odd in odds_data:
                # Basic name matching (might need refinement for nicknames)
                if home_name in odd['home_team'] or odd['home_team'] in home_name:
                    spread = odd['bookmakers'][0]['markets'][0]['outcomes'][0]['point']
                    break
            
            home_owner = current_owners.get(home_name, "Unknown")
            away_owner = current_owners.get(away_name, "Unknown")
            winner_team = home_name if h_score > a_score else away_name
            
            # THE TAKEOVER RULE
            if (h_score + spread) > a_score:
                new_owner = home_owner
            else:
                new_owner = away_owner
            
            current_owners[winner_team] = new_owner
            history.append(f"**{winner_team}** won. Owner is now **{new_owner}** (Spread: {spread})")
            
    return current_owners, history

# --- UI ---
st.title("🏀 Sweet 16 Takeover: ESPN Live")

try:
    espn_data = get_espn_scores()
    odds_data = get_spreads()
    final_owners, logs = calculate_state(espn_data, odds_data, INITIAL_MAP)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("Current Ownership")
        # List all teams currently in the Sweet 16 and their current owner
        active_owners = [{"Team": t, "Owner": o} for t, o in final_owners.items()]
        st.table(pd.DataFrame(active_owners))
        
    with col2:
        st.header("Takeover Logs")
        for log in logs:
            st.write(log)
            
except Exception as e:
    st.error(f"Error pulling data: {e}")
