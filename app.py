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
    # Fetching group 50 (Division I) scores
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?groups=50&limit=100"
    return requests.get(url).json()

@st.cache_data(ttl=900)
def get_odds(target_utc=None):
    if target_utc:
        params = {'apiKey': ODDS_API_KEY, 'regions': 'us', 'markets': 'spreads,h2h', 'bookmakers': 'draftkings', 'date': target_utc}
        return requests.get(HISTORICAL_ODDS_URL, params=params).json().get('data', [])
    params = {'apiKey': ODDS_API_KEY, 'regions': 'us', 'markets': 'spreads,h2h', 'bookmakers': 'draftkings'}
    return requests.get(LIVE_ODDS_URL, params=params).json()

def get_probs(h_score, a_score, status, ml):
    if "Final" in status:
        return (100, 0) if h_score > a_score else (0, 100)
    base = (100 / (ml + 100)) if ml > 0 else (abs(ml) / (abs(ml) + 100))
    diff = (h_score - a_score) * 0.04 if h_score + a_score > 0 else 0
    h_p = max(0.01, min(0.99, base + diff)) * 100
    return (round(h_p, 1), round(100 - h_p, 1))

def process_pool(espn_data):
    pool_state = INITIAL_MAP.copy()
    owner_tracking = {v: {"Status": "Alive", "Msg": "", "OriginalTeam": k} for k, v in INITIAL_MAP.items()}
    takeover_logs, match_list = [], []
    live_odds = get_odds()
    
    events = espn_data.get('events', [])
    for event in events:
        try:
            competitors = event['competitions'][0]['competitors']
            home = next(t for t in competitors if t['homeAway'] == 'home')
            away = next(t for t in competitors if t['homeAway'] == 'away')
            h_name, a_name = home['team']['displayName'], away['team']['displayName']
            
            # Map ESPN names to our Initial Map keys
            h_key = next((k for k in INITIAL_MAP.keys() if k.lower() in h_name.lower()), h_name)
            a_key = next((k for k in INITIAL_MAP.keys() if k.lower() in a_name.lower()), a_name)
            
            if h_key not in INITIAL_MAP and a_key not in INITIAL_MAP: continue

            # Get Spread (Locking at 4PM ET of game day)
            game_time = pd.to_datetime(event['date'])
            lock_time = game_time.replace(hour=16, minute=0, second=0).strftime("%Y-%m-%dT%H:%M:%SZ")
            odds_data = get_odds(lock_time) if game_time.tz_localize(None) < pd.Timestamp.now() else live_odds
            
            spread, ml = 0, 0
            n_h, n_a = normalize(h_key), normalize(a_key)
            for game in odds_data:
                if (n_h in normalize(game['home_team']) or n_h in normalize(game['away_team'])) and \
                   (n_a in normalize(game['home_team']) or n_a in normalize(game['away_team'])):
                    m = game['bookmakers'][0]['markets']
                    for out in next(i for i in m if i['key'] == 'spreads')['outcomes']:
                        if n_h in normalize(out['name']): spread = float(out['point'])
                    for out in next(i for i in m if i['key'] == 'h2h')['outcomes']:
                        if n_h in normalize(out['name']): ml = float(out['price'])
                    break

            status = event['status']['type']['state']
            h_score, a_score = int(home.get('score', 0)), int(away.get('score', 0))
            is_final = status == 'post'

            # Elimination & Takeover logic
            h_diff = (h_score + spread) - a_score
            if is_final:
                su_winner, su_loser = (h_key, a_key) if h_score > a_score else (a_key, h_key)
                home_covered = h_diff > 0
                orig_h_owner, orig_a_owner = INITIAL_MAP[h_key], INITIAL_MAP[a_key]

                if home_covered:
                    pool_state[su_winner] = orig_h_owner
                    owner_tracking[orig_a_owner]["Status"] = "Eliminated"
                    owner_tracking[orig_a_owner]["Msg"] = "Won Game, Lost Team" if a_score > h_score else "Lost Game & Spread"
                else:
                    pool_state[su_winner] = orig_a_owner
                    owner_tracking[orig_h_owner]["Status"] = "Eliminated"
                    owner_tracking[orig_h_owner]["Msg"] = "Won Game, Lost Spread" if h_score > a_score else "Lost Straight Up"
                    takeover_logs.append(f"🔄 **{orig_a_owner}** Took Over **{su_winner}** from **{orig_h_owner}**")

            h_p, a_p = get_probs(h_score, a_score, event['status']['type']['shortDetail'], ml)
            match_list.append({
                "Matchup": f"{a_name} @ {h_name}", "Status": event['status']['type']['shortDetail'],
                "Score": f"{a_score} - {h_score}", "Line": f"{h_name} {spread}",
                "Win Prob": f"{h_name} {h_p}% / {a_name} {a_p}%"
            })
        except: continue
    return pool_state, owner_tracking, match_list, takeover_logs

# --- UI ---
st.title("🏀 Sweet 16 Takeover Pool")
scores = get_espn_scores()
current_holders, stats, matches, logs = process_pool(scores)

st.header("🕒 Live Matchups & Coverage")
st.dataframe(pd.DataFrame(matches), hide_index=True, use_container_width=True)

col1, col2 = st.columns([1.5, 1])
with col1:
    st.header("✅ Owners Still Alive")
    alive = [{"Region": TEAM_INFO[t]["Region"], "Seed": TEAM_INFO[t]["Seed"], "Owner": o, "Team": t} 
             for t, o in current_holders.items() if stats[INITIAL_MAP[t]]["Status"] == "Alive" or t in ["Purdue", "Iowa"]]
    st.dataframe(pd.DataFrame(alive).sort_values(["Region", "Seed"]), hide_index=True, use_container_width=True)

with col2:
    st.header("💀 Eliminated Owners")
    dead = [{"Owner": n, "Original Team": d["OriginalTeam"], "Status": d["Msg"]} 
            for n, d in stats.items() if d["Status"] == "Eliminated"]
    st.dataframe(pd.DataFrame(dead), hide_index=True, use_container_width=True)
    
    st.header("📜 Takeover History")
    for log in logs: st.info(log)

st.divider()
st.subheader("💀 Elimination Key")
st.write("- **Won Game, Lost Spread:** Team won, but failed to cover. Team goes to underdog owner.\n- **Won Game, Lost Team:** Underdog won the game, but didn't beat the spread. Favorite keeps the spot.\n- **Lost Straight Up:** Favorite lost the game and failed to cover.\n- **Lost Game & Spread:** Underdog lost the game and failed to cover.")
