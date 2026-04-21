// Walk service adapter.
//
// addEntry now posts to the backend connectivity-test endpoint
// POST /api/walk/test-event. The POST is authoritative for this step: if it
// fails (network or non-2xx HTTP), the save fails visibly in the UI and no
// local state is mutated. On success, local session bookkeeping is updated
// so MobileWalkContainer keeps working unchanged.
//
// No real persistence yet. The endpoint just logs the payload and returns
// {"success": true}. This is a smoke test of the network path only.

import type { MobileWalkAddEntryPayload } from "@/components/MobileWalkUI";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") ||
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://127.0.0.1:8000";

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

export type AddEntryResult = {
  entry: WalkEntrySnapshot;
  session: WalkSessionSnapshot;
};

export interface WalkService {
  getActiveSession(): Promise<WalkSessionSnapshot | null>;
  startSession(input: {
    route_name: string | null;
    route_length_ft: number | null;
    design_snapshot_label: string | null;
  }): Promise<WalkSessionSnapshot>;
  addEntry(input: AddEntryInput): Promise<AddEntryResult>;
  endSession(): Promise<WalkSessionSnapshot>;
  sendHome(): Promise<WalkSessionSnapshot | null>;
}

/* ------------------------------------------------------------------ */
/* LocalWalkService — local session bookkeeping only. addEntry performs */
/* a network POST before mutating state; everything else stays local   */
/* until real walk backend routes ship.                                 */
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

  async addEntry(input: AddEntryInput): Promise<AddEntryResult> {
    if (!this.session) {
      throw new Error("No active walk session. Start a walk before adding entries.");
    }
    if (this.session.status !== "active") {
      throw new Error("Walk session is not active. Start a new walk to continue.");
    }

    // Build the POST body. Minimal — matches what the backend test endpoint
    // expects to log: station, optional note, optional gps.
    const body: Record<string, unknown> = {
      station: input.stationText,
    };
    if (input.note && input.note.trim()) {
      body.note = input.note;
    }
    if (input.currentGps) {
      body.gps = {
        lat: input.currentGps.lat,
        lon: input.currentGps.lon,
        accuracy_m: input.currentGps.accuracy_m,
      };
    }

    // POST-first. If the network or HTTP call fails, we throw BEFORE mutating
    // local state. MobileWalkContainer catches and surfaces a toast.
    let response: Response;
    try {
      response = await fetch(`${API_BASE}/api/walk/test-event`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch (err) {
      const reason = err instanceof Error ? err.message : "network error";
      throw new Error(`Failed to reach backend: ${reason}`);
    }

    if (!response.ok) {
      throw new Error(`Backend rejected entry (HTTP ${response.status}).`);
    }

    // Surface any JSON payload the backend returned for debugging, but we
    // don't depend on its shape — the contract is just the 2xx status.
    try {
      const parsed = await response.json();
      if (typeof console !== "undefined" && console.log) {
        console.log("[walk] test-event response:", parsed);
      }
    } catch {
      /* ignore: endpoint contract is HTTP status only */
    }

    // POST succeeded → update local session bookkeeping.
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
    return { entry, session: this.session };
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

export const defaultWalkService: WalkService = new LocalWalkService();
