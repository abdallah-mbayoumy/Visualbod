import pyodbc
import pandas as pd
import os
import time

# ============================================================
# CONFIGURATION — change folder path if needed
# ============================================================
FOLDER = r"C:\Users\Data\Documents\abdallah\Projects\Visualbod\premuier league"

# Map each CSV pair to its season name
# Format: 'SeasonName': ('team_standings_file', 'players_file')
SEASON_MAP = {
    '2020/21': ('league-chemp.csv',    'league-players.csv'),
    '2021/22': ('league-chemp (1).csv','league-players (1).csv'),
    '2022/23': ('league-chemp (2).csv','league-players (2).csv'),
    '2023/24': ('league-chemp (3).csv','league-players (3).csv'),
    '2024/25': ('league-chemp (4).csv','league-players (4).csv'),
}

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
# SETUP — create TeamSeasonStats if missing
# ============================================================
def setup_db(cursor):
    cursor.execute("""
        IF NOT EXISTS (
            SELECT * FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_NAME = 'TeamSeasonStats'
        )
        CREATE TABLE TeamSeasonStats (
            ID           INT IDENTITY(1,1) PRIMARY KEY,
            TeamID       INT NOT NULL,
            SeasonID     INT NOT NULL,
            Matches      INT DEFAULT 0,
            Wins         INT DEFAULT 0,
            Draws        INT DEFAULT 0,
            Loses        INT DEFAULT 0,
            Goals        INT DEFAULT 0,
            GoalsAgainst INT DEFAULT 0,
            Points       INT DEFAULT 0,
            xG           FLOAT DEFAULT 0,
            xGA          FLOAT DEFAULT 0,
            xPTS         FLOAT DEFAULT 0
        )
    """)
    print("✅ TeamSeasonStats table ready")

# ============================================================
# CLEAR OLD DATA (fresh import)
# ============================================================
def clear_data(cursor):
    print("\n🗑️  Clearing old data...")
    cursor.execute("DELETE FROM TeamSeasonStats")
    cursor.execute("DELETE FROM PlayerStats")
    cursor.execute("DELETE FROM Players")
    cursor.execute("DELETE FROM Teams")
    cursor.execute("DELETE FROM Seasons")
    print("✅ Old data cleared")

# ============================================================
# HELPER — get or create a team, return TeamID
# ============================================================
def get_or_create_team(cursor, team_cache, team_name):
    team_name = team_name.strip()
    if team_name in team_cache:
        return team_cache[team_name]

    cursor.execute("SELECT TeamID FROM Teams WHERE TeamName=?", (team_name,))
    row = cursor.fetchone()
    if row:
        team_cache[team_name] = row[0]
        return row[0]

    cursor.execute("INSERT INTO Teams (TeamName) VALUES (?)", (team_name,))
    cursor.execute("SELECT @@IDENTITY")
    tid = int(cursor.fetchone()[0])
    team_cache[team_name] = tid
    return tid

# ============================================================
# INSERT SEASONS
# ============================================================
def insert_seasons(cursor):
    print("\n📅 Inserting seasons...")
    season_ids = {}
    for season_name in SEASON_MAP:
        cursor.execute(
            "INSERT INTO Seasons (SeasonName) VALUES (?)", (season_name,)
        )
        cursor.execute("SELECT @@IDENTITY")
        sid = int(cursor.fetchone()[0])
        season_ids[season_name] = sid
        print(f"   → {season_name} (ID={sid})")
    return season_ids

# ============================================================
# INSERT TEAM STANDINGS
# ============================================================
def insert_team_standings(cursor, season_ids, team_cache):
    print("\n🏆 Inserting team standings...")
    total = 0

    for season_name, (chemp_file, _) in SEASON_MAP.items():
        path = os.path.join(FOLDER, chemp_file)
        if not os.path.exists(path):
            print(f"   ⚠️  File not found: {chemp_file} — skipping")
            continue

        sid = season_ids[season_name]
        df = pd.read_csv(path, sep=';', encoding='utf-8-sig')
        df.columns = df.columns.str.strip().str.strip('"')

        rows = []
        for _, row in df.iterrows():
            team_name = str(row.get('team', '')).strip().strip('"')
            if not team_name:
                continue
            tid = get_or_create_team(cursor, team_cache, team_name)
            rows.append((
                tid, sid,
                int(row.get('matches', 0)),
                int(row.get('wins', 0)),
                int(row.get('draws', 0)),
                int(row.get('loses', 0)),
                int(row.get('goals', 0)),
                int(row.get('ga', 0)),
                int(row.get('points', 0)),
                float(row.get('xG', 0)),
                float(row.get('xGA', 0)),
                float(row.get('xPTS', 0)),
            ))

        cursor.executemany("""
            INSERT INTO TeamSeasonStats
            (TeamID, SeasonID, Matches, Wins, Draws, Loses, Goals, GoalsAgainst, Points, xG, xGA, xPTS)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, rows)
        total += len(rows)
        print(f"   ✅ {season_name}: {len(rows)} teams")

    print(f"   Total: {total} team-season rows")

# ============================================================
# INSERT PLAYERS + PLAYER STATS
# ============================================================
def insert_players(cursor, season_ids, team_cache):
    print("\n👤 Inserting players and stats...")

    # player_cache: name -> PlayerID  (one entry per unique player name)
    player_cache = {}
    total_stats = 0
    errors = 0

    for season_name, (_, players_file) in SEASON_MAP.items():
        path = os.path.join(FOLDER, players_file)
        if not os.path.exists(path):
            print(f"   ⚠️  File not found: {players_file} — skipping")
            continue

        sid = season_ids[season_name]
        df = pd.read_csv(path, sep=';', encoding='utf-8-sig')
        df.columns = df.columns.str.strip().str.strip('"')

        stats_rows = []
        for _, row in df.iterrows():
            try:
                player_name = str(row.get('player', '')).strip()
                team_name   = str(row.get('team', '')).strip().split(',')[0].strip()

                if not player_name or not team_name or player_name == 'nan':
                    continue

                # Get or create team
                tid = get_or_create_team(cursor, team_cache, team_name)

                # Get or create player
                if player_name not in player_cache:
                    cursor.execute(
                        "INSERT INTO Players (PlayerName, TeamID) VALUES (?,?)",
                        (player_name, tid)
                    )
                    cursor.execute("SELECT @@IDENTITY")
                    pid = int(cursor.fetchone()[0])
                    player_cache[player_name] = pid
                else:
                    pid = player_cache[player_name]

                stats_rows.append((
                    pid, sid,
                    int(float(row.get('apps', 0))),
                    int(float(row.get('min', 0))),
                    int(float(row.get('goals', 0))),
                    int(float(row.get('a', 0))),
                    float(row.get('xG', 0)),
                    float(row.get('xA', 0)),
                    float(row.get('xG90', 0)),
                    float(row.get('xA90', 0)),
                ))

            except Exception as e:
                errors += 1
                if errors <= 5:
                    print(f"   ⚠️  Row error: {e}")

        # Batch insert stats
        cursor.executemany("""
            INSERT INTO PlayerStats
            (PlayerID, SeasonID, Apps, Minutes, Goals, Assists, xG, xA, xG90, xA90)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, stats_rows)

        total_stats += len(stats_rows)
        print(f"   ✅ {season_name}: {len(stats_rows)} player-season rows")

    print(f"   Total players: {len(player_cache)}")
    print(f"   Total stat rows: {total_stats}")
    if errors:
        print(f"   ⚠️  Skipped rows (errors): {errors}")

# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 55)
    print("  PREMIER LEAGUE DATA IMPORT")
    print("=" * 55)
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

        insert_team_standings(cursor, season_ids, team_cache)
        conn.commit()

        insert_players(cursor, season_ids, team_cache)
        conn.commit()

        elapsed = time.time() - start
        print(f"\n{'='*55}")
        print(f"  ✅ IMPORT COMPLETE in {elapsed:.1f}s")
        print(f"  Seasons : {len(season_ids)}")
        print(f"  Teams   : {len(team_cache)}")
        print(f"{'='*55}")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ FATAL ERROR: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    main()
