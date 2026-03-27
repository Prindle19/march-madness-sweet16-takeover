import streamlit as st
import requests
import pandas as pd

# --- SECRETS & API CONFIG ---
ODDS_API_KEY = st.secrets.get("API_KEY", "5a5871e7cd461a9cbfca1cbb28efd7ee")
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

def get_probs(h_score, a_score, status, ml):
    if "Final" in status:
        return (100, 0) if h_score > a_score else (0, 100)
    base = (100 / (ml + 100)) if ml > 0 else (abs(ml) / (abs(ml) + 100))
    if h_score == 0 and a_score == 0:
        h_p = base * 100
    else:
        diff = (h_score - a_score) * 0.04
        h_p = max(0.01, min(0.99, base + diff)) * 100
    return (round(h_p, 1), round(100 - h_p, 1))

def process_pool(espn_data):
    pool_state = {k: {"Owner": v, "Status": "Alive", "Msg": ""} for k, v in INITIAL_MAP.items()}
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
            odds_to_search = live_odds
            if is_locked:
                lock_str = game_time_et.replace(hour=16, minute=0, second=0).tz_convert('UTC').strftime("%Y-%m-%dT%H:%M:%SZ")
                hist = get_historical_odds(lock_str).get('data', [])
                if hist: odds_to_search = hist

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
            short_detail = event['status']['type']['shortDetail']
            h_score, a_score = int(home.get('score', 0)), int(away.get('score', 0))
            
            if status == 'post':
                su_winner = h_key if h_score > a_score else a_key
                su_loser = a_key if h_score > a_score else h_key
                home_covered = (h_score + spread) > a_score
                orig_h_owner, orig_a_owner = INITIAL_MAP[h_key], INITIAL_MAP[a_key]
                
                if home_covered:
                    pool_state[su_winner]["Owner"] = orig_h_owner
                    pool_state[su_loser]["Status"] = "Eliminated"
                    if h_score < a_score:
                        pool_state[su_loser]["Msg"] = "Eliminated (Won Game, Lost Team)"
                        takeover_logs.append(f"🛡️ **{orig_h_owner}** used the spread to survive with **{h_key}**.")
                    else:
                        pool_state[su_loser]["Msg"] = "Knocked Out (Lost Game & Spread)"
                else:
                    pool_state[su_winner]["Owner"] = orig_a_owner
                    pool_state[su_loser]["Status"] = "Eliminated"
                    pool_state[su_loser]["Msg"] = "Knocked Out (Spread)"
                    takeover_logs.append(f"🔄 **{orig_a_owner}** TOOK OVER the **{su_winner}** from **{orig_h_owner}**!")

            h_p, a_p = get_probs(h_score, a_score, short_detail, ml)
            lock_info = f" (DK @ {pd.to_datetime(last_update).tz_convert('America/New_York').strftime('%I:%M %p')})" if is_locked and last_update else ""
            
            match_list.append({
                "Matchup": f"({TEAM_INFO[a_key]['Seed']}) {a_name} @ ({TEAM_INFO[h_key]['Seed']}) {h_name}",
                "Status": short_detail,
                "Score": f"{a_score} - {h_score}",
                "Favorite": f"⭐ {h_name}" if spread < 0 else f"⭐ {a_name}",
                "Spread": f"{'🔒 ' if is_locked else ''}{h_name} {spread}{lock_info}",
                "Win Prob": f"{h_name} {h_p}% / {a_name} {a_p}%"
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
    alive_rows = [{"Region": TEAM_INFO[t]["Region"], "Seed": TEAM_INFO[t]["Seed"], "Owner": d["Owner"], "Advancing Team": t} 
                  for t, d in pool_data.items() if d["Status"] == "Alive"]
    if alive_rows:
        st.dataframe(pd.DataFrame(alive_rows).sort_values(["Region", "Seed"]), hide_index=True, use_container_width=True)

with col2:
    st.header("💀 Eliminated Owners")
    alive_list = [d["Owner"] for d in pool_data.values() if d["Status"] == "Alive"]
    dead_rows = []
    for team_name, team_data in pool_data.items():
        orig_owner = INITIAL_MAP[team_name]
        if orig_owner not in alive_list:
            if not any(r['Owner'] == orig_owner for r in dead_rows):
                status_msg = team_data["Msg"] if team_data["Status"] == "Eliminated" else "Knocked Out"
                dead_rows.append({"Owner": orig_owner, "Original Team": team_name, "Status": status_msg})

    if dead_rows:
        st.dataframe(pd.DataFrame(dead_rows), hide_index=True, use_container_width=True)
    
    st.header("📜 Takeover History")
    for log in logs: st.info(log)
