-- CreateTable
CREATE TABLE "Team" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "name" TEXT NOT NULL,
    "abbreviation" TEXT NOT NULL,
    "city" TEXT NOT NULL,
    "leagueId" INTEGER NOT NULL,
    "divisionId" INTEGER NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL
);

-- CreateTable
CREATE TABLE "Person" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "fullName" TEXT NOT NULL,
    "position" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL
);

-- CreateTable
CREATE TABLE "Venue" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "name" TEXT NOT NULL,
    "city" TEXT NOT NULL,
    "state" TEXT,
    "country" TEXT NOT NULL DEFAULT 'US',
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- CreateTable
CREATE TABLE "Game" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "date" TEXT NOT NULL,
    "startTimeUtc" DATETIME NOT NULL,
    "status" TEXT NOT NULL,
    "homeTeamId" TEXT NOT NULL,
    "awayTeamId" TEXT NOT NULL,
    "venueId" TEXT NOT NULL,
    "season" INTEGER NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "Game_homeTeamId_fkey" FOREIGN KEY ("homeTeamId") REFERENCES "Team" ("id") ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "Game_awayTeamId_fkey" FOREIGN KEY ("awayTeamId") REFERENCES "Team" ("id") ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "Game_venueId_fkey" FOREIGN KEY ("venueId") REFERENCES "Venue" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "SourceObservation" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "gameId" TEXT,
    "provider" TEXT NOT NULL,
    "providerId" TEXT,
    "sourceIdentifier" TEXT,
    "retrievedAt" DATETIME NOT NULL,
    "effectiveAt" DATETIME,
    "season" INTEGER,
    "sourceTimezone" TEXT,
    "rawChecksum" TEXT NOT NULL,
    "normalizedData" TEXT NOT NULL,
    "freshnessState" TEXT NOT NULL,
    "validationWarnings" TEXT NOT NULL DEFAULT '[]',
    "dataType" TEXT NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "SourceObservation_gameId_fkey" FOREIGN KEY ("gameId") REFERENCES "Game" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "ProbableStarterObservation" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "gameId" TEXT NOT NULL,
    "personId" TEXT NOT NULL,
    "side" TEXT NOT NULL,
    "confirmationStatus" TEXT NOT NULL,
    "gamesStarted" INTEGER,
    "roleLabel" TEXT,
    "retrievedAt" DATETIME NOT NULL,
    "sourceProvider" TEXT NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "ProbableStarterObservation_gameId_fkey" FOREIGN KEY ("gameId") REFERENCES "Game" ("id") ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "ProbableStarterObservation_personId_fkey" FOREIGN KEY ("personId") REFERENCES "Person" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "PitcherSnapshot" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "personId" TEXT NOT NULL,
    "season" INTEGER NOT NULL,
    "era" REAL NOT NULL,
    "whip" REAL NOT NULL,
    "inningsPitched" REAL NOT NULL,
    "outsRecorded" INTEGER NOT NULL,
    "gamesStarted" INTEGER NOT NULL,
    "earnedRuns" INTEGER NOT NULL,
    "walks" INTEGER NOT NULL,
    "strikeouts" INTEGER NOT NULL,
    "sourceProvider" TEXT NOT NULL,
    "sourceObservationId" TEXT,
    "retrievedAt" DATETIME NOT NULL,
    "freshnessState" TEXT NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "PitcherSnapshot_personId_fkey" FOREIGN KEY ("personId") REFERENCES "Person" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "PitcherGameLogStart" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "personId" TEXT NOT NULL,
    "gameDate" TEXT NOT NULL,
    "season" INTEGER NOT NULL,
    "earnedRuns" INTEGER NOT NULL,
    "outsRecorded" INTEGER NOT NULL,
    "gameEra" REAL NOT NULL,
    "isGoodStart" BOOLEAN NOT NULL,
    "sourceProvider" TEXT NOT NULL,
    "sourceObservationId" TEXT,
    "retrievedAt" DATETIME NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "PitcherGameLogStart_personId_fkey" FOREIGN KEY ("personId") REFERENCES "Person" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "TeamSnapshot" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "teamId" TEXT NOT NULL,
    "season" INTEGER NOT NULL,
    "avg" REAL NOT NULL,
    "ops" REAL NOT NULL,
    "runsPerGame" REAL NOT NULL,
    "bullpenEra" REAL,
    "bullpenWhip" REAL,
    "wins" INTEGER NOT NULL,
    "losses" INTEGER NOT NULL,
    "last10Wins" INTEGER NOT NULL,
    "last10Losses" INTEGER NOT NULL,
    "currentStreak" INTEGER NOT NULL,
    "sourceProvider" TEXT NOT NULL,
    "sourceObservationId" TEXT,
    "retrievedAt" DATETIME NOT NULL,
    "freshnessState" TEXT NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "TeamSnapshot_teamId_fkey" FOREIGN KEY ("teamId") REFERENCES "Team" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "MarketSnapshot" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "gameId" TEXT NOT NULL,
    "provider" TEXT NOT NULL,
    "retrievedAt" DATETIME NOT NULL,
    "moneylineHome" REAL,
    "moneylineAway" REAL,
    "moneylineHomeOrig" TEXT,
    "moneylineAwayOrig" TEXT,
    "totalLine" REAL,
    "totalOverDecimal" REAL,
    "totalUnderDecimal" REAL,
    "freshnessState" TEXT NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "MarketSnapshot_gameId_fkey" FOREIGN KEY ("gameId") REFERENCES "Game" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "ParkFactorSnapshot" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "venueId" TEXT NOT NULL,
    "season" INTEGER NOT NULL,
    "factor" REAL NOT NULL,
    "source" TEXT NOT NULL,
    "notes" TEXT,
    "isFallback" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "ParkFactorSnapshot_venueId_fkey" FOREIGN KEY ("venueId") REFERENCES "Venue" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "ModelDefinition" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "name" TEXT NOT NULL,
    "version" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- CreateTable
CREATE TABLE "ModelConfigVersion" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "modelId" TEXT NOT NULL,
    "semver" TEXT NOT NULL,
    "configJson" TEXT NOT NULL,
    "isActive" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "createdBy" TEXT NOT NULL DEFAULT 'system',
    CONSTRAINT "ModelConfigVersion_modelId_fkey" FOREIGN KEY ("modelId") REFERENCES "ModelDefinition" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "InputSnapshot" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "gameId" TEXT NOT NULL,
    "frozenAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "pitcherSnapshotAwayId" TEXT,
    "pitcherSnapshotHomeId" TEXT,
    "teamSnapshotAwayId" TEXT,
    "teamSnapshotHomeId" TEXT,
    "marketSnapshotId" TEXT,
    "parkFactorSnapshotId" TEXT,
    "gameLogStartsAway" TEXT NOT NULL DEFAULT '[]',
    "gameLogStartsHome" TEXT NOT NULL DEFAULT '[]',
    "probableStarterAwayId" TEXT,
    "probableStarterHomeId" TEXT,
    "freshnessIssues" TEXT NOT NULL DEFAULT '[]',
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "InputSnapshot_gameId_fkey" FOREIGN KEY ("gameId") REFERENCES "Game" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "ModelRun" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "gameId" TEXT NOT NULL,
    "modelId" TEXT NOT NULL,
    "configVersionId" TEXT NOT NULL,
    "inputSnapshotId" TEXT NOT NULL,
    "runAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "finalState" TEXT NOT NULL,
    "rawScore" REAL,
    "rawGap" REAL,
    "outputJson" TEXT NOT NULL,
    "isLocked" BOOLEAN NOT NULL DEFAULT false,
    "isInvalidated" BOOLEAN NOT NULL DEFAULT false,
    "invalidationReason" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "ModelRun_gameId_fkey" FOREIGN KEY ("gameId") REFERENCES "Game" ("id") ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "ModelRun_modelId_fkey" FOREIGN KEY ("modelId") REFERENCES "ModelDefinition" ("id") ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "ModelRun_configVersionId_fkey" FOREIGN KEY ("configVersionId") REFERENCES "ModelConfigVersion" ("id") ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "ModelRun_inputSnapshotId_fkey" FOREIGN KEY ("inputSnapshotId") REFERENCES "InputSnapshot" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "ModelWarning" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "modelRunId" TEXT NOT NULL,
    "code" TEXT NOT NULL,
    "severity" TEXT NOT NULL,
    "message" TEXT NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "ModelWarning_modelRunId_fkey" FOREIGN KEY ("modelRunId") REFERENCES "ModelRun" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "Forecast" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "modelRunId" TEXT NOT NULL,
    "lockedAt" DATETIME NOT NULL,
    "marketLine" REAL,
    "marketPrice" REAL,
    "selectedSide" TEXT,
    "finalState" TEXT NOT NULL,
    "notes" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Forecast_modelRunId_fkey" FOREIGN KEY ("modelRunId") REFERENCES "ModelRun" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "ForecastRevision" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "forecastId" TEXT NOT NULL,
    "revisedAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "reason" TEXT NOT NULL,
    "oldState" TEXT NOT NULL,
    "newState" TEXT NOT NULL,
    "notes" TEXT,
    CONSTRAINT "ForecastRevision_forecastId_fkey" FOREIGN KEY ("forecastId") REFERENCES "Forecast" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "GameResult" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "gameId" TEXT NOT NULL,
    "homeScore" INTEGER NOT NULL,
    "awayScore" INTEGER NOT NULL,
    "finalStatus" TEXT NOT NULL,
    "officialAt" DATETIME NOT NULL,
    "sourceProvider" TEXT NOT NULL,
    "retrievedAt" DATETIME NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "GameResult_gameId_fkey" FOREIGN KEY ("gameId") REFERENCES "Game" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "Settlement" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "forecastId" TEXT NOT NULL,
    "gameResultId" TEXT NOT NULL,
    "outcome" TEXT NOT NULL,
    "settledAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "gradeNotes" TEXT,
    CONSTRAINT "Settlement_forecastId_fkey" FOREIGN KEY ("forecastId") REFERENCES "Forecast" ("id") ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "Settlement_gameResultId_fkey" FOREIGN KEY ("gameResultId") REFERENCES "GameResult" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

-- CreateIndex
CREATE INDEX "SourceObservation_gameId_dataType_idx" ON "SourceObservation"("gameId", "dataType");

-- CreateIndex
CREATE INDEX "SourceObservation_retrievedAt_idx" ON "SourceObservation"("retrievedAt");

-- CreateIndex
CREATE UNIQUE INDEX "SourceObservation_provider_providerId_rawChecksum_key" ON "SourceObservation"("provider", "providerId", "rawChecksum");

-- CreateIndex
CREATE INDEX "ProbableStarterObservation_gameId_idx" ON "ProbableStarterObservation"("gameId");

-- CreateIndex
CREATE INDEX "PitcherSnapshot_personId_season_idx" ON "PitcherSnapshot"("personId", "season");

-- CreateIndex
CREATE INDEX "PitcherGameLogStart_personId_season_idx" ON "PitcherGameLogStart"("personId", "season");

-- CreateIndex
CREATE INDEX "PitcherGameLogStart_personId_gameDate_idx" ON "PitcherGameLogStart"("personId", "gameDate");

-- CreateIndex
CREATE INDEX "TeamSnapshot_teamId_season_idx" ON "TeamSnapshot"("teamId", "season");

-- CreateIndex
CREATE INDEX "MarketSnapshot_gameId_retrievedAt_idx" ON "MarketSnapshot"("gameId", "retrievedAt");

-- CreateIndex
CREATE UNIQUE INDEX "ParkFactorSnapshot_venueId_season_source_key" ON "ParkFactorSnapshot"("venueId", "season", "source");

-- CreateIndex
CREATE INDEX "ModelConfigVersion_modelId_isActive_idx" ON "ModelConfigVersion"("modelId", "isActive");

-- CreateIndex
CREATE INDEX "InputSnapshot_gameId_idx" ON "InputSnapshot"("gameId");

-- CreateIndex
CREATE INDEX "ModelRun_gameId_modelId_idx" ON "ModelRun"("gameId", "modelId");

-- CreateIndex
CREATE INDEX "ModelRun_runAt_idx" ON "ModelRun"("runAt");

-- CreateIndex
CREATE INDEX "ModelWarning_modelRunId_idx" ON "ModelWarning"("modelRunId");

-- CreateIndex
CREATE INDEX "Forecast_modelRunId_idx" ON "Forecast"("modelRunId");

-- CreateIndex
CREATE INDEX "Forecast_lockedAt_idx" ON "Forecast"("lockedAt");

-- CreateIndex
CREATE INDEX "ForecastRevision_forecastId_idx" ON "ForecastRevision"("forecastId");

-- CreateIndex
CREATE UNIQUE INDEX "GameResult_gameId_key" ON "GameResult"("gameId");

-- CreateIndex
CREATE UNIQUE INDEX "Settlement_forecastId_key" ON "Settlement"("forecastId");
