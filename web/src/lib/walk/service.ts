"use client";

import type { CurrentGps } from "@/components/MobileWalkUI";

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