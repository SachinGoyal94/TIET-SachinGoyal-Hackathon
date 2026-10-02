/** Shared API types — kept in sync with src/engine/api/schemas.py. */

export interface Health {
  status: "ok" | "initializing";
  version: string;
  ready: boolean;
  models_loaded: boolean;
  components: {
    risk_engine: boolean;
    rebalancer_module: boolean;
    stress_testing_module: boolean;
  };
}

export const EVENT_LABELS = [
  "Geopolitical",
  "Macroeconomic",
  "Credit Event",
  "Merger/Acquisition",
  "Product Launch",
  "Other",
] as const;

export type EventLabel = (typeof EVENT_LABELS)[number];
