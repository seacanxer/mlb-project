CREATE TABLE "AiFinalPick" (
    "id" TEXT NOT NULL,
    "slateDateWib" TEXT NOT NULL,
    "gameId" TEXT NOT NULL,
    "market" TEXT NOT NULL,
    "selection" TEXT NOT NULL,
    "marketLine" DOUBLE PRECISION,
    "decimalOdds" DOUBLE PRECISION,
    "classification" TEXT NOT NULL,
    "frameworkState" TEXT NOT NULL,
    "frameworkScore" DOUBLE PRECISION,
    "aiModel" TEXT NOT NULL,
    "aiRating" INTEGER NOT NULL,
    "aiVerdict" TEXT NOT NULL,
    "rationale" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "profitUnits" DOUBLE PRECISION,
    "settledAt" TIMESTAMP(3),
    "settlementNote" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "AiFinalPick_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "AiFinalPick_slateDateWib_gameId_key" ON "AiFinalPick"("slateDateWib", "gameId");
CREATE INDEX "AiFinalPick_slateDateWib_idx" ON "AiFinalPick"("slateDateWib");
CREATE INDEX "AiFinalPick_status_idx" ON "AiFinalPick"("status");
ALTER TABLE "AiFinalPick" ADD CONSTRAINT "AiFinalPick_gameId_fkey" FOREIGN KEY ("gameId") REFERENCES "Game"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
