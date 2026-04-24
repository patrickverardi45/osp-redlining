"use client";

import type { CurrentGps } from "@/components/MobileWalkUI";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") ||
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://127.0.0.1:8000";

export type StartSessionInput = {
  route_name: string | null;
  route_length_ft: number | null;
  design_snapshot_label: string;
};

export type AddEntryInput = {
  stationText: string;
  note: string;
  photoFile: File | null;
  currentGps: CurrentGps | null;
};

export type WalkEntrySnapshot = {
  sequence: number;
  station_text: string;
  note: string;
  photo_name: string | null;
  lat: number | null;
  lon: number | null;
  accuracy_m: number | null;
  created_at: string;
};

export type WalkSessionStatus = "active" | "ended" | "sent_home";

export type WalkSessionSnapshot = {
  id: string;
  status: WalkSessionStatus;
  route_name: string | null;
  route_length_ft: number | null;
  design_snapshot_label: string;
  started_at: string;
  ended_at: string | null;
  sent_home_at: string | null;
  entry_count: number;
  entries: WalkEntrySnapshot[];
};

export type AddEntryResult = {
  entry: WalkEntrySnapshot;
  session: WalkSessionSnapshot;
};

export interface WalkService {
  getActiveSession(): Promise<WalkSessionSnapshot | null>;
  startSession(input: StartSessionInput): Promise<WalkSessionSnapshot>;
  addEntry(input: AddEntryInput): Promise<AddEntryResult>;
  endSession(): Promise<WalkSessionSnapshot>;
  sendHome(): Promise<WalkSessionSnapshot>;
}

function nowIso(): string {
  return new Date().toISOString();
}

function cloneSession(session: WalkSessionSnapshot | null): WalkSessionSnapshot | null {
  if (!session) return null;
  return {
    ...session,
    entries: session.entries.map((entry) => ({ ...entry })),
  };
}

function stationIdentityPart(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "";
  return String(value).trim();
}

function buildStationIdentity(params: {
  routeName: string | null;
  sourceFile: string;
  stationLabel: string;
  mappedStationFt: string;
  lat: string;
  lon: string;
}): string {
  return [
    stationIdentityPart(params.routeName),
    stationIdentityPart(params.sourceFile),
    stationIdentityPart(params.stationLabel),
    stationIdentityPart(params.mappedStationFt),
    stationIdentityPart(params.lat),
    stationIdentityPart(params.lon),
  ].join("|");
}

class InMemoryWalkService implements WalkService {
  private activeSession: WalkSessionSnapshot | null = null;
  private nextSequence = 1;

  async getActiveSession(): Promise<WalkSessionSnapshot | null> {
    return cloneSession(this.activeSession);
  }

  async startSession(input: StartSessionInput): Promise<WalkSessionSnapshot> {
    const startedAt = nowIso();

    this.activeSession = {
      id: `walk_${Date.now()}`,
      status: "active",
      route_name: input.route_name ?? null,
      route_length_ft: input.route_length_ft ?? null,
      design_snapshot_label: input.design_snapshot_label,
      started_at: startedAt,
      ended_at: null,
      sent_home_at: null,
      entry_count: 0,
      entries: [],
    };

    this.nextSequence = 1;

    return cloneSession(this.activeSession)!;
  }

  async addEntry(input: AddEntryInput): Promise<AddEntryResult> {
    if (!this.activeSession || this.activeSession.status !== "active") {
      throw new Error("No active walk session.");
    }

    const entry: WalkEntrySnapshot = {
      sequence: this.nextSequence++,
      station_text: input.stationText.trim(),
      note: input.note ?? "",
      photo_name: input.photoFile?.name ?? null,
      lat: input.currentGps?.lat ?? null,
      lon: input.currentGps?.lon ?? null,
      accuracy_m: input.currentGps?.accuracy_m ?? null,
      created_at: nowIso(),
    };

    this.activeSession = {
      ...this.activeSession,
      entry_count: this.activeSession.entry_count + 1,
      entries: [...this.activeSession.entries, entry],
    };

    if (input.photoFile) {
      const routeName = this.activeSession.route_name || "";
      const sourceFile = this.activeSession.design_snapshot_label || "";
      const stationLabel = input.stationText.trim();
      const mappedStationFt = "";
      const lat =
        input.currentGps && Number.isFinite(input.currentGps.lat)
          ? String(input.currentGps.lat)
          : "";
      const lon =
        input.currentGps && Number.isFinite(input.currentGps.lon)
          ? String(input.currentGps.lon)
          : "";

      const stationIdentity = buildStationIdentity({
        routeName,
        sourceFile,
        stationLabel,
        mappedStationFt,
        lat,
        lon,
      });

      const form = new FormData();
      form.append("station_identity", stationIdentity);
      form.append("station_summary", stationLabel);
      form.append("route_name", routeName);
      form.append("source_file", sourceFile);
      form.append("station_label", stationLabel);
      form.append("mapped_station_ft", mappedStationFt);
      form.append("lat", lat);
      form.append("lon", lon);
      form.append("files", input.photoFile);

      const uploadUrl = `${API_BASE}/api/station-photos/upload`;
      if (typeof console !== "undefined" && console.log) {
        console.log("[walk] uploading station photo", {
          url: uploadUrl,
          stationIdentity,
          fileName: input.photoFile.name,
        });
      }

      const uploadResponse = await fetch(uploadUrl, {
        method: "POST",
        body: form,
      });
      const uploadData = await uploadResponse.json();

      if (typeof console !== "undefined" && console.log) {
        console.log("[walk] station photo upload response", {
          status: uploadResponse.status,
          ok: uploadResponse.ok,
          success: uploadData?.success,
        });
      }

      if (!uploadResponse.ok || uploadData?.success === false) {
        throw new Error(uploadData?.error || "Station photo upload failed.");
      }
    }

    return {
      entry: { ...entry },
      session: cloneSession(this.activeSession)!,
    };
  }

  async endSession(): Promise<WalkSessionSnapshot> {
    if (!this.activeSession) {
      throw new Error("No active walk session.");
    }

    this.activeSession = {
      ...this.activeSession,
      status: "ended",
      ended_at: nowIso(),
    };

    return cloneSession(this.activeSession)!;
  }

  async sendHome(): Promise<WalkSessionSnapshot> {
    if (!this.activeSession) {
      throw new Error("No active walk session.");
    }

    this.activeSession = {
      ...this.activeSession,
      status: "sent_home",
      sent_home_at: nowIso(),
    };

    return cloneSession(this.activeSession)!;
  }
}

export const defaultWalkService: WalkService = new InMemoryWalkService();