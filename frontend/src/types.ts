// The shapes of the data the API sends and receives.
// TypeScript checks at build time that the code uses these fields correctly
// (e.g. a typo like site.clientname is a compile error, not a runtime bug).

export interface SiteInput {
  clientName: string;
  address: string;
  latitude: number;
  longitude: number;
  roofAreaM2: number | null; // optional in the contract
  peakKwp: number;
}

// A site is the input fields plus id (as the contract says).
export interface Site extends SiteInput {
  id: number;
}

export interface Production {
  yearlyKwh: number;
  monthlyKwh: { month: number; kwh: number }[];
}

export interface BatteryScenario {
  selfUsedKwh: number;
  gridImportKwh: number;
  gridExportKwh: number;
  selfConsumptionPercent: number;
  selfSufficiencyPercent: number;
}

export interface BatteryResult {
  productionKwh: number;
  consumptionKwh: number;
  capacityKwh: number;
  year: number;
  withoutBattery: BatteryScenario;
  withBattery: BatteryScenario;
  batteryAddsKwh: number;
}
