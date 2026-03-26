import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# --- SECRETS & API CONFIG ---
try:
    ODDS_API_KEY = st.secrets["API_KEY"]
except KeyError:
    st.error("Missing API_KEY in Secrets!")
    st.stop()

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"

st.set_page_config(page_title="Sweet 16 Takeover", page_icon="🏀", layout="wide")

# --- INITIAL HAT PULL ---
# Update these names to your actual 16 players
INITIAL_MAP = {
    "Arizona": "User 1", "Arkansas": "User 2", "Purdue": "User 3", "Texas": "User 4",
    "Nebraska": "User 5", "Iowa": "User 6", "Houston": "User 7", "Illinois": "User 8",
    "Duke": "User 9", "St. John's": "User 10", "UConn": "User 11", "Michigan State": "User 12",
    "Michigan": "User 13", "Alabama": "User 14", "Iowa State": "User 15", "Tennessee": "User 16"
}

# --- DATA FETCHING ---
@st.cache_data(ttl=60)
def get_live_data():
    scores = requests.get(ESPN_SCOREBOARD).json()
    odds_url = f"https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds/?apiKey={ODDS_API_KEY}&regions=us&markets=spreads"
    odds = requests.get(odds_url).json()
    return scores, odds

# --- LOGIC ENGINE ---
def process_tournament(espn_data, odds_data):
    current_owners = INITIAL_MAP.copy()
    takeover_logs = []
    alive_teams = []
    upcoming_games = []

    events = espn_data.get('events', [])
    for event in events:
        try:
            comps = event.get('competitions', [])
            if not comps: continue
            teams = comps[0].get('competitors', [])
            if len(teams) < 2: continue

            home = next((t for t in teams if t.get('homeAway') == 'home'), teams[0])
            away = next((t for t in teams if t.get('homeAway') == 'away'), teams[1])
            
            h_name = home['team'].get('displayName')
            a_name = away['team'].get('displayName')
            status = event['status']['type']['state'] # 'pre', 'in', 'post'

            # Find Spread
            spread = 0
            for game_odds in odds_data:
                if h_name in game_odds.get('home_team', "") or game_odds.get('home_team', "") in h_name:
                    if game_odds.get('bookmakers'):
                        spread = game_odds['bookmakers'][0]['markets'][0]['outcomes'][0]['point']
                    break

            # 1. Track Upcoming/Live Games
            if status in ['pre', 'in']:
                alive_teams.extend([h_name, a_name])
                upcoming_games.append({
                    "Matchup": f"{a_name} @ {h_name}",
                    "Away Owner": current_owners.get(a_name, "N/A"),
                    "Home Owner": current_owners.get(h_name, "N/A"),
                    "Spread": f"{h_name} {spread}",
                    "Status": event['status']['type']['shortDetail']
                })

            # 2. Process Final Results (Takeovers)
            if status == 'post':
                h_score = int(home.get('score', 0))
                a_score = int(away.get('score', 0))
                winner_team = h_name if h_score > a_score else a_name
                
                h_owner = current_owners.get(h_name)
                a_owner = current_owners.get(a_name)

                # The Takeover Rule
                if (h_score + spread) > a_score:
                    new_owner = h_owner
                else:
                    new_owner = a_owner

                if current_owners.get(winner_team) != new_owner:
                    takeover_logs.append(f"🔄 {new_owner} took over {winner_team} (Final: {a_score}-{h_score}, Spread: {spread})")
                
                current_owners[winner_team] = new_owner
                alive_teams.append(winner_team)

        except Exception:
            continue

    return current_owners, alive_teams, upcoming_games, takeover_logs

# --- UI DISPLAY ---
st.title("🏀 Sweet 16 Takeover Pool")
st.caption(f"Last ESPN Sync: {datetime.now().strftime('%I:%M:%S %p')} ET")

try:
    s_json, o_json = get_live_data()
    owners, alive, upcoming, logs = process_tournament(s_json, o_json)

    # SECTION 1: UPCOMING GAMES
    st.header("🕒 Upcoming & Live Matchups")
    if upcoming:
        st.table(pd.DataFrame(upcoming))
    else:
        st.write("No active or upcoming games found.")

    st.divider()

    # SECTION 2: OWNERSHIP STATUS
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.header("✅ Owners Still Alive")
        alive_data = [{"Owner": owners[t], "Holding Team": t} for t in alive if t in owners]
        if alive_data:
            st.table(pd.DataFrame(alive_data))
        else:
            st.write("Tournament results pending...")

    with col_b:
        st.header("❌ Eliminated Owners")
        all_initial_owners = set(INITIAL_MAP.values())
        current_alive_owners = set([owners[t] for t in alive if t in owners])
        eliminated_owners = all_initial_owners - current_alive_owners
        if eliminated_owners:
            st.write(", ".join(list(eliminated_owners)))
        else:
            st.write("Everyone is still in!")

    # SECTION 3: LOGS
    st.divider()
    st.header("📜 Takeover History")
    for log in logs:
        st.info(log)

except Exception as e:
    st.error(f"App Error: {e}")
