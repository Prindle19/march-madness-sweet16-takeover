import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# --- SECRETS & API CONFIG ---
try:
    API_KEY = st.secrets["API_KEY"]
except KeyError:
    st.error("Missing API_KEY in Secrets!")
    st.stop()

ESPN_API = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"
ODDS_URL = "https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds/"

st.set_page_config(page_title="Sweet 16 Takeover", page_icon="🏀", layout="wide")

# --- INITIAL HAT PULL (Updated from Image) ---
INITIAL_MAP = {
    "Michigan": "Greg Doc", "Houston": "Ryan Doc", "UConn": "Joe Doc", "Michigan State": "DOB",
    "Texas": "Schroller", "Tennessee": "Jimmy A", "Purdue": "Jim Henry", "Iowa": "EJ",
    "Iowa State": "Sean W", "Arizona": "Wenzel", "Arkansas": "Burgess", "Illinois": "Seitz",
    "St. John's": "Nick", "Nebraska": "Ken", "Alabama": "Burgess dude", "Duke": "Tom"
}

@st.cache_data(ttl=60)
def get_live_data():
    scores = requests.get(ESPN_API).json()
    params = {'apiKey': API_KEY, 'regions': 'us', 'markets': 'spreads,h2h', 'oddsFormat': 'american'}
    odds = requests.get(ODDS_URL, params=params).json()
    return scores, odds

def process_pool(espn_data, odds_data):
    current_owners = INITIAL_MAP.copy()
    takeover_logs, match_list = [], []
    
    events = espn_data.get('events', [])
    for event in events:
        try:
            teams = event['competitions'][0]['competitors']
            home = next(t for t in teams if t['homeAway'] == 'home')
            away = next(t for t in teams if t['homeAway'] == 'away')
            h_name, a_name = home['team']['displayName'], away['team']['displayName']
            h_score, a_score = int(home.get('score', 0)), int(away.get('score', 0))
            status = event['status']['type']['state']
            
            # Match Odds
            spread, h_win_prob = 0, 0.5
            for game in odds_data:
                if h_name in game['home_team'] or a_name in game['home_team']:
                    m_spread = next((m for m in game['bookmakers'][0]['markets'] if m['key'] == 'spreads'), None)
                    if m_spread: spread = m_spread['outcomes'][0]['point']
                    break

            def get_owner(full_name):
                for k in INITIAL_MAP.keys():
                    if k.lower() in full_name.lower(): return current_owners[k]
                return "N/A"

            h_owner, a_owner = get_owner(h_name), get_owner(a_name)
            
            # --- LIVE COVER LOGIC ---
            cover_status = "—"
            if status == 'in':
                # (Home Score + Spread) vs Away Score
                if (h_score + spread) > a_score:
                    cover_status = f"✅ {h_name} Covering" if h_score < a_score else "Leader Covering"
                else:
                    cover_status = f"✅ {a_name} Covering" if a_score < h_score else "Leader Covering"

            # Identify the Favorite for coloring
            fav_indicator = f"⭐ {h_name}" if spread < 0 else f"⭐ {a_name}"

            match_list.append({
                "Matchup": f"{a_name} @ {h_name}",
                "Status": event['status']['type']['shortDetail'],
                "Score": f"{a_score} - {h_score}",
                "Favorite": fav_indicator,
                "Away Owner": a_owner,
                "Home Owner": h_owner,
                "Takeover Spread": f"{h_name} {spread}",
                "Live Cover Status": cover_status
            })

            if status == 'post':
                winner = h_name if h_score > a_score else a_name
                new_owner = h_owner if (h_score + spread) > a_score else a_owner
                winner_key = next((k for k in INITIAL_MAP.keys() if k.lower() in winner.lower()), winner)
                if current_owners[winner_key] != new_owner:
                    takeover_logs.append(f"🔄 **{new_owner}** took over **{winner}**")
                current_owners[winner_key] = new_owner
        except: continue
    return current_owners, match_list, takeover_logs

# --- UI ---
st.title("🏀 Sweet 16 Takeover Pool")

try:
    scores, odds = get_live_data()
    owners, matches, logs = process_pool(scores, odds)

    st.header("🕒 Matchups & Live Coverage", help="If a team is 'Covering' while losing, their owner is currently on track to steal the winning team!")
    
    # Styling: Highlight the 'Live Cover Status' if an underdog is beating the spread
    df_matches = pd.DataFrame(matches)
    def highlight_cover(val):
        color = '#d4edda' if '✅' in str(val) else ''
        return f'background-color: {color}'
    
    st.dataframe(df_matches.style.applymap(highlight_cover, subset=['Live Cover Status']), 
                 hide_index=True, use_container_width=True)

    st.divider()
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("✅ Owners Still Alive")
        alive_data = [{"Owner": v, "Holding Team": k} for k, v in owners.items()]
        st.table(pd.DataFrame(alive_data).sort_values("Owner"))

    with col2:
        st.header("💰 Pool Money & Payouts")
        st.metric("Total Pot", "$1,600", help="16 players @ $100 each")
        c1, c2 = st.columns(2)
        c1.write("🏆 **1st Place:** $900")
        c1.write("🥈 **2nd Place:** $400")
        c2.write("🎟️ **F4 Losers:** $100 back")
        c2.write("🎟️ **F4 Losers:** $100 back")
        
        st.divider()
        st.header("📜 Takeover History")
        if logs:
            for log in logs: st.info(log)
        else:
            st.write("No takeovers recorded yet.")

except Exception as e:
    st.error(f"App Error: {e}")
