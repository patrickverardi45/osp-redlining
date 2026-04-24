"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { BackendState } from "@/lib/types/backend";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") ||
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://127.0.0.1:8000";

interface DesignSetupPanelProps {
  onMutated?: () => void | Promise<void>;
}

export default function DesignSetupPanel({ onMutated }: DesignSetupPanelProps) {
  const [state, setState] = useState<BackendState | null>(null);
  const [loadingState, setLoadingState] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [confirmingRoute, setConfirmingRoute] = useState(false);
  const [statusMessage, setStatusMessage] = useState("Loading current design state...");
  const [statusTone, setStatusTone] = useState<"neutral" | "success" | "warning" | "error">("neutral");

  const hasDesign = useMemo(() => {
    const lineCount = state?.kmz_reference?.line_features?.length || 0;
    const polyCount = state?.kmz_reference?.polygon_features?.length || 0;
    return lineCount + polyCount > 0;
  }, [state]);

  const hasRoute = Boolean((state?.selected_route_name || state?.route_name || "").trim());
  const suggestedRouteId = (state?.suggested_route_id || "").trim();

  const fetchCurrentState = useCallback(
    async (message?: string) => {
      setLoadingState(true);
      if (message) {
        setStatusMessage(message);
        setStatusTone("neutral");
      }
      try {
        const response = await fetch(`${API_BASE}/api/current-state`, { cache: "no-store" });
        const data: BackendState = await response.json();
        if (!response.ok || data.success === false) {
          throw new Error(data.error || "Unable to load current design state.");
        }
        setState(data);

        if (data.warning) {
          setStatusMessage(String(data.warning));
          setStatusTone("warning");
        } else if (data.message) {
          setStatusMessage(String(data.message));
          setStatusTone("success");
        } else {
          setStatusMessage("Current design state loaded.");
          setStatusTone("success");
        }
      } catch (error) {
        setStatusMessage(error instanceof Error ? error.message : "Unable to load current design state.");
        setStatusTone("error");
      } finally {
        setLoadingState(false);
      }
    },
    []
  );

  useEffect(() => {
    fetchCurrentState();
  }, [fetchCurrentState]);

  const handleDesignUpload = useCallback(
    async (file: File) => {
      setUploading(true);
      setStatusMessage(`Uploading design: ${file.name}`);
      setStatusTone("neutral");
      try {
        const form = new FormData();
        form.append("file", file);

        const response = await fetch(`${API_BASE}/api/upload-design`, {
          method: "POST",
          body: form,
        });
        const data: BackendState = await response.json();
        if (!response.ok || data.success === false) {
          throw new Error(data.error || "Design upload failed.");
        }

        await fetchCurrentState(data.message || "Design uploaded. Refreshing state...");
        await onMutated?.();
      } catch (error) {
        setStatusMessage(error instanceof Error ? error.message : "Design upload failed.");
        setStatusTone("error");
      } finally {
        setUploading(false);
      }
    },
    [fetchCurrentState, onMutated]
  );

  const handleConfirmActiveRoute = useCallback(async () => {
    if (!suggestedRouteId) return;
    setConfirmingRoute(true);
    setStatusMessage("Confirming active route...");
    setStatusTone("neutral");
    try {
      const form = new FormData();
      form.append("route_id", suggestedRouteId);
      const response = await fetch(`${API_BASE}/api/select-active-route`, {
        method: "POST",
        body: form,
      });
      const data: BackendState = await response.json();
      if (!response.ok || data.success === false) {
        throw new Error(data.error || "Unable to confirm active route.");
      }

      await fetchCurrentState(data.message || "Active route updated.");
      await onMutated?.();
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Unable to confirm active route.");
      setStatusTone("error");
    } finally {
      setConfirmingRoute(false);
    }
  }, [suggestedRouteId, fetchCurrentState, onMutated]);

  return (
    <section>
      <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
        <div>
          <h2 className="text-base font-semibold text-gray-800">Design / KMZ Setup</h2>
          <p className="text-sm text-gray-500 mt-1">
            Upload design, refresh backend route context, and confirm active route.
          </p>
        </div>
        <button
          onClick={() => fetchCurrentState("Refreshing current design state...")}
          disabled={loadingState || uploading || confirmingRoute}
          className="px-3 py-1.5 rounded text-sm font-medium bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-60"
        >
          Refresh State
        </button>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-4 space-y-4">
        <div
          className={`rounded-md border px-3 py-2 text-sm ${
            statusTone === "success"
              ? "bg-green-50 border-green-200 text-green-700"
              : statusTone === "warning"
              ? "bg-yellow-50 border-yellow-200 text-yellow-800"
              : statusTone === "error"
              ? "bg-red-50 border-red-200 text-red-700"
              : "bg-gray-50 border-gray-200 text-gray-700"
          }`}
        >
          {statusMessage}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
          <div className="rounded-md border border-gray-200 bg-gray-50 px-3 py-2">
            <span className="text-gray-500">Design loaded:</span>{" "}
            <span className="font-medium text-gray-800">{hasDesign ? "Yes" : "No"}</span>
          </div>
          <div className="rounded-md border border-gray-200 bg-gray-50 px-3 py-2">
            <span className="text-gray-500">Active route:</span>{" "}
            <span className="font-medium text-gray-800">{state?.selected_route_name || state?.route_name || "—"}</span>
          </div>
          <div className="rounded-md border border-gray-200 bg-gray-50 px-3 py-2">
            <span className="text-gray-500">Suggested route id:</span>{" "}
            <span className="font-medium text-gray-800">{suggestedRouteId || "—"}</span>
          </div>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <label className="inline-flex items-center">
            <input
              type="file"
              accept=".kmz,.kml"
              className="hidden"
              disabled={uploading || loadingState || confirmingRoute}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) {
                  handleDesignUpload(file);
                }
                e.currentTarget.value = "";
              }}
            />
            <span className="px-3 py-1.5 rounded text-sm font-medium bg-gray-800 text-white hover:bg-gray-700 cursor-pointer">
              {uploading ? "Uploading..." : "Upload KMZ Design"}
            </span>
          </label>

          <button
            onClick={handleConfirmActiveRoute}
            disabled={!suggestedRouteId || confirmingRoute || loadingState || uploading}
            className="px-3 py-1.5 rounded text-sm font-medium bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            {confirmingRoute ? "Confirming..." : "Confirm Active Route"}
          </button>

          {!hasRoute && (
            <span className="text-xs text-gray-500">
              No active route selected yet.
            </span>
          )}
        </div>
      </div>
    </section>
  );
}
