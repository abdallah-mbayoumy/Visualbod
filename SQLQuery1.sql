USE master;
GO

ALTER DATABASE PremierLeagueDB
SET SINGLE_USER
WITH ROLLBACK IMMEDIATE;
GO

DROP DATABASE PremierLeagueDB;
GO

CREATE DATABASE PremierLeagueDB;
GO

USE PremierLeagueDB;
GO

CREATE TABLE Seasons (
    SeasonID INT IDENTITY(1,1) PRIMARY KEY,
    SeasonName VARCHAR(20)
);

CREATE TABLE Teams (
    TeamID INT IDENTITY(1,1) PRIMARY KEY,
    TeamName VARCHAR(100)
);

CREATE TABLE Players (
    PlayerID INT IDENTITY(1,1) PRIMARY KEY,
    PlayerName VARCHAR(100),
    TeamID INT,
    FOREIGN KEY (TeamID) REFERENCES Teams(TeamID)
);

CREATE TABLE PlayerStats (
    StatID INT IDENTITY(1,1) PRIMARY KEY,
    PlayerID INT,
    SeasonID INT,
    Apps INT,
    Minutes INT,
    Goals INT,
    Assists INT,
    xG FLOAT,
    xA FLOAT,
    xG90 FLOAT,
    xA90 FLOAT,
    FOREIGN KEY (PlayerID) REFERENCES Players(PlayerID),
    FOREIGN KEY (SeasonID) REFERENCES Seasons(SeasonID)
);

DELETE FROM PlayerStats;
DELETE FROM Players;
DELETE FROM Teams;

SELECT COUNT(*) FROM Players;
SELECT COUNT(*) FROM PlayerStats;
SELECT COUNT(*) FROM Teams;
