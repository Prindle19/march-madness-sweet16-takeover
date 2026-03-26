import streamlit as st
import requests
import pandas as pd

# --- SECRETS & API CONFIG ---
ODDS_API_KEY = st.secrets.get("API_KEY", "MISSING_KEY")
ODDS_URL = "https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds/"

st.set_page_config(page_title="Sweet 16 Takeover", page_icon="🏀", layout="wide")

# --- INITIAL HAT PULL ---
INITIAL_MAP = {
    "Michigan": "Greg Doc", "Houston": "Ryan Doc", "UConn": "Joe Doc", "Michigan State": "DOB",
    "Texas": "Schroller", "Tennessee": "Jimmy A", "Purdue": "Jim Henry", "Iowa": "EJ",
    "Iowa State": "Sean W", "Arizona": "Wenzel", "Arkansas": "Burgess", "Illinois": "Seitz",
    "St. John's": "Nick", "Nebraska": "Ken", "Alabama": "Burgess dude", "Duke": "Tom"
}

# --- HARDCODED TOURNAMENT DATA ---
# This guarantees seeds and regions never show up as "TBD" or missing.
TEAM_INFO = {
    "Michigan": {"Seed": 1, "Region": "Midwest"},
    "Houston": {"Seed": 2, "Region": "South"},
    "UConn": {"Seed": 2, "Region": "East"},
    "Michigan State": {"Seed": 3, "Region": "East"},
    "Texas": {"Seed": 11, "Region": "West"},
    "Tennessee": {"Seed": 6, "Region": "Midwest"},
    "Purdue": {"Seed": 2, "Region": "West"},
    "Iowa": {"Seed": 9, "Region": "South"},
    "Iowa State": {"Seed": 2, "Region": "Midwest"},
    "Arizona": {"Seed": 1, "Region": "West"},
    "Arkansas": {"Seed": 4, "Region": "West"},
    "Illinois": {"Seed": 3, "Region": "South"},
    "St. John's": {"Seed": 5, "Region": "East"},
    "Nebraska": {"Seed": 4, "Region": "South"},
    "Alabama": {"Seed": 4, "Region": "Midwest"},
    "Duke": {"Seed": 1, "Region": "East"}
}

@st.cache_data(ttl=60)
def get_live_data():
    primary_url = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates=20260326-20260329&limit=100"
    scores = requests.get(primary_url).json()
    
    # Fallback to base live scoreboard if date filter fails
    if not scores.get('events'):
        backup_url = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"
        scores = requests.get(backup_url).json()

    odds = []
    if ODDS_API_KEY != "MISSING_KEY":
        params = {'apiKey': ODDS_API_KEY, 'regions': 'us', 'markets': 'spreads,h2h', 'oddsFormat': 'american'}
        odds = requests.get(ODDS_URL, params=params).json()
        
    return scores, odds

def calculate_win_prob(odds):
    if odds > 0: return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)

def process_pool(espn_data, odds_data):
    current_owners = INITIAL_MAP.copy()
    takeover_logs, match_list = [], []
    
    events = espn_data.get('events', [])
    for event in events:
        try:
            competitions = event.get('competitions', [{}])[0]
            teams = competitions.get('competitors', [])
            if len(teams) < 2: continue
            
            home = next(t for t in teams if t['homeAway'] == 'home')
            away = next(t for t in teams if t['homeAway'] == 'away')
            
            h_name, a_name = home['team']['displayName'], away['team']['displayName']
            
            # Match ESPN names to our hardcoded dictionaries
            h_key = next((k for k in INITIAL_MAP.keys() if k.lower() in h_name.lower()), h_name)
            a_key = next((k for k in INITIAL_MAP.keys() if k.lower() in a_name.lower()), a_name)
            
            # Pull static seed data directly from our hardcoded map
            h_seed = TEAM_INFO.get(h_key, {}).get("Seed", "—")
            a_seed = TEAM_INFO.get(a_key, {}).get("Seed", "—")
            
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
    return current_owners, match_list, takeover_logs

# --- UI ---
st.title("🏀 Sweet 16 Takeover Pool")

try:
    scores, odds = get_live_data()
    owners, matches, logs = process_pool(scores, odds)

    st.header("🕒 Matchups & Live Coverage")
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
        # Groups by Region (East, Midwest, South, West), then sorts 1-16 within the region
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
