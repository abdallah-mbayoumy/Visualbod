from flask import Flask, render_template, jsonify, request
import pyodbc

app = Flask(__name__)

# ============================================================
# DB CONNECTION
# ============================================================
def get_connection():
    return pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=(localdb)\\MSSQLLocalDB;"
        "DATABASE=PremierLeagueDB;"
        "Trusted_Connection=yes;"
    )

def query(sql, params=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql, params or [])
    cols = [c[0] for c in cursor.description]
    rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
    conn.close()
    return rows

def season_filter(sid_param='season_id', alias='s'):
    """Returns a WHERE/AND clause fragment if season_id is passed."""
    sid = request.args.get(sid_param)
    if sid:
        return f"AND {alias}.SeasonID = {int(sid)}", int(sid)
    return "", None

# ============================================================
# PAGES
# ============================================================
@app.route('/')
def home():
    return render_template('dashboard.html')

# ============================================================
# SEASONS
# ============================================================
@app.route('/api/seasons')
def seasons():
    return jsonify(query("SELECT SeasonID, SeasonName FROM Seasons ORDER BY SeasonID"))

# ============================================================
# KPIs
# ============================================================
@app.route('/api/kpis')
def kpis():
    sf, sid = season_filter()
    season_clause = f"WHERE SeasonID = {sid}" if sid else ""
    player_season_clause = f"WHERE s.SeasonID = {sid}" if sid else ""

    data = query(f"""
        SELECT
            (SELECT COUNT(DISTINCT p.PlayerID)
             FROM Players p
             JOIN PlayerStats s ON p.PlayerID = s.PlayerID
             {player_season_clause}) AS TotalPlayers,

            (SELECT COUNT(*) FROM Teams) AS TotalTeams,

            (SELECT ISNULL(SUM(Goals),0) FROM PlayerStats {season_clause}) AS TotalGoals,
            (SELECT ISNULL(SUM(Assists),0) FROM PlayerStats {season_clause}) AS TotalAssists,

            (SELECT COUNT(*) FROM Seasons) AS TotalSeasons
    """)
    return jsonify(data[0] if data else {})

# ============================================================
# TOP SCORERS
# ============================================================
@app.route('/api/top-scorers')
def top_scorers():
    sf, _ = season_filter()
    return jsonify(query(f"""
        SELECT TOP 15
            p.PlayerName,
            t.TeamName,
            s.SeasonID,
            se.SeasonName,
            s.Goals,
            s.Assists,
            s.Goals + s.Assists AS Contributions,
            s.Apps,
            s.Minutes,
            ROUND(s.xG, 2) AS xG,
            ROUND(s.xA, 2) AS xA
        FROM PlayerStats s
        JOIN Players p ON s.PlayerID = p.PlayerID
        JOIN Teams t   ON p.TeamID   = t.TeamID
        JOIN Seasons se ON s.SeasonID = se.SeasonID
        WHERE 1=1 {sf}
        ORDER BY s.Goals DESC
    """))

# ============================================================
# TOP ASSISTS
# ============================================================
@app.route('/api/top-assists')
def top_assists():
    sf, _ = season_filter()
    return jsonify(query(f"""
        SELECT TOP 15
            p.PlayerName,
            t.TeamName,
            se.SeasonName,
            s.Goals,
            s.Assists,
            s.Goals + s.Assists AS Contributions,
            s.Apps,
            ROUND(s.xA, 2) AS xA
        FROM PlayerStats s
        JOIN Players p  ON s.PlayerID = p.PlayerID
        JOIN Teams t    ON p.TeamID   = t.TeamID
        JOIN Seasons se ON s.SeasonID = se.SeasonID
        WHERE 1=1 {sf}
        ORDER BY s.Assists DESC
    """))

# ============================================================
# TOP CONTRIBUTIONS (Goals + Assists)
# ============================================================
@app.route('/api/top-contributions')
def top_contributions():
    sf, _ = season_filter()
    return jsonify(query(f"""
        SELECT TOP 15
            p.PlayerName,
            t.TeamName,
            se.SeasonName,
            s.Goals,
            s.Assists,
            s.Goals + s.Assists AS Contributions,
            s.Apps,
            ROUND(s.xG + s.xA, 2) AS xGI
        FROM PlayerStats s
        JOIN Players p  ON s.PlayerID = p.PlayerID
        JOIN Teams t    ON p.TeamID   = t.TeamID
        JOIN Seasons se ON s.SeasonID = se.SeasonID
        WHERE 1=1 {sf}
        ORDER BY Contributions DESC
    """))

# ============================================================
# ALL PLAYERS (filterable)
# ============================================================
@app.route('/api/all-players')
def all_players():
    sf, _ = season_filter()
    return jsonify(query(f"""
        SELECT
            p.PlayerName,
            t.TeamName,
            se.SeasonName,
            s.Apps,
            s.Minutes,
            s.Goals,
            s.Assists,
            s.Goals + s.Assists AS Contributions,
            ROUND(s.xG, 2) AS xG,
            ROUND(s.xA, 2) AS xA,
            ROUND(s.xG90, 2) AS xG90,
            ROUND(s.xA90, 2) AS xA90
        FROM PlayerStats s
        JOIN Players p  ON s.PlayerID = p.PlayerID
        JOIN Teams t    ON p.TeamID   = t.TeamID
        JOIN Seasons se ON s.SeasonID = se.SeasonID
        WHERE s.Apps > 0 {sf}
        ORDER BY s.Goals DESC
    """))

# ============================================================
# GOALS PER TEAM
# ============================================================
@app.route('/api/goals-per-team')
def goals_per_team():
    sf, _ = season_filter()
    return jsonify(query(f"""
        SELECT
            t.TeamName,
            SUM(s.Goals)   AS TotalGoals,
            SUM(s.Assists) AS TotalAssists,
            SUM(s.Goals + s.Assists) AS TotalContributions
        FROM PlayerStats s
        JOIN Players p ON s.PlayerID = p.PlayerID
        JOIN Teams t   ON p.TeamID   = t.TeamID
        WHERE 1=1 {sf}
        GROUP BY t.TeamName
        ORDER BY TotalGoals DESC
    """))

# ============================================================
# ASSISTS PER TEAM
# ============================================================
@app.route('/api/assists-per-team')
def assists_per_team():
    sf, _ = season_filter()
    return jsonify(query(f"""
        SELECT
            t.TeamName,
            SUM(s.Assists) AS TotalAssists
        FROM PlayerStats s
        JOIN Players p ON s.PlayerID = p.PlayerID
        JOIN Teams t   ON p.TeamID   = t.TeamID
        WHERE 1=1 {sf}
        GROUP BY t.TeamName
        ORDER BY TotalAssists DESC
    """))

# ============================================================
# TEAM STANDINGS (from TeamSeasonStats)
# ============================================================
@app.route('/api/team-standings')
def team_standings():
    sf, _ = season_filter(alias='ts')
    return jsonify(query(f"""
        SELECT
            t.TeamName,
            se.SeasonName,
            ts.Matches,
            ts.Wins,
            ts.Draws,
            ts.Loses,
            ts.Goals,
            ts.GoalsAgainst,
            ts.Goals - ts.GoalsAgainst AS GoalDiff,
            ts.Points,
            ROUND(ts.xG, 2)   AS xG,
            ROUND(ts.xGA, 2)  AS xGA,
            ROUND(ts.xPTS, 2) AS xPTS,
            ROUND(ts.xG - ts.Goals, 2) AS xG_Diff
        FROM TeamSeasonStats ts
        JOIN Teams t    ON ts.TeamID   = t.TeamID
        JOIN Seasons se ON ts.SeasonID = se.SeasonID
        WHERE 1=1 {sf}
        ORDER BY ts.Points DESC
    """))

# ============================================================
# XG vs ACTUAL (over/under performers)
# ============================================================
@app.route('/api/xg-analysis')
def xg_analysis():
    sf, _ = season_filter()
    return jsonify(query(f"""
        SELECT TOP 20
            p.PlayerName,
            t.TeamName,
            se.SeasonName,
            s.Goals,
            ROUND(s.xG, 2) AS xG,
            ROUND(s.Goals - s.xG, 2) AS xG_Diff,
            s.Apps
        FROM PlayerStats s
        JOIN Players p  ON s.PlayerID = p.PlayerID
        JOIN Teams t    ON p.TeamID   = t.TeamID
        JOIN Seasons se ON s.SeasonID = se.SeasonID
        WHERE s.Goals >= 5 {sf}
        ORDER BY ABS(s.Goals - s.xG) DESC
    """))

# ============================================================
# TOP SCORER PER SEASON
# ============================================================
@app.route('/api/top-scorer-per-season')
def top_scorer_per_season():
    return jsonify(query("""
        SELECT
            se.SeasonName,
            p.PlayerName,
            t.TeamName,
            s.Goals,
            s.Assists,
            s.Goals + s.Assists AS Contributions
        FROM PlayerStats s
        JOIN Players p  ON s.PlayerID = p.PlayerID
        JOIN Teams t    ON p.TeamID   = t.TeamID
        JOIN Seasons se ON s.SeasonID = se.SeasonID
        WHERE s.Goals = (
            SELECT MAX(s2.Goals)
            FROM PlayerStats s2
            WHERE s2.SeasonID = s.SeasonID
        )
        ORDER BY se.SeasonID
    """))

# ============================================================
# TOP ASSISTS PER SEASON
# ============================================================
@app.route('/api/top-assists-per-season')
def top_assists_per_season():
    return jsonify(query("""
        SELECT
            se.SeasonName,
            p.PlayerName,
            t.TeamName,
            s.Goals,
            s.Assists
        FROM PlayerStats s
        JOIN Players p  ON s.PlayerID = p.PlayerID
        JOIN Teams t    ON p.TeamID   = t.TeamID
        JOIN Seasons se ON s.SeasonID = se.SeasonID
        WHERE s.Assists = (
            SELECT MAX(s2.Assists)
            FROM PlayerStats s2
            WHERE s2.SeasonID = s.SeasonID
        )
        ORDER BY se.SeasonID
    """))

# ============================================================
# TEAM PERFORMANCE OVER SEASONS (for line chart)
# ============================================================
@app.route('/api/team-season-performance')
def team_season_performance():
    team = request.args.get('team', '')
    if not team:
        return jsonify([])
    return jsonify(query("""
        SELECT
            se.SeasonName,
            ts.Points,
            ts.Goals,
            ts.GoalsAgainst,
            ts.Wins,
            ROUND(ts.xG, 2) AS xG,
            ROUND(ts.xGA, 2) AS xGA
        FROM TeamSeasonStats ts
        JOIN Teams t    ON ts.TeamID   = t.TeamID
        JOIN Seasons se ON ts.SeasonID = se.SeasonID
        WHERE t.TeamName = ?
        ORDER BY se.SeasonID
    """, [team]))

# ============================================================
# SEASON COMPARE — top teams side by side
# ============================================================
@app.route('/api/season-compare')
def season_compare():
    return jsonify(query("""
        SELECT
            t.TeamName,
            se.SeasonName,
            ts.Points,
            ts.Goals,
            ts.GoalsAgainst,
            ts.Wins,
            ROUND(ts.xG, 2) AS xG
        FROM TeamSeasonStats ts
        JOIN Teams t    ON ts.TeamID   = t.TeamID
        JOIN Seasons se ON ts.SeasonID = se.SeasonID
        ORDER BY se.SeasonID, ts.Points DESC
    """))

# ============================================================
# GOALS CONCEDED PER TEAM
# ============================================================
@app.route('/api/goals-conceded')
def goals_conceded():
    sf, _ = season_filter(alias='ts')
    return jsonify(query(f"""
        SELECT
            t.TeamName,
            se.SeasonName,
            ts.GoalsAgainst,
            ROUND(ts.xGA, 2) AS xGA
        FROM TeamSeasonStats ts
        JOIN Teams t    ON ts.TeamID   = t.TeamID
        JOIN Seasons se ON ts.SeasonID = se.SeasonID
        WHERE 1=1 {sf}
        ORDER BY ts.GoalsAgainst ASC
    """))

# ============================================================
# MINUTES PER GOAL (efficiency)
# ============================================================
@app.route('/api/efficiency')
def efficiency():
    sf, _ = season_filter()
    return jsonify(query(f"""
        SELECT TOP 20
            p.PlayerName,
            t.TeamName,
            se.SeasonName,
            s.Goals,
            s.Minutes,
            CASE WHEN s.Goals > 0
                 THEN ROUND(CAST(s.Minutes AS FLOAT) / s.Goals, 0)
                 ELSE NULL END AS MinutesPerGoal,
            ROUND(s.xG90, 2) AS xG90
        FROM PlayerStats s
        JOIN Players p  ON s.PlayerID = p.PlayerID
        JOIN Teams t    ON p.TeamID   = t.TeamID
        JOIN Seasons se ON s.SeasonID = se.SeasonID
        WHERE s.Goals >= 8 AND s.Minutes > 0 {sf}
        ORDER BY MinutesPerGoal ASC
    """))

# ============================================================
# TEST CONNECTION
# ============================================================
@app.route('/api/test')
def test():
    try:
        data = query("SELECT COUNT(*) AS cnt FROM Players")
        return jsonify({"status": "ok", "players": data[0]['cnt']})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# ============================================================
# ALL TEAMS LIST
# ============================================================
@app.route('/api/teams')
def teams():
    return jsonify(query("SELECT TeamID, TeamName FROM Teams ORDER BY TeamName"))

# ============================================================
# RUN
# ============================================================
if __name__ == '__main__':
    print("🚀 Server running → http://127.0.0.1:5000")
    app.run(debug=True)
