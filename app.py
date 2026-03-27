import streamlit as st
import requests
import pandas as pd
import numpy as np

# --- SECRETS & API CONFIG ---
ODDS_API_KEY = st.secrets.get("API_KEY", "MISSING_KEY")
LIVE_ODDS_URL = "https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds/"
HISTORICAL_ODDS_URL = "https://api.the-odds-api.com/v4/historical/sports/basketball_ncaab/odds/"

st.set_page_config(page_title="Sweet 16 Takeover", page_icon="🏀", layout="wide")

# --- INITIAL HAT PULL ---
INITIAL_MAP = {
    "Michigan": "Greg Doc", "Houston": "Ryan Doc", "UConn": "Joe Doc", "Michigan State": "DOB",
    "Texas": "Schroller", "Tennessee": "Jimmy A", "Purdue": "Jim Henry", "Iowa": "EJ",
    "Iowa State": "Sean W", "Arizona": "Wenzel", "Arkansas": "Burgess", "Illinois": "Seitz",
    "St. John's": "Nick", "Nebraska": "Ken", "Alabama": "Burgess dude", "Duke": "Tom"
}

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

def normalize(name):
    return name.lower().replace("state", "st").replace(".", "").strip()

@st.cache_data(ttl=60)
def get_espn_scores():
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?groups=50&limit=100"
    return requests.get(url).json()

@st.cache_data(ttl=900)
def get_live_odds():
    params = {'apiKey': ODDS_API_KEY, 'regions': 'us', 'markets': 'spreads,h2h', 'bookmakers': 'draftkings', 'oddsFormat': 'american'}
    return requests.get(LIVE_ODDS_URL, params=params).json()

@st.cache_data(ttl=None) 
def get_historical_odds(target_utc_date):
    params = {'apiKey': ODDS_API_KEY, 'regions': 'us', 'markets': 'spreads,h2h', 'bookmakers': 'draftkings', 'oddsFormat': 'american', 'date': target_utc_date}
    return requests.get(HISTORICAL_ODDS_URL, params=params).json()

def calculate_live_prob(h_score, a_score, status_detail, pregame_ml):
    if "Final" in status_detail:
        return 1.0 if h_score > a_score else 0.0
    
    # Simple logic: start with betting market prob, adjust by current lead
    base_prob = (100 / (pregame_ml + 100)) if pregame_ml > 0 else (abs(pregame_ml) / (abs(pregame_ml) + 100))
    if h_score == 0 and a_score == 0: return base_prob
    
    score_diff = h_score - a_score
    # In-game weight: as the game progresses, current score matters more than opening line
    live_prob = base_prob + (score_diff * 0.05) 
    return max(0.01, min(0.99, live_prob))

def process_pool(espn_data):
    pool_state = {k: {"Owner": v, "Status": "Alive", "Message": ""} for k, v in INITIAL_MAP.items()}
    takeover_logs, match_list = [], []
    live_odds = get_live_odds()
    now_et = pd.Timestamp.utcnow().tz_convert('America/New_York')
    
    events = espn_data.get('events', [])
    for event in events:
        try:
            competitions = event.get('competitions', [{}])[0]
            teams = competitions.get('competitors', [])
            game_time_et = pd.to_datetime(event['date'], utc=True).tz_convert('America/New_York')
            is_locked = now_et.date() > game_time_et.date() or (now_et.date() == game_time_et.date() and now_et.hour >= 16)
            
            home = next(t for t in teams if t['homeAway'] == 'home')
            away = next(t for t in teams if t['homeAway'] == 'away')
            h_name, a_name = home['team']['displayName'], away['team']['displayName']
            h_key = next((k for k in INITIAL_MAP.keys() if k.lower() in h_name.lower()), h_name)
            a_key = next((k for k in INITIAL_MAP.keys() if k.lower() in a_name.lower()), a_name)
            
            spread, ml, last_update = 0, 0, None
            if is_locked:
                lock_str = game_time_et.replace(hour=16, minute=0, second=0).tz_convert('UTC').strftime("%Y-%m-%dT%H:%M:%SZ")
                hist = get_historical_odds(lock_str).get('data', [])
                odds_to_search = hist if hist else live_odds
            else:
                odds_to_search = live_odds

            n_h, n_a = normalize(h_key), normalize(a_key)
            for game in odds_to_search:
                if (n_h in normalize(game['home_team']) or n_h in normalize(game['away_team'])) and \
                   (n_a in normalize(game['home_team']) or n_a in normalize(game['away_team'])):
                    market = game['bookmakers'][0]['markets']
                    m_spreads = next(m for m in market if m['key'] == 'spreads')
                    last_update = m_spreads['last_update']
                    for out in m_spreads['outcomes']:
                        if n_h in normalize(out['name']): spread = float(out['point'])
                    m_h2h = next(m for m in market if m['key'] == 'h2h')
                    for out in m_h2h['outcomes']:
                        if n_h in normalize(out['name']): ml = float(out['price'])
                    break

            status = event['status']['type']['state']
            status_detail = event['status']['type']['shortDetail']
            h_score, a_score = int(home.get('score', 0)), int(away.get('score', 0))
            
            if status == 'post':
                su_winner_key = h_key if h_score > a_score else a_key
                su_loser_key = a_key if h_score > a_score else h_key
                home_covered = (h_score + spread) > a_score
                
                orig_h_owner, orig_a_owner = INITIAL_MAP[h_key], INITIAL_MAP[a_key]
                
                if home_covered:
                    pool_state[su_winner_key]["Owner"] = orig_h_owner
                    pool_state[su_loser_key]["Status"] = "Eliminated"
                    pool_state[su_loser_key]["Message"] = "Knocked Out"
                    if h_score < a_score:
                        takeover_logs.append(f"🛡️ **{orig_h_owner}** survived with **{h_key}** via spread.")
                else:
                    pool_state[su_winner_key]["Owner"] = orig_a_owner
                    pool_state[su_loser_key]["Status"] = "Eliminated"
                    pool_state[su_loser_key]["Message"] = f"Taken over by {orig_a_owner}"
                    takeover_logs.append(f"🔄 **{orig_a_owner}** TOOK OVER the **{su_winner_key}** spot!")

            # Live Prob Calculation
            live_win_prob = calculate_live_prob(h_score, a_score, status_detail, ml)
            
            lock_info = f" (DK @ {pd.to_datetime(last_update).tz_convert('America/New_York').strftime('%I:%M %p')})" if is_locked and last_update else ""
            match_list.append({
                "Matchup": f"({TEAM_INFO[a_key]['Seed']}) {a_name} @ ({TEAM_INFO[h_key]['Seed']}) {h_name}",
                "Status": status_detail,
                "Score": f"{a_score} - {h_score}",
                "Spread": f"{'🔒 ' if is_locked else ''}{h_name} {spread}{lock_info}",
                "Win Prob": f"{h_name} {live_win_prob:.1%}"
            })
        except: continue
    return pool_state, match_list, takeover_logs

# --- UI ---
st.title("🏀 Sweet 16 Takeover Pool")
scores = get_espn_scores()
pool_data, matches, logs = process_pool(scores)

st.header("🕒 Matchups & Live Coverage")
st.dataframe(pd.DataFrame(matches), hide_index=True, use_container_width=True)

col1, col2 = st.columns([1.5, 1])
with col1:
    st.header("✅ Owners Still Alive")
    alive = [{"Region": TEAM_INFO[t]["Region"], "Seed": TEAM_INFO[t]["Seed"], "Owner": d["Owner"], "Tournament Spot": t} 
             for t, d in pool_data.items() if d["Status"] == "Alive"]
    st.dataframe(pd.DataFrame(alive).sort_values(["Region", "Seed"]), hide_index=True, use_container_width=True)

with col2:
    st.header("💀 Eliminated Owners")
    # Only show owners who no longer hold ANY tournament spots
    alive_owners = [d["Owner"] for d in pool_data.values() if d["Status"] == "Alive"]
    dead_owners = []
    for team, data in pool_data.items():
        orig_owner = INITIAL_MAP[team]
        if data["Status"] == "Eliminated" and orig_owner not in alive_owners:
            dead_owners.append({"Owner": orig_owner, "Lost Team": team, "Status": data["Message"]})
    
    if dead_owners:
        st.dataframe(pd.DataFrame(dead_owners), hide_index=True, use_container_width=True)
    
    st.header("📜 Takeover History")
    for log in logs: st.info(log)
