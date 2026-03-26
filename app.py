import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# --- SECRETS & API CONFIG ---
try:
    ODDS_API_KEY = st.secrets["API_KEY"]
except KeyError:
    st.error("Missing API_KEY in Secrets! Please add it to your Streamlit App Settings.")
    st.stop()

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"

st.set_page_config(page_title="Sweet 16 Takeover", page_icon="🏀", layout="wide")

# --- INITIAL HAT PULL (Updated from Image) ---
INITIAL_MAP = {
    "Michigan": "Greg Doc",
    "Houston": "Ryan Doc",
    "UConn": "Joe Doc",
    "Michigan State": "DOB",
    "Texas": "Schroller",
    "Tennessee": "Jimmy A",
    "Purdue": "Jim Henry",
    "Iowa": "EJ",
    "Iowa State": "Sean W",
    "Arizona": "Wenzel",
    "Arkansas": "Burgess",
    "Illinois": "Seitz",
    "St. John's": "Nick",
    "Nebraska": "Ken",
    "Alabama": "Burgess dude",
    "Duke": "Tom"
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
    alive_teams = set()
    upcoming_games = []

    events = espn_data.get('events', [])
    
    # Default to all 16 alive if no games are final
    if not any(e['status']['type']['state'] == 'post' for e in events):
        alive_teams = set(INITIAL_MAP.keys())

    for event in events:
        try:
            comps = event.get('competitions', [])
            if not comps: continue
            teams = comps[0].get('competitors', [])
            if len(teams) < 2: continue

            home = next((t for t in teams if t.get('homeAway') == 'home'), teams[0])
            away = next((t for t in teams if t.get('homeAway') == 'away'), teams[1])
            
            h_name_full = home['team'].get('displayName')
            a_name_full = away['team'].get('displayName')
            h_short = home['team'].get('shortDisplayName', h_name_full)
            a_short = away['team'].get('shortDisplayName', a_name_full)
            
            status = event['status']['type']['state']

            # Find Spread
            spread = 0
            for game_odds in odds_data:
                if h_name_full in game_odds.get('home_team', "") or h_short in game_odds.get('home_team', ""):
                    if game_odds.get('bookmakers'):
                        spread = game_odds['bookmakers'][0]['markets'][0]['outcomes'][0]['point']
                    break

            def find_owner(name_to_match):
                for key in INITIAL_MAP.keys():
                    if key in name_to_match:
                        return current_owners.get(key)
                return "N/A"

            h_owner = find_owner(h_name_full)
            a_owner = find_owner(a_name_full)

            if status in ['pre', 'in']:
                alive_teams.add(h_short)
                alive_teams.add(a_short)
                upcoming_games.append({
                    "Matchup": f"{a_name_full} @ {h_name_full}",
                    "Away Owner": a_owner,
                    "Home Owner": h_owner,
                    "Spread": f"{h_name_full} {spread}",
                    "Status": event['status']['type']['shortDetail']
                })

            if status == 'post':
                h_score = int(home.get('score', 0))
                a_score = int(away.get('score', 0))
                winner_short = h_short if h_score > a_score else a_short
                
                if (h_score + spread) > a_score:
                    new_owner = h_owner
                else:
                    new_owner = a_owner

                winner_key = next((k for k in INITIAL_MAP.keys() if k in winner_short), winner_short)
                
                if current_owners.get(winner_key) != new_owner:
                    takeover_logs.append(f"🔄 **{new_owner}** took over **{winner_short}** (Spread was {spread})")
                
                current_owners[winner_key] = new_owner
                alive_teams.add(winner_short)

        except Exception:
            continue

    return current_owners, alive_teams, upcoming_games, takeover_logs

# --- UI DISPLAY ---
st.title("🏀 Sweet 16 Takeover Pool")
st.caption(f"Last ESPN Sync: {datetime.now().strftime('%I:%M:%S %p')} ET")

try:
    s_json, o_json = get_live_data()
    owners, alive, upcoming, logs = process_tournament(s_json, o_json)

    st.header("🕒 Upcoming & Live Matchups")
    if upcoming:
        st.dataframe(pd.DataFrame(upcoming), hide_index=True, use_container_width=True)
    else:
        st.write("No active games currently on the board.")

    st.divider()

    col_a, col_b = st.columns(2)
    
    with col_a:
        st.header("✅ Owners Still Alive")
        alive_data = []
        for team_key, owner in owners.items():
            if any(team_key in a_team for a_team in alive):
                alive_data.append({"Owner": owner, "Holding Team": team_key})
        
        if alive_data:
            df_alive = pd.DataFrame(alive_data)
            df_alive.index = range(1, len(df_alive) + 1) # Set 1-based index
            st.table(df_alive) # Using table for a clean, non-interactive look
        else:
            st.write("Tournament results pending...")

    with col_b:
        st.header("❌ Eliminated Owners")
        all_players = set(INITIAL_MAP.values())
        current_alive = set([d['Owner'] for d in alive_data])
        eliminated = sorted(list(all_players - current_alive))
        if eliminated:
            st.write(", ".join(eliminated))
        else:
            st.write("Everyone is still in!")

    st.divider()
    st.header("📜 Takeover History")
    if logs:
        for log in logs:
            st.info(log)
    else:
        st.write("No takeovers yet. Waiting for the first game to go Final.")

except Exception as e:
    st.error(f"App Error: {e}")
