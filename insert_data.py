import pyodbc
import pandas as pd
import os, csv, io, time, re

# ============================================================
# CONFIGURATION — paths match your exact folder structure
# ============================================================
BASE = r"C:\Users\Data\Documents\abdallah\Projects\Python Projects\Visualbod\premuier league"

# Each season has its own subfolder with exact file names as seen in your screenshots
SEASON_MAP = {
    '2020/21': {
        'folder':      os.path.join(BASE, '2020-2021'),
        'chemp':       'league-chemp.csv',
        'players':     'league-players.csv',
        'player_stats':'2020-2021 Premier League Player Stats _ FBref.com.csv',
        'fixtures':    '2020-2021 Premier League Scores & Fixt....csv',
        'shooting':    None,
    },
    '2021/22': {
        'folder':      os.path.join(BASE, '2021-2022'),
        'chemp':       'league-chemp (1).csv',
        'players':     'league-players (1).csv',
        'player_stats': None,
        'fixtures':    '2021-2022 Premier League Scores & Fixt....csv',
        'shooting':    '2021-2022 Premier League Shooting Stat....csv',
    },
    '2022/23': {
        'folder':      os.path.join(BASE, '2022-2023'),
        'chemp':       'league-chemp (2).csv',
        'players':     'league-players (2).csv',
        'player_stats': None,
        'fixtures':    '2022-2023 Premier League Scores & Fixt....csv',
        'shooting':    '2022-2023 Premier League Shooting Stat....csv',
    },
    '2023/24': {
        'folder':      os.path.join(BASE, '2023-2024'),
        'chemp':       'league-chemp (3).csv',
        'players':     'league-players (3).csv',
        'player_stats': None,
        'fixtures':    '2023-2024 Premier League Scores & Fixt....csv',
        'shooting':    '2023-2024 Premier League Shooting Stat....csv',
    },
    '2024/25': {
        'folder':      os.path.join(BASE, '2024-2025'),
        'chemp':       'league-chemp (4).csv',
        'players':     'league-players (4).csv',
        'player_stats':'2024-2025 Premier League Player Stats _ FBref.com.csv',
        'fixtures':    '2024-2025 Premier League Scores & Fixt....csv',
        'shooting':    None,
    },
}

# ============================================================
# AUTO-DETECT actual file names (handles truncated names)
# ============================================================
def find_file(folder, pattern_keywords):
    """Find a file in folder that contains all keywords (case-insensitive)"""
    if not os.path.exists(folder):
        return None
    for fname in os.listdir(folder):
        fl = fname.lower()
        if all(k.lower() in fl for k in pattern_keywords):
            return os.path.join(folder, fname)
    return None

def get_path(season_info, file_type):
    folder = season_info['folder']
    filename = season_info.get(file_type)

    # Try exact name first
    if filename:
        full = os.path.join(folder, filename)
        if os.path.exists(full):
            return full

    # Auto-detect by keywords
    keywords_map = {
        'chemp':        ['league-chemp'],
        'players':      ['league-players'],
        'player_stats': ['player', 'stats', 'fbref'],
        'fixtures':     ['scores', 'fixtures'],
        'shooting':     ['shooting'],
    }
    kw = keywords_map.get(file_type, [])
    if kw:
        found = find_file(folder, kw)
        if found:
            return found
    return None

# ============================================================
# CONNECTION
# ============================================================
def get_conn():
    return pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=(localdb)\\MSSQLLocalDB;"
        "DATABASE=PremierLeagueDB;"
        "Trusted_Connection=yes;"
    )

# ============================================================
# SETUP NEW TABLES
# ============================================================
def setup_db(cursor):
    print("\n🔧 Setting up tables...")
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='TeamSeasonStats')
        CREATE TABLE TeamSeasonStats (
            ID INT IDENTITY(1,1) PRIMARY KEY,
            TeamID INT, SeasonID INT,
            Matches INT DEFAULT 0, Wins INT DEFAULT 0,
            Draws INT DEFAULT 0, Loses INT DEFAULT 0,
            Goals INT DEFAULT 0, GoalsAgainst INT DEFAULT 0,
            Points INT DEFAULT 0,
            xG FLOAT DEFAULT 0, xGA FLOAT DEFAULT 0, xPTS FLOAT DEFAULT 0)
    """)
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='TeamExtendedStats')
        CREATE TABLE TeamExtendedStats (
            ID INT IDENTITY(1,1) PRIMARY KEY,
            TeamID INT, SeasonID INT,
            Possession FLOAT DEFAULT 0,
            Shots INT DEFAULT 0, ShotsOnTarget INT DEFAULT 0,
            ShotAccuracy FLOAT DEFAULT 0, ShotsPer90 FLOAT DEFAULT 0,
            SoTPer90 FLOAT DEFAULT 0, GoalPerShot FLOAT DEFAULT 0,
            Penalties INT DEFAULT 0, PenaltiesAtt INT DEFAULT 0,
            YellowCards INT DEFAULT 0, RedCards INT DEFAULT 0,
            HomeWins INT DEFAULT 0, HomeLosses INT DEFAULT 0,
            HomeDraws INT DEFAULT 0, HomeGoals INT DEFAULT 0,
            AwayWins INT DEFAULT 0, AwayLosses INT DEFAULT 0,
            AwayDraws INT DEFAULT 0, AwayGoals INT DEFAULT 0,
            AvgAttendance INT DEFAULT 0)
    """)
    cursor.execute("""
        IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='PlayerExtendedStats')
        CREATE TABLE PlayerExtendedStats (
            ID INT IDENTITY(1,1) PRIMARY KEY,
            PlayerID INT, SeasonID INT,
            Position NVARCHAR(20), Nation NVARCHAR(50),
            Age INT DEFAULT 0, Starts INT DEFAULT 0,
            YellowCards INT DEFAULT 0, RedCards INT DEFAULT 0,
            Penalties INT DEFAULT 0, PenaltiesAtt INT DEFAULT 0)
    """)
    print("   ✅ All tables ready")

# ============================================================
# CLEAR DATA
# ============================================================
def clear_data(cursor):
    print("\n🗑️  Clearing old data...")
    for tbl in ['PlayerExtendedStats','TeamExtendedStats','TeamSeasonStats','PlayerStats','Players','Teams','Seasons']:
        try: cursor.execute(f"DELETE FROM {tbl}")
        except: pass
    print("   ✅ Done")

# ============================================================
# HELPERS
# ============================================================
def get_or_create_team(cursor, cache, name):
    name = name.strip()
    if not name: return None
    if name in cache: return cache[name]
    cursor.execute("SELECT TeamID FROM Teams WHERE TeamName=?", (name,))
    row = cursor.fetchone()
    if row: cache[name]=row[0]; return row[0]
    cursor.execute("INSERT INTO Teams (TeamName) VALUES (?)", (name,))
    cursor.execute("SELECT @@IDENTITY")
    tid = int(cursor.fetchone()[0])
    cache[name] = tid; return tid

def safe_float(v, d=0.0):
    try: return float(str(v).replace(',','').strip())
    except: return d

def safe_int(v, d=0):
    try: return int(float(str(v).replace(',','').strip()))
    except: return d

def parse_fbref_table(filepath, header_keywords):
    if not filepath or not os.path.exists(filepath): return None, None
    with open(filepath, encoding='utf-8-sig') as f:
        lines = f.readlines()
    for i, line in enumerate(lines):
        if all(k in line for k in header_keywords):
            header = [h.strip() for h in lines[i].strip().split(',')]
            rows = []
            for j in range(i+1, len(lines)):
                l = lines[j].strip()
                if not l or all(k in l for k in header_keywords): continue
                parts = l.replace('"','').split(',')
                if len(parts) >= len(header)-2:
                    rows.append(dict(zip(header, parts)))
            return header, rows
    return None, None

def parse_score(s):
    s = s.replace('–','-').replace('—','-').strip()
    if '-' in s:
        p = s.split('-')
        if len(p)==2:
            try: return int(p[0].strip()), int(p[1].strip())
            except: pass
    return None, None

# ============================================================
# INSERT SEASONS
# ============================================================
def insert_seasons(cursor):
    print("\n📅 Inserting seasons...")
    ids = {}
    for name in SEASON_MAP:
        cursor.execute("INSERT INTO Seasons (SeasonName) VALUES (?)", (name,))
        cursor.execute("SELECT @@IDENTITY")
        sid = int(cursor.fetchone()[0])
        ids[name] = sid
        print(f"   → {name} (ID={sid})")
    return ids

# ============================================================
# INSERT CORE (standings + players)
# ============================================================
def insert_core(cursor, season_ids, team_cache):
    print("\n📊 Inserting league standings and player stats...")
    player_cache = {}

    for season, info in SEASON_MAP.items():
        sid = season_ids[season]
        folder = info['folder']

        # --- Team Standings ---
        cp = get_path(info, 'chemp')
        if cp:
            try:
                df = pd.read_csv(cp, sep=';', encoding='utf-8-sig')
                df.columns = df.columns.str.strip().str.strip('"')
                rows = []
                for _, r in df.iterrows():
                    tname = str(r.get('team','')).strip().strip('"')
                    if not tname: continue
                    tid = get_or_create_team(cursor, team_cache, tname)
                    rows.append((tid,sid,safe_int(r.get('matches')),safe_int(r.get('wins')),
                        safe_int(r.get('draws')),safe_int(r.get('loses')),
                        safe_int(r.get('goals')),safe_int(r.get('ga')),
                        safe_int(r.get('points')),safe_float(r.get('xG')),
                        safe_float(r.get('xGA')),safe_float(r.get('xPTS'))))
                cursor.executemany("""INSERT INTO TeamSeasonStats
                    (TeamID,SeasonID,Matches,Wins,Draws,Loses,Goals,GoalsAgainst,Points,xG,xGA,xPTS)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
                print(f"   ✅ {season}: {len(rows)} team standings")
            except Exception as e:
                print(f"   ⚠️  {season} standings error: {e}")
        else:
            print(f"   ⚠️  {season}: chemp file not found in {folder}")

        # --- Player Stats ---
        pp = get_path(info, 'players')
        if pp:
            try:
                df2 = pd.read_csv(pp, sep=';', encoding='utf-8-sig')
                df2.columns = df2.columns.str.strip().str.strip('"')
                stats_rows = []; errors = 0
                for _, r in df2.iterrows():
                    try:
                        pname = str(r.get('player','')).strip()
                        tname = str(r.get('team','')).strip().split(',')[0].strip()
                        if not pname or not tname or pname=='nan': continue
                        tid = get_or_create_team(cursor, team_cache, tname)
                        if pname not in player_cache:
                            cursor.execute("INSERT INTO Players (PlayerName,TeamID) VALUES (?,?)",(pname,tid))
                            cursor.execute("SELECT @@IDENTITY")
                            player_cache[pname] = int(cursor.fetchone()[0])
                        stats_rows.append((player_cache[pname],sid,
                            safe_int(r.get('apps')),safe_int(r.get('min')),
                            safe_int(r.get('goals')),safe_int(r.get('a')),
                            safe_float(r.get('xG')),safe_float(r.get('xA')),
                            safe_float(r.get('xG90')),safe_float(r.get('xA90'))))
                    except: errors+=1
                cursor.executemany("""INSERT INTO PlayerStats
                    (PlayerID,SeasonID,Apps,Minutes,Goals,Assists,xG,xA,xG90,xA90)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""", stats_rows)
                print(f"   ✅ {season}: {len(stats_rows)} player stats" + (f" ({errors} skipped)" if errors else ""))
            except Exception as e:
                print(f"   ⚠️  {season} players error: {e}")
        else:
            print(f"   ⚠️  {season}: players file not found in {folder}")

    return player_cache

# ============================================================
# INSERT SHOOTING
# ============================================================
def insert_shooting(cursor, season_ids, team_cache):
    print("\n🎯 Inserting shooting stats...")
    for season, info in SEASON_MAP.items():
        path = get_path(info, 'shooting')
        if not path: print(f"   ⚠️  {season}: no shooting file"); continue
        sid = season_ids[season]
        _, rows = parse_fbref_table(path, ['Squad','Sh','SoT'])
        if not rows: print(f"   ⚠️  {season}: could not parse shooting"); continue
        count = 0
        for row in rows:
            tname = row.get('Squad','').strip()
            if not tname or tname=='Squad': continue
            tid = team_cache.get(tname)
            if not tid:
                cursor.execute("SELECT TeamID FROM Teams WHERE TeamName=?",(tname,))
                r = cursor.fetchone()
                if r: tid=r[0]
            if not tid: continue
            cursor.execute("""
                IF EXISTS (SELECT 1 FROM TeamExtendedStats WHERE TeamID=? AND SeasonID=?)
                    UPDATE TeamExtendedStats SET Shots=?,ShotsOnTarget=?,ShotAccuracy=?,ShotsPer90=?,SoTPer90=?,GoalPerShot=?,Penalties=?,PenaltiesAtt=?
                    WHERE TeamID=? AND SeasonID=?
                ELSE
                    INSERT INTO TeamExtendedStats (TeamID,SeasonID,Shots,ShotsOnTarget,ShotAccuracy,ShotsPer90,SoTPer90,GoalPerShot,Penalties,PenaltiesAtt)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
            """, tid,sid,
                safe_int(row.get('Sh')),safe_int(row.get('SoT')),safe_float(row.get('SoT%')),
                safe_float(row.get('Sh/90')),safe_float(row.get('SoT/90')),safe_float(row.get('G/Sh')),
                safe_int(row.get('PK')),safe_int(row.get('PKatt')),
                tid,sid,
                tid,sid,safe_int(row.get('Sh')),safe_int(row.get('SoT')),safe_float(row.get('SoT%')),
                safe_float(row.get('Sh/90')),safe_float(row.get('SoT/90')),safe_float(row.get('G/Sh')),
                safe_int(row.get('PK')),safe_int(row.get('PKatt')))
            count+=1
        print(f"   ✅ {season}: {count} teams shooting")

# ============================================================
# INSERT PLAYER EXTENDED (position, cards, nation)
# ============================================================
def insert_player_extended(cursor, season_ids, player_cache):
    print("\n👤 Inserting player positions and cards...")
    for season, info in SEASON_MAP.items():
        path = get_path(info, 'player_stats')
        if not path: print(f"   ⚠️  {season}: no player stats file"); continue
        sid = season_ids[season]
        with open(path, encoding='utf-8-sig') as f:
            lines = f.readlines()
        header_line = None
        for i, line in enumerate(lines):
            if line.startswith('Rk,Player,Nation,Pos') or ('Player' in line and 'Pos' in line and 'Nation' in line):
                header_line = i; break
        if header_line is None: print(f"   ⚠️  {season}: player header not found"); continue
        rows = []
        for line in lines[header_line+1:]:
            l = line.strip()
            if not l or 'Player' in l[:10]: continue
            parts = re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', l)
            parts = [p.strip().strip('"') for p in parts]
            if len(parts)<19 or not parts[0].isdigit(): continue
            pname = parts[1].strip()
            pos = parts[3].replace('"','').split(',')[0].strip().strip('"').strip("'")
            nation = parts[2].split(' ')[-1] if parts[2] else ''
            pid = player_cache.get(pname)
            if pid is None: continue
            rows.append((pid,sid,pos[:20],nation[:50],
                safe_int(parts[5]),safe_int(parts[8] if len(parts)>8 else '0'),
                safe_int(parts[17] if len(parts)>17 else '0'),
                safe_int(parts[18] if len(parts)>18 else '0'),
                safe_int(parts[15] if len(parts)>15 else '0'),
                safe_int(parts[16] if len(parts)>16 else '0')))
        if rows:
            cursor.executemany("""INSERT INTO PlayerExtendedStats
                (PlayerID,SeasonID,Position,Nation,Age,Starts,YellowCards,RedCards,Penalties,PenaltiesAtt)
                VALUES (?,?,?,?,?,?,?,?,?,?)""", rows)
        print(f"   ✅ {season}: {len(rows)} players with position/cards")

# ============================================================
# INSERT SQUAD EXTENDED (possession, discipline from squad section)
# ============================================================
def insert_squad_extended(cursor, season_ids, team_cache):
    print("\n📋 Inserting possession and discipline...")
    for season, info in SEASON_MAP.items():
        path = get_path(info, 'player_stats')
        if not path: continue
        sid = season_ids[season]
        with open(path, encoding='utf-8-sig') as f:
            lines = f.readlines()
        for i, line in enumerate(lines):
            if line.startswith('Squad,# Pl,Age,Poss') or ('Squad' in line and 'Poss' in line and 'CrdY' in line):
                # Build column index from header — safe against column order changes
                hparts = lines[i].strip().replace('"','').split(',')
                col = {h.strip():idx for idx,h in enumerate(hparts)}
                count = 0
                for j in range(i+1, i+30):
                    if j>=len(lines): break
                    l = lines[j].strip().replace('"','')
                    if not l or l.startswith('Squad') or l.startswith(','): break
                    parts = l.split(',')
                    if len(parts)<10: continue
                    tname = parts[0].strip()
                    if not tname: continue
                    tid = team_cache.get(tname)
                    if not tid:
                        cursor.execute("SELECT TeamID FROM Teams WHERE TeamName=?",(tname,))
                        r = cursor.fetchone()
                        if r: tid=r[0]
                    if not tid: continue
                    # Header-based indexing — CrdY and CrdR positions vary by file
                    poss  = safe_float(parts[col.get('Poss', 3)])
                    crdy  = safe_int(parts[col.get('CrdY', 14)])
                    crdr  = safe_int(parts[col.get('CrdR', 15)])
                    pk    = safe_int(parts[col.get('PK',   12)])
                    pkatt = safe_int(parts[col.get('PKatt',13)])
                    cursor.execute("""
                        IF EXISTS (SELECT 1 FROM TeamExtendedStats WHERE TeamID=? AND SeasonID=?)
                            UPDATE TeamExtendedStats SET Possession=?,YellowCards=?,RedCards=?,Penalties=?,PenaltiesAtt=? WHERE TeamID=? AND SeasonID=?
                        ELSE
                            INSERT INTO TeamExtendedStats (TeamID,SeasonID,Possession,YellowCards,RedCards,Penalties,PenaltiesAtt)
                            VALUES (?,?,?,?,?,?,?)
                    """, tid,sid,poss,crdy,crdr,pk,pkatt,tid,sid, tid,sid,poss,crdy,crdr,pk,pkatt)
                    count+=1
                print(f"   ✅ {season}: {count} teams possession/discipline")
                break

# ============================================================
# INSERT FIXTURES (home/away + attendance)
# ============================================================
def insert_fixtures(cursor, season_ids, team_cache):
    print("\n🏟️  Inserting fixture data...")
    for season, info in SEASON_MAP.items():
        path = get_path(info, 'fixtures')
        if not path: print(f"   ⚠️  {season}: no fixtures file"); continue
        sid = season_ids[season]
        with open(path, encoding='utf-8-sig') as f:
            lines = f.readlines()
        header_line = None
        for i, line in enumerate(lines):
            if 'Wk' in line and 'Home' in line and 'Score' in line:
                header_line = i; break
        if header_line is None: print(f"   ⚠️  {season}: fixture header not found"); continue
        content = ''.join(lines[header_line:])
        reader = csv.DictReader(io.StringIO(content))
        matches = [r for r in reader if r.get('Score','') and '–' in r.get('Score','')]
        team_stats = {}; total_att = {}; att_count = {}
        for m in matches:
            ht=m.get('Home','').strip(); at=m.get('Away','').strip()
            hg,ag = parse_score(m.get('Score',''))
            if hg is None: continue
            att_str = m.get('Attendance','').replace(',','').strip()
            for t in [ht,at]:
                if t not in team_stats:
                    team_stats[t]={'hw':0,'hd':0,'hl':0,'hg':0,'aw':0,'ad':0,'al':0,'ag':0}
            if hg>ag: team_stats[ht]['hw']+=1
            elif hg==ag: team_stats[ht]['hd']+=1
            else: team_stats[ht]['hl']+=1
            team_stats[ht]['hg']+=hg
            if ag>hg: team_stats[at]['aw']+=1
            elif ag==hg: team_stats[at]['ad']+=1
            else: team_stats[at]['al']+=1
            team_stats[at]['ag']+=ag
            if att_str.isdigit():
                total_att[ht]=total_att.get(ht,0)+int(att_str)
                att_count[ht]=att_count.get(ht,0)+1
        count=0
        for tname,s in team_stats.items():
            tid=team_cache.get(tname)
            if not tid:
                cursor.execute("SELECT TeamID FROM Teams WHERE TeamName=?",(tname,))
                r=cursor.fetchone()
                if r: tid=r[0]
            if not tid: continue
            avg_att=int(total_att.get(tname,0)/att_count[tname]) if att_count.get(tname,0)>0 else 0
            cursor.execute("""
                IF EXISTS (SELECT 1 FROM TeamExtendedStats WHERE TeamID=? AND SeasonID=?)
                    UPDATE TeamExtendedStats SET HomeWins=?,HomeDraws=?,HomeLosses=?,HomeGoals=?,AwayWins=?,AwayDraws=?,AwayLosses=?,AwayGoals=?,AvgAttendance=? WHERE TeamID=? AND SeasonID=?
                ELSE
                    INSERT INTO TeamExtendedStats (TeamID,SeasonID,HomeWins,HomeDraws,HomeLosses,HomeGoals,AwayWins,AwayDraws,AwayLosses,AwayGoals,AvgAttendance)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, tid,sid,s['hw'],s['hd'],s['hl'],s['hg'],s['aw'],s['ad'],s['al'],s['ag'],avg_att,tid,sid,
                 tid,sid,s['hw'],s['hd'],s['hl'],s['hg'],s['aw'],s['ad'],s['al'],s['ag'],avg_att)
            count+=1
        print(f"   ✅ {season}: {count} teams home/away/attendance")

# ============================================================
# MAIN
# ============================================================
def main():
    print("="*58)
    print("  PREMIERSTAT — FULL DATA IMPORT")
    print("="*58)

    # Show what files were found
    print("\n📂 Checking files...")
    for season, info in SEASON_MAP.items():
        folder = info['folder']
        exists = os.path.exists(folder)
        print(f"\n  {season} → {folder} {'✅' if exists else '❌ NOT FOUND'}")
        if exists:
            for ftype in ['chemp','players','player_stats','fixtures','shooting']:
                p = get_path(info, ftype)
                status = f"✅ {os.path.basename(p)}" if p else "⚠️  not found"
                print(f"    {ftype:15}: {status}")

    print("\n" + "="*58)
    confirm = input("Continue with import? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled."); return

    start = time.time()
    conn = get_conn()
    cursor = conn.cursor()
    team_cache = {}

    try:
        setup_db(cursor)
        clear_data(cursor)
        conn.commit()

        season_ids = insert_seasons(cursor)
        conn.commit()

        player_cache = insert_core(cursor, season_ids, team_cache)
        conn.commit()

        insert_shooting(cursor, season_ids, team_cache)
        conn.commit()

        insert_player_extended(cursor, season_ids, player_cache)
        conn.commit()

        insert_squad_extended(cursor, season_ids, team_cache)
        conn.commit()

        insert_fixtures(cursor, season_ids, team_cache)
        conn.commit()

        elapsed = time.time()-start
        print(f"\n{'='*58}")
        print(f"  ✅ IMPORT COMPLETE in {elapsed:.1f}s")
        print(f"  Seasons : {len(season_ids)}")
        print(f"  Teams   : {len(team_cache)}")
        print(f"  Players : {len(player_cache)}")
        print(f"{'='*58}")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        conn.close()

if __name__ == '__main__':
    main()
