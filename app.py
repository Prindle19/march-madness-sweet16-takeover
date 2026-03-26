import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# --- SECRETS & API CONFIG ---
ODDS_API_KEY = st.secrets.get("API_KEY", "MISSING_KEY")
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
def get_live_data():
    scores = requests.get(ESPN_API).json()
    odds = []
    if ODDS_API_KEY != "MISSING_KEY":
        params = {'apiKey': ODDS_API_KEY, 'regions': 'us', 'markets': 'spreads,h2h', 'oddsFormat': 'american'}
        odds = requests.get(ODDS_URL, params=params).json()
    return scores, odds

def calculate_win_prob(odds):
    if odds > 0: return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)

def extract_seed(team_node):
    rank_data = team_node.get('curatedRank', team_node.get('rank', '—'))
    if isinstance(rank_data, dict):
        return rank_data.get('current', '—')
    return rank_data

def process_pool(espn_data, odds_data):
    current_owners = INITIAL_MAP.copy()
    takeover_logs, match_list, team_seeds = [], [], {}
    
    events = espn_data.get('events', [])
    for event in events:
        try:
            competitions = event.get('competitions', [{}])[0]
            teams = competitions.get('competitors', [])
            if len(teams) < 2: continue
            
            home = next(t for t in teams if t['homeAway'] == 'home')
            away = next(t for t in teams if t['homeAway'] == 'away')
            
            h_name, a_name = home['team']['displayName'], away['team']['displayName']
            
            # Get the Short Keys to ensure the seeds map perfectly to the Owners Table
            h_key = next((k for k in INITIAL_MAP.keys() if k.lower() in h_name.lower()), h_name)
            a_key = next((k for k in INITIAL_MAP.keys() if k.lower() in a_name.lower()), a_name)
            
            h_seed, a_seed = extract_seed(home), extract_seed(away)
            
            # Map seeds to the SHORT names
            team_seeds[h_key] = h_seed
            team_seeds[a_key] = a_seed
            
            h_score, a_score = int(home.get('score', 0)), int(away.get('score', 0))
            status = event['status']['type']['state']
            
            spread, h_win_prob = 0, 0.5
            if odds_data and isinstance(odds_data, list):
                for game in odds_data:
                    if h_name in game.get('home_team', "") or a_name in game.get('home_team', ""):
                        bookmaker = game.get('bookmakers', [{}])[0]
                        markets = bookmaker.get('markets', [])
                        m_spread = next((m for m in markets if m['key'] == 'spreads'), None)
                        if m_spread: spread = m_spread['outcomes'][0]['point']
                        m_ml = next((m for m in markets if m['key'] == 'h2h'), None)
                        if m_ml: h_win_prob = calculate_win_prob(m_ml['outcomes'][0]['price'])
                        break

            h_owner, a_owner = current_owners.get(h_key, "N/A"), current_owners.get(a_key, "N/A")
            
            # Live Cover Logic
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
                "Spread": f"{h_name} {spread}",
                "Win Prob": f"{h_name} {h_win_prob:.1%}",
                "Live Cover": cover_status
            })

            if status == 'post':
                winner = h_name if h_score > a_score else a_name
                new_owner = h_owner if (h_score + spread) > a_score else a_owner
                winner_key = next((k for k in INITIAL_MAP.keys() if k.lower() in winner.lower()), winner)
                if current_owners[winner_key] != new_owner:
                    takeover_logs.append(f"🔄 **{new_owner}** took over **{winner}**")
                current_owners[winner_key] = new_owner
        except: continue
    return current_owners, match_list, takeover_logs, team_seeds

# --- UI ---
st.title("🏀 Sweet 16 Takeover Pool")

try:
    scores, odds = get_live_data()
    owners, matches, logs, seeds = process_pool(scores, odds)

    st.header("🕒 Matchups & Live Coverage", help="Seeds represent the 1-16 ranking within each of the 4 tournament regions.")
    st.dataframe(pd.DataFrame(matches), hide_index=True, use_container_width=True)

    st.divider()
    col1, col2 = st.columns([1.5, 1])
    
    with col1:
        st.header("✅ Owners Still Alive")
        alive_data = []
        for team, owner in owners.items():
            alive_data.append({
                "Region Seed": seeds.get(team, "—"),
                "Owner": owner, 
                "Holding Team": team
            })
            
        df_alive = pd.DataFrame(alive_data)
        # Convert seeds to numbers for accurate sorting
        df_alive['SeedSort'] = pd.to_numeric(df_alive['Region Seed'], errors='coerce').fillna(99)
        df_alive = df_alive.sort_values("SeedSort").drop(columns=['SeedSort'])
        
        st.dataframe(df_alive, hide_index=True, use_container_width=True)

    with col2:
        st.header("💰 Pool & Payouts")
        st.metric("Total Pot", "$1,600")
        
        # Splitting these into separate lines fixes the LaTeX/Math rendering bug
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
