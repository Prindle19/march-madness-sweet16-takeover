import streamlit as st
import requests
import pandas as pd

# --- SECRETS & API CONFIG ---
ODDS_API_KEY = st.secrets.get("API_KEY", "5a5871e7cd461a9cbfca1cbb28efd7ee")
HISTORICAL_ODDS_URL = "https://api.the-odds-api.com/v4/historical/sports/basketball_ncaab/odds/"
LIVE_ODDS_URL = "https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds/"

st.set_page_config(page_title="Sweet 16 Takeover", page_icon="🏀", layout="wide")

# --- INITIAL HAT PULL (The Source of Truth) ---
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

@st.cache_data(ttl=300)
def get_tournament_data():
    # Fetching all games from the start of the Sweet 16 (March 26) through today
    # This ensures Thursday's games are never "forgotten"
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?groups=50&limit=100&dates=20260326-20260330"
    return requests.get(url).json().get('events', [])

@st.cache_data(ttl=3600)
def get_locked_odds(timestamp_str):
    # Retrieve the DraftKings line at 4:00 PM ET for that specific game day
    params = {'apiKey': ODDS_API_KEY, 'regions': 'us', 'markets': 'spreads,h2h', 'bookmakers': 'draftkings', 'date': timestamp_str}
    return requests.get(HISTORICAL_ODDS_URL, params=params).json().get('data', [])

def get_probs(h_score, a_score, status, ml):
    if "Final" in status:
        return (100, 0) if h_score > a_score else (0, 100)
    base = (100 / (ml + 100)) if ml > 0 else (abs(ml) / (abs(ml) + 100))
    diff = (h_score - a_score) * 0.04 if h_score + a_score > 0 else 0
    h_p = max(0.01, min(0.99, base + diff)) * 100
    return (round(h_p, 1), round(100 - h_p, 1))

def process_pool(events):
    # Start with the original hat pull
    pool_state = INITIAL_MAP.copy()
    owner_stats = {v: {"Status": "Alive", "Msg": "", "OrigTeam": k} for k, v in INITIAL_MAP.items()}
    match_list, logs = [], []
    
    # Process games chronologically
    sorted_events = sorted(events, key=lambda x: x['date'])
    
    for event in sorted_events:
        try:
            competitors = event['competitions'][0]['competitors']
            home = next(t for t in competitors if t['homeAway'] == 'home')
            away = next(t for t in competitors if t['homeAway'] == 'away')
            h_name, a_name = home['team']['displayName'], away['team']['displayName']
            
            h_key = next((k for k in INITIAL_MAP.keys() if k.lower() in h_name.lower()), h_name)
            a_key = next((k for k in INITIAL_MAP.keys() if k.lower() in a_name.lower()), a_name)
            
            if h_key not in INITIAL_MAP and a_key not in INITIAL_MAP: continue

            # Get the locked line for the day of the game
            dt = pd.to_datetime(event['date'])
            lock_ts = dt.replace(hour=16, minute=0, second=0).strftime("%Y-%m-%dT%H:%M:%SZ")
            odds_data = get_locked_odds(lock_ts)
            
            spread, ml = 0, 0
            n_h, n_a = normalize(h_key), normalize(a_key)
            for game in odds_data:
                if (n_h in normalize(game['home_team']) or n_h in normalize(game['away_team'])) and \
                   (n_a in normalize(game['home_team']) or n_a in normalize(game['away_team'])):
                    m = game['bookmakers'][0]['markets']
                    spr_m = next(i for i in m if i['key'] == 'spreads')
                    for out in spr_m['outcomes']:
                        if n_h in normalize(out['name']): spread = float(out['point'])
                    h2h_m = next(i for i in m if i['key'] == 'h2h')
                    for out in h2h_m['outcomes']:
                        if n_h in normalize(out['name']): ml = float(out['price'])
                    break

            status = event['status']['type']['state']
            short_detail = event['status']['type']['shortDetail']
            h_score, a_score = int(home.get('score', 0)), int(away.get('score', 0))
            is_final = status == 'post'

            # Logic check: Who is currently winning the takeover?
            h_diff = (h_score + spread) - a_score
            tense = "Taking Over" if not is_final else "Took Over"
            shield = "Surviving" if not is_final else "Survived"
            dom = "Won" if is_final else "Dominating"

            # Get the current owner of each team for live display
            curr_h_owner = pool_state.get(h_key, "N/A")
            curr_a_owner = pool_state.get(a_key, "N/A")

            if h_score + a_score > 0:
                if h_diff > 0: # Home is covering
                    elim_status = f"✅ {h_key} ({curr_h_owner}) {dom}" if h_score > a_score else f"🛡️ {h_key} ({curr_h_owner}) {shield}"
                else: # Away is covering
                    elim_status = f"🔄 {a_key} ({curr_a_owner}) {tense}" if h_score > a_score else f"✅ {a_key} ({curr_a_owner}) {dom}"
            else:
                elim_status = "TBD"

            if is_final:
                su_winner, su_loser = (h_key, a_key) if h_score > a_score else (a_key, h_key)
                home_covered = h_diff > 0
                orig_h_owner, orig_a_owner = pool_state[h_key], pool_state[a_key]

                if home_covered:
                    pool_state[su_winner] = orig_h_owner
                    owner_stats[orig_a_owner]["Status"] = "Eliminated"
                    owner_stats[orig_a_owner]["Msg"] = "Won Game, Lost Team" if a_score > h_score else "Lost Game & Spread"
                else:
                    pool_state[su_winner] = orig_a_owner
                    owner_stats[orig_h_owner]["Status"] = "Eliminated"
                    owner_stats[orig_h_owner]["Msg"] = "Won Game, Lost Spread" if h_score > a_score else "Lost Straight Up"
                    logs.append(f"🔄 **{orig_a_owner}** {tense} **{su_winner}** from **{orig_h_owner}**")
                
                # The loser of the game is physically out of the bracket
                if su_loser in pool_state: del pool_state[su_loser]

            h_p, a_p = get_probs(h_score, a_score, short_detail, ml)
            match_list.append({
                "Matchup": f"{a_name} @ {h_name}", "Status": short_detail,
                "Score": f"{a_score} - {h_score}", "Line": f"{h_name} {spread}",
                "Win Prob": f"{h_name} {h_p}% / {a_name} {a_p}%", "Elimination Status": elim_status
            })
        except: continue
    return pool_state, owner_stats, match_list, logs

# --- UI ---
st.title("🏀 Sweet 16 Takeover Pool")
all_events = get_tournament_data()
current_holders, stats, matches, logs = process_pool(all_events)

st.header("🕒 Matchups & Live Coverage")
st.dataframe(pd.DataFrame(matches), hide_index=True, use_container_width=True)

col1, col2 = st.columns([1.5, 1])
with col1:
    st.header("✅ Owners Still Alive")
    alive_rows = [{"Region": TEAM_INFO[t]["Region"], "Seed": TEAM_INFO[t]["Seed"], "Owner": o, "Team": t} 
                  for t, o in current_holders.items()]
    st.dataframe(pd.DataFrame(alive_rows).sort_values(["Region", "Seed"]), hide_index=True, use_container_width=True)

with col2:
    st.header("💀 Eliminated Owners")
    # Owners are truly dead if they are in owner_stats as Eliminated AND don't appear in current_holders
    alive_names = [o for o in current_holders.values()]
    dead_rows = [{"Owner": name, "Original Team": data["OrigTeam"], "Status": data["Msg"]} 
                 for name, data in stats.items() if name not in alive_names and data["Status"] == "Eliminated"]
    st.dataframe(pd.DataFrame(dead_rows), hide_index=True, use_container_width=True)
    
    st.header("📜 Takeover History")
    for log in logs: st.info(log)

st.divider()
st.subheader("💀 Elimination Key")
st.write("- **Won Game, Lost Spread:** Team won, but failed to cover. Team goes to underdog owner.\n- **Won Game, Lost Team:** Underdog won the game, but didn't beat spread.\n- **Lost Straight Up:** Favorite lost game and failed to cover.\n- **Lost Game & Spread:** Underdog lost game and failed to cover.")
