from flask import Flask, render_template, jsonify, request
import pyodbc

app = Flask(__name__)

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

def sf(alias='s'):
    sid = request.args.get('season_id')
    return (f"AND {alias}.SeasonID={int(sid)}", int(sid)) if sid else ("", None)

def sf_where(alias='s'):
    sid = request.args.get('season_id')
    return (f"WHERE {alias}.SeasonID={int(sid)}", int(sid)) if sid else ("WHERE 1=1", None)

@app.route('/')
def home(): return render_template('dashboard.html')

# ── BASIC ──────────────────────────────────────────────────
@app.route('/api/seasons')
def seasons(): return jsonify(query("SELECT SeasonID,SeasonName FROM Seasons ORDER BY SeasonID"))

@app.route('/api/teams')
def teams(): return jsonify(query("SELECT TeamID,TeamName FROM Teams ORDER BY TeamName"))

@app.route('/api/kpis')
def kpis():
    frag, sid = sf()
    sc = f"WHERE SeasonID={sid}" if sid else ""
    psc = f"WHERE s.SeasonID={sid}" if sid else ""
    return jsonify(query(f"""SELECT
        (SELECT COUNT(DISTINCT p.PlayerID) FROM Players p JOIN PlayerStats s ON p.PlayerID=s.PlayerID {psc}) AS TotalPlayers,
        (SELECT COUNT(*) FROM Teams) AS TotalTeams,
        (SELECT ISNULL(SUM(Goals),0) FROM PlayerStats {sc}) AS TotalGoals,
        (SELECT ISNULL(SUM(Assists),0) FROM PlayerStats {sc}) AS TotalAssists,
        (SELECT COUNT(*) FROM Seasons) AS TotalSeasons""")[0])

# ── PLAYERS ────────────────────────────────────────────────
@app.route('/api/top-scorers')
def top_scorers():
    frag, _ = sf()
    return jsonify(query(f"""SELECT TOP 15 p.PlayerName,t.TeamName,se.SeasonName,
        s.Goals,s.Assists,s.Goals+s.Assists AS Contributions,s.Apps,s.Minutes,
        ROUND(s.xG,2) AS xG,ROUND(s.xA,2) AS xA
        FROM PlayerStats s JOIN Players p ON s.PlayerID=p.PlayerID
        JOIN Teams t ON p.TeamID=t.TeamID JOIN Seasons se ON s.SeasonID=se.SeasonID
        WHERE 1=1 {frag} ORDER BY s.Goals DESC"""))

@app.route('/api/top-assists')
def top_assists():
    frag, _ = sf()
    return jsonify(query(f"""SELECT TOP 15 p.PlayerName,t.TeamName,se.SeasonName,
        s.Goals,s.Assists,s.Goals+s.Assists AS Contributions,s.Apps,ROUND(s.xA,2) AS xA
        FROM PlayerStats s JOIN Players p ON s.PlayerID=p.PlayerID
        JOIN Teams t ON p.TeamID=t.TeamID JOIN Seasons se ON s.SeasonID=se.SeasonID
        WHERE 1=1 {frag} ORDER BY s.Assists DESC"""))

@app.route('/api/top-contributions')
def top_contributions():
    frag, _ = sf()
    return jsonify(query(f"""SELECT TOP 15 p.PlayerName,t.TeamName,se.SeasonName,
        s.Goals,s.Assists,s.Goals+s.Assists AS Contributions,
        ROUND(s.xG+s.xA,2) AS xGI
        FROM PlayerStats s JOIN Players p ON s.PlayerID=p.PlayerID
        JOIN Teams t ON p.TeamID=t.TeamID JOIN Seasons se ON s.SeasonID=se.SeasonID
        WHERE 1=1 {frag} ORDER BY Contributions DESC"""))

@app.route('/api/all-players')
def all_players():
    frag, _ = sf()
    return jsonify(query(f"""SELECT p.PlayerName,t.TeamName,se.SeasonName,
        s.Apps,s.Minutes,s.Goals,s.Assists,s.Goals+s.Assists AS Contributions,
        ROUND(s.xG,2) AS xG,ROUND(s.xA,2) AS xA,
        ROUND(s.xG90,2) AS xG90,ROUND(s.xA90,2) AS xA90,
        ISNULL(pe.Position,'—') AS Position,
        ISNULL(pe.Nation,'—') AS Nation,
        ISNULL(pe.YellowCards,0) AS YellowCards,
        ISNULL(pe.RedCards,0) AS RedCards
        FROM PlayerStats s JOIN Players p ON s.PlayerID=p.PlayerID
        JOIN Teams t ON p.TeamID=t.TeamID JOIN Seasons se ON s.SeasonID=se.SeasonID
        LEFT JOIN PlayerExtendedStats pe ON pe.PlayerID=s.PlayerID AND pe.SeasonID=s.SeasonID
        WHERE s.Apps>0 {frag} ORDER BY s.Goals DESC"""))

@app.route('/api/goals-per-team')
def goals_per_team():
    frag, _ = sf()
    return jsonify(query(f"""SELECT t.TeamName,
        SUM(s.Goals) AS TotalGoals,SUM(s.Assists) AS TotalAssists,
        SUM(s.Goals+s.Assists) AS TotalContributions
        FROM PlayerStats s JOIN Players p ON s.PlayerID=p.PlayerID
        JOIN Teams t ON p.TeamID=t.TeamID
        WHERE 1=1 {frag} GROUP BY t.TeamName ORDER BY TotalGoals DESC"""))

@app.route('/api/top-scorer-per-season')
def top_scorer_per_season():
    return jsonify(query("""SELECT se.SeasonName,p.PlayerName,t.TeamName,s.Goals,s.Assists
        FROM PlayerStats s JOIN Players p ON s.PlayerID=p.PlayerID
        JOIN Teams t ON p.TeamID=t.TeamID JOIN Seasons se ON s.SeasonID=se.SeasonID
        WHERE s.Goals=(SELECT MAX(s2.Goals) FROM PlayerStats s2 WHERE s2.SeasonID=s.SeasonID)
        ORDER BY se.SeasonID"""))

@app.route('/api/top-assists-per-season')
def top_assists_per_season():
    return jsonify(query("""SELECT se.SeasonName,p.PlayerName,t.TeamName,s.Goals,s.Assists
        FROM PlayerStats s JOIN Players p ON s.PlayerID=p.PlayerID
        JOIN Teams t ON p.TeamID=t.TeamID JOIN Seasons se ON s.SeasonID=se.SeasonID
        WHERE s.Assists=(SELECT MAX(s2.Assists) FROM PlayerStats s2 WHERE s2.SeasonID=s.SeasonID)
        ORDER BY se.SeasonID"""))

@app.route('/api/xg-analysis')
def xg_analysis():
    frag, _ = sf()
    return jsonify(query(f"""SELECT TOP 25 p.PlayerName,t.TeamName,se.SeasonName,
        s.Goals,ROUND(s.xG,2) AS xG,ROUND(s.Goals-s.xG,2) AS xG_Diff,s.Apps
        FROM PlayerStats s JOIN Players p ON s.PlayerID=p.PlayerID
        JOIN Teams t ON p.TeamID=t.TeamID JOIN Seasons se ON s.SeasonID=se.SeasonID
        WHERE s.Goals>=5 {frag} ORDER BY ABS(s.Goals-s.xG) DESC"""))

@app.route('/api/efficiency')
def efficiency():
    frag, _ = sf()
    return jsonify(query(f"""SELECT TOP 20 p.PlayerName,t.TeamName,se.SeasonName,
        s.Goals,s.Minutes,
        CASE WHEN s.Goals>0 THEN ROUND(CAST(s.Minutes AS FLOAT)/s.Goals,0) ELSE NULL END AS MinutesPerGoal,
        ROUND(s.xG90,2) AS xG90
        FROM PlayerStats s JOIN Players p ON s.PlayerID=p.PlayerID
        JOIN Teams t ON p.TeamID=t.TeamID JOIN Seasons se ON s.SeasonID=se.SeasonID
        WHERE s.Goals>=8 AND s.Minutes>0 {frag} ORDER BY MinutesPerGoal ASC"""))

# ── POSITION ANALYSIS ──────────────────────────────────────
@app.route('/api/position-stats')
def position_stats():
    frag, _ = sf('s')
    return jsonify(query(f"""SELECT pe.Position,
        SUM(s.Goals) AS TotalGoals,SUM(s.Assists) AS TotalAssists,
        SUM(s.Goals+s.Assists) AS TotalContributions,
        SUM(s.Minutes) AS TotalMinutes,SUM(s.Apps) AS TotalApps,
        COUNT(DISTINCT s.PlayerID) AS PlayerCount,
        ROUND(AVG(s.xG90),3) AS AvgxG90,ROUND(AVG(s.xA90),3) AS AvgxA90,
        SUM(ISNULL(pe.YellowCards,0)) AS TotalYellows,
        SUM(ISNULL(pe.RedCards,0)) AS TotalReds
        FROM PlayerStats s
        JOIN PlayerExtendedStats pe ON pe.PlayerID=s.PlayerID AND pe.SeasonID=s.SeasonID
        WHERE pe.Position IS NOT NULL AND pe.Position!='' {frag}
        GROUP BY pe.Position ORDER BY TotalGoals DESC"""))

@app.route('/api/position-leaders')
def position_leaders():
    frag, _ = sf('s')
    return jsonify(query(f"""SELECT pe.Position,p.PlayerName,t.TeamName,se.SeasonName,
        s.Goals,s.Assists,s.Goals+s.Assists AS Contributions,s.Minutes
        FROM PlayerStats s
        JOIN PlayerExtendedStats pe ON pe.PlayerID=s.PlayerID AND pe.SeasonID=s.SeasonID
        JOIN Players p ON s.PlayerID=p.PlayerID
        JOIN Teams t ON p.TeamID=t.TeamID JOIN Seasons se ON s.SeasonID=se.SeasonID
        WHERE pe.Position IS NOT NULL AND pe.Position!='' {frag}
        AND s.Goals=(SELECT MAX(s2.Goals) FROM PlayerStats s2
            JOIN PlayerExtendedStats pe2 ON pe2.PlayerID=s2.PlayerID AND pe2.SeasonID=s2.SeasonID
            WHERE pe2.Position=pe.Position AND s2.SeasonID=s.SeasonID)
        ORDER BY pe.Position"""))

# ── TEAM STANDINGS & EXTENDED ──────────────────────────────
@app.route('/api/team-standings')
def team_standings():
    frag, _ = sf('ts')
    return jsonify(query(f"""SELECT t.TeamName,se.SeasonName,
        ts.Matches,ts.Wins,ts.Draws,ts.Loses,ts.Goals,ts.GoalsAgainst,
        ts.Goals-ts.GoalsAgainst AS GoalDiff,ts.Points,
        ROUND(ts.xG,2) AS xG,ROUND(ts.xGA,2) AS xGA,ROUND(ts.xPTS,2) AS xPTS,
        ISNULL(te.Possession,0) AS Possession,
        ISNULL(te.Shots,0) AS Shots,ISNULL(te.ShotsOnTarget,0) AS ShotsOnTarget,
        ISNULL(te.ShotAccuracy,0) AS ShotAccuracy,
        ISNULL(te.YellowCards,0) AS YellowCards,ISNULL(te.RedCards,0) AS RedCards,
        ISNULL(te.Penalties,0) AS Penalties,ISNULL(te.PenaltiesAtt,0) AS PenaltiesAtt,
        ISNULL(te.HomeWins,0) AS HomeWins,ISNULL(te.HomeDraws,0) AS HomeDraws,
        ISNULL(te.HomeLosses,0) AS HomeLosses,ISNULL(te.HomeGoals,0) AS HomeGoals,
        ISNULL(te.AwayWins,0) AS AwayWins,ISNULL(te.AwayDraws,0) AS AwayDraws,
        ISNULL(te.AwayLosses,0) AS AwayLosses,ISNULL(te.AwayGoals,0) AS AwayGoals,
        ISNULL(te.AvgAttendance,0) AS AvgAttendance
        FROM TeamSeasonStats ts
        JOIN Teams t ON ts.TeamID=t.TeamID JOIN Seasons se ON ts.SeasonID=se.SeasonID
        LEFT JOIN TeamExtendedStats te ON te.TeamID=ts.TeamID AND te.SeasonID=ts.SeasonID
        WHERE 1=1 {frag} ORDER BY ts.Points DESC"""))

@app.route('/api/goals-conceded')
def goals_conceded():
    frag, _ = sf('ts')
    return jsonify(query(f"""SELECT t.TeamName,se.SeasonName,ts.GoalsAgainst,ROUND(ts.xGA,2) AS xGA
        FROM TeamSeasonStats ts JOIN Teams t ON ts.TeamID=t.TeamID
        JOIN Seasons se ON ts.SeasonID=se.SeasonID
        WHERE 1=1 {frag} ORDER BY ts.GoalsAgainst ASC"""))

@app.route('/api/team-discipline')
def team_discipline():
    frag, _ = sf('te')
    return jsonify(query(f"""SELECT t.TeamName,se.SeasonName,
        te.YellowCards,te.RedCards,te.Penalties,te.PenaltiesAtt
        FROM TeamExtendedStats te JOIN Teams t ON te.TeamID=t.TeamID
        JOIN Seasons se ON te.SeasonID=se.SeasonID
        WHERE 1=1 {frag} ORDER BY te.YellowCards DESC"""))

@app.route('/api/team-shooting')
def team_shooting():
    frag, _ = sf('te')
    return jsonify(query(f"""SELECT t.TeamName,se.SeasonName,
        te.Shots,te.ShotsOnTarget,te.ShotAccuracy,
        te.ShotsPer90,te.SoTPer90,te.GoalPerShot,te.Possession
        FROM TeamExtendedStats te JOIN Teams t ON te.TeamID=t.TeamID
        JOIN Seasons se ON te.SeasonID=se.SeasonID
        WHERE te.Shots>0 {frag} ORDER BY te.Shots DESC"""))

@app.route('/api/team-home-away')
def team_home_away():
    frag, _ = sf('te')
    return jsonify(query(f"""SELECT t.TeamName,se.SeasonName,
        te.HomeWins,te.HomeDraws,te.HomeLosses,te.HomeGoals,
        te.AwayWins,te.AwayDraws,te.AwayLosses,te.AwayGoals,
        te.AvgAttendance,
        ts.Wins,ts.Draws,ts.Loses,ts.Points
        FROM TeamExtendedStats te JOIN Teams t ON te.TeamID=t.TeamID
        JOIN Seasons se ON te.SeasonID=se.SeasonID
        JOIN TeamSeasonStats ts ON ts.TeamID=te.TeamID AND ts.SeasonID=te.SeasonID
        WHERE 1=1 {frag} ORDER BY ts.Points DESC"""))

@app.route('/api/attendance')
def attendance():
    frag, _ = sf('te')
    return jsonify(query(f"""SELECT t.TeamName,se.SeasonName,te.AvgAttendance
        FROM TeamExtendedStats te JOIN Teams t ON te.TeamID=t.TeamID
        JOIN Seasons se ON te.SeasonID=se.SeasonID
        WHERE te.AvgAttendance>0 {frag} ORDER BY te.AvgAttendance DESC"""))

@app.route('/api/possession')
def possession():
    frag, _ = sf('te')
    return jsonify(query(f"""SELECT t.TeamName,se.SeasonName,te.Possession,ts.Points,ts.Goals
        FROM TeamExtendedStats te JOIN Teams t ON te.TeamID=t.TeamID
        JOIN Seasons se ON te.SeasonID=se.SeasonID
        JOIN TeamSeasonStats ts ON ts.TeamID=te.TeamID AND ts.SeasonID=te.SeasonID
        WHERE te.Possession>0 {frag} ORDER BY te.Possession DESC"""))

@app.route('/api/season-compare')
def season_compare():
    return jsonify(query("""SELECT t.TeamName,se.SeasonName,
        ts.Points,ts.Goals,ts.GoalsAgainst,ts.Wins,ROUND(ts.xG,2) AS xG
        FROM TeamSeasonStats ts JOIN Teams t ON ts.TeamID=t.TeamID
        JOIN Seasons se ON ts.SeasonID=se.SeasonID
        ORDER BY se.SeasonID,ts.Points DESC"""))

@app.route('/api/team-season-performance')
def team_season_performance():
    team = request.args.get('team','')
    if not team: return jsonify([])
    return jsonify(query("""SELECT se.SeasonName,ts.Points,ts.Goals,ts.GoalsAgainst,
        ts.Wins,ROUND(ts.xG,2) AS xG,ROUND(ts.xGA,2) AS xGA,
        ISNULL(te.Possession,0) AS Possession,
        ISNULL(te.Shots,0) AS Shots,ISNULL(te.AvgAttendance,0) AS AvgAttendance
        FROM TeamSeasonStats ts JOIN Teams t ON ts.TeamID=t.TeamID
        JOIN Seasons se ON ts.SeasonID=se.SeasonID
        LEFT JOIN TeamExtendedStats te ON te.TeamID=ts.TeamID AND te.SeasonID=ts.SeasonID
        WHERE t.TeamName=? ORDER BY se.SeasonID""", [team]))

@app.route('/api/test')
def test():
    try:
        d = query("SELECT COUNT(*) AS cnt FROM Players")
        return jsonify({"status":"ok","players":d[0]['cnt']})
    except Exception as e:
        return jsonify({"status":"error","message":str(e)})

if __name__ == '__main__':
    print("🚀 PremierStat → http://127.0.0.1:5000")
    app.run(debug=True)
