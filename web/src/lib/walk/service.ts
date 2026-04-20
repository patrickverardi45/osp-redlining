// Walk service adapter.
//
// Intentionally frontend-only for this batch. The interface is shaped to match
// what a future FastAPI walk module will expose (start / end / addEntry / sendHome),
// so when backend walk endpoints ship, the only change is swapping
// `defaultWalkService` from `LocalWalkService` to a `RemoteWalkService`
// implementation in this file. `MobileWalkContainer` does not change.
//
// NOTHING in this file calls fetch(). Do not add network code here without
// first confirming the actual backend route shapes.

import type { MobileWalkAddEntryPayload } from "@/components/MobileWalkUI";

export type WalkSessionSnapshot = {
  id: string;
  status: "active" | "ended";
  entry_count: number;
  started_at: string;
  route_name: string | null;
  route_length_ft: number | null;
  design_snapshot_label: string | null;
};

export type WalkEntrySnapshot = {
  id: string;
  session_id: string;
  sequence: number;
  station_text: string;
  note: string;
  photo_filename: string | null;
  gps_lat: number | null;
  gps_lon: number | null;
  gps_accuracy_m: number | null;
  captured_at: string;
};

export type AddEntryInput = MobileWalkAddEntryPayload & {
  currentGps: { lat: number; lon: number; accuracy_m: number } | null;
};

export interface WalkService {
  /** Look up any existing active session (e.g. after page reload). */
  getActiveSession(): Promise<WalkSessionSnapshot | null>;

  /** Start a new walk session. The preflight context is informational only for the local service. */
  startSession(input: {
    route_name: string | null;
    route_length_ft: number | null;
    design_snapshot_label: string | null;
  }): Promise<WalkSessionSnapshot>;

  /** Persist (or locally record) a new entry on the active session. */
  addEntry(input: AddEntryInput): Promise<WalkEntrySnapshot>;

  /** Mark the active session ended. */
  endSession(): Promise<WalkSessionSnapshot>;

  /** Crew's "wrap up" action. Semantics finalized when backend ships; locally it ends the session if active. */
  sendHome(): Promise<WalkSessionSnapshot | null>;
}

/* ------------------------------------------------------------------ */
/* LocalWalkService — in-memory only, used until backend walk routes  */
/* ship. Persists nothing across page reloads.                         */
/* ------------------------------------------------------------------ */

function makeId(prefix: string): string {
  const rand = Math.random().toString(36).slice(2, 10);
  return `${prefix}_${Date.now().toString(36)}_${rand}`;
}

class LocalWalkService implements WalkService {
  private session: WalkSessionSnapshot | null = null;
  private entries: WalkEntrySnapshot[] = [];

  async getActiveSession(): Promise<WalkSessionSnapshot | null> {
    return this.session;
  }

  async startSession(input: {
    route_name: string | null;
    route_length_ft: number | null;
    design_snapshot_label: string | null;
  }): Promise<WalkSessionSnapshot> {
    this.session = {
      id: makeId("walk"),
      status: "active",
      entry_count: 0,
      started_at: new Date().toISOString(),
      route_name: input.route_name,
      route_length_ft: input.route_length_ft,
      design_snapshot_label: input.design_snapshot_label,
    };
    this.entries = [];
    return this.session;
  }

  async addEntry(input: AddEntryInput): Promise<WalkEntrySnapshot> {
    if (!this.session || this.session.status !== "active") {
      throw new Error("No active walk session.");
    }
    const entry: WalkEntrySnapshot = {
      id: makeId("entry"),
      session_id: this.session.id,
      sequence: this.entries.length + 1,
      station_text: input.stationText,
      note: input.note,
      photo_filename: input.photoFile ? input.photoFile.name : null,
      gps_lat: input.currentGps ? input.currentGps.lat : null,
      gps_lon: input.currentGps ? input.currentGps.lon : null,
      gps_accuracy_m: input.currentGps ? input.currentGps.accuracy_m : null,
      captured_at: new Date().toISOString(),
    };
    this.entries = [...this.entries, entry];
    this.session = { ...this.session, entry_count: this.entries.length };
    return entry;
  }

  async endSession(): Promise<WalkSessionSnapshot> {
    if (!this.session) throw new Error("No walk session to end.");
    this.session = { ...this.session, status: "ended" };
    return this.session;
  }

  async sendHome(): Promise<WalkSessionSnapshot | null> {
    if (!this.session) return null;
    if (this.session.status === "active") {
      this.session = { ...this.session, status: "ended" };
    }
    return this.session;
  }
}

/**
 * Module-scoped default instance. The container imports this; swapping the
 * implementation later is a one-line change here.
 */
export const defaultWalkService: WalkService = new LocalWalkService();
