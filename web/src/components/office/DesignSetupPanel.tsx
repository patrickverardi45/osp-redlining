"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { BackendState } from "@/lib/types/backend";
import { acceptSessionFromMutation, appendSessionIdReadOnly, appendSessionIdToForm } from "@/lib/session";
import { apiFetch } from "@/lib/apiFetch";

const API_BASE = "";

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
  // Engineering Plan PDF lane — separate from KMZ upload (diagnostic/signals only).
  const [uploadingPdf, setUploadingPdf] = useState(false);
  const [pdfStatusMessage, setPdfStatusMessage] = useState<string>("");
  const [pdfStatusTone, setPdfStatusTone] = useState<"neutral" | "success" | "warning" | "error">("neutral");
  // Bore-log (field data) lane — structured field/billable truth. Wired to the
  // existing /api/upload-structured-bore-files route; frontend-only, no backend change.
  const [uploadingBore, setUploadingBore] = useState(false);
  const [boreStatusMessage, setBoreStatusMessage] = useState<string>("");
  const [boreStatusTone, setBoreStatusTone] = useState<"neutral" | "success" | "warning" | "error">("neutral");

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
        const response = await apiFetch(appendSessionIdReadOnly(`${API_BASE}/api/current-state`), { cache: "no-store" });
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
        appendSessionIdToForm(form);

        const response = await apiFetch(`${API_BASE}/api/upload-design`, {
          method: "POST",
          body: form,
        });
        const data: BackendState = await response.json();
        acceptSessionFromMutation(data);
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

  const handleEngineeringPlanUpload = useCallback(
    async (files: FileList) => {
      // Filter client-side to PDFs only. Defense-in-depth: the backend already
      // rejects non-allowed extensions, but the UI lane is declared PDF-only.
      const pdfFiles: File[] = [];
      const dropped: string[] = [];
      for (let i = 0; i < files.length; i += 1) {
        const f = files.item(i);
        if (!f) continue;
        const isPdf =
          f.type === "application/pdf" ||
          f.name.toLowerCase().endsWith(".pdf");
        if (isPdf) {
          pdfFiles.push(f);
        } else {
          dropped.push(f.name);
        }
      }

      if (pdfFiles.length === 0) {
        setPdfStatusMessage(
          dropped.length > 0
            ? `No PDF files selected (skipped ${dropped.length} non-PDF file${dropped.length === 1 ? "" : "s"}).`
            : "No files selected."
        );
        setPdfStatusTone("warning");
        return;
      }

      setUploadingPdf(true);
      setPdfStatusMessage(
        `Uploading ${pdfFiles.length} engineering plan PDF${pdfFiles.length === 1 ? "" : "s"}...`
      );
      setPdfStatusTone("neutral");
      try {
        const form = new FormData();
        for (const f of pdfFiles) {
          form.append("files", f);
        }
        appendSessionIdToForm(form);

        const response = await apiFetch(`${API_BASE}/api/upload-engineering-plans`, {
          method: "POST",
          body: form,
        });
        const data = await response.json();
        acceptSessionFromMutation(data);
        if (!response.ok || data.success === false) {
          throw new Error(data.error || "Engineering plan upload failed.");
        }

        const skippedNote =
          dropped.length > 0
            ? ` (skipped ${dropped.length} non-PDF file${dropped.length === 1 ? "" : "s"})`
            : "";
        setPdfStatusMessage(
          (data.message || `Uploaded ${pdfFiles.length} engineering plan PDF${pdfFiles.length === 1 ? "" : "s"}.`) +
            skippedNote
        );
        setPdfStatusTone("success");

        await fetchCurrentState();
        await onMutated?.();
      } catch (error) {
        setPdfStatusMessage(
          error instanceof Error ? error.message : "Engineering plan upload failed."
        );
        setPdfStatusTone("error");
      } finally {
        setUploadingPdf(false);
      }
    },
    [fetchCurrentState, onMutated]
  );

  const handleBoreLogUpload = useCallback(
    async (files: FileList) => {
      if (!files || files.length === 0) return;
      setUploadingBore(true);
      setBoreStatusMessage(
        `Uploading ${files.length} bore-log file${files.length === 1 ? "" : "s"}...`
      );
      setBoreStatusTone("neutral");
      try {
        const form = new FormData();
        for (let i = 0; i < files.length; i += 1) {
          const f = files.item(i);
          if (f) form.append("files", f);
        }
        appendSessionIdToForm(form);

        const response = await apiFetch(`${API_BASE}/api/upload-structured-bore-files`, {
          method: "POST",
          body: form,
        });
        const data: BackendState = await response.json();
        acceptSessionFromMutation(data);
        if (!response.ok || data.success === false) {
          throw new Error(data.error || "Bore-log upload failed.");
        }

        setBoreStatusMessage(
          String(
            data.warning ||
              data.message ||
              `Uploaded ${files.length} bore-log file${files.length === 1 ? "" : "s"}.`
          )
        );
        setBoreStatusTone(data.warning ? "warning" : "success");

        await fetchCurrentState();
        await onMutated?.();
      } catch (error) {
        setBoreStatusMessage(error instanceof Error ? error.message : "Bore-log upload failed.");
        setBoreStatusTone("error");
      } finally {
        setUploadingBore(false);
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
        appendSessionIdToForm(form);
      const response = await apiFetch(`${API_BASE}/api/select-active-route`, {
        method: "POST",
        body: form,
      });
      const data: BackendState = await response.json();
        acceptSessionFromMutation(data);
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
          <h2 className="text-base font-semibold text-gray-800">Project Inputs</h2>
          <p className="text-sm text-gray-500 mt-1">
            Upload engineering plan PDFs, KMZ design, and bore-log field data for this job.
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

        {/*
          Lane order: engineering plan PDFs, then KMZ design, then bore-log
          field data. Order is presentation only — the lanes are independent,
          not a required sequence.

          Engineering Plan PDF lane — separate from KMZ design upload.
          Engineering PDFs are diagnostic/signal-only and never feed route
          matching or redline truth. Backend route /api/upload-engineering-plans
          enforces session ownership via the protected router.
        */}
        <div>
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div>
              <h3 className="text-sm font-semibold text-gray-800">Engineering Plan PDFs</h3>
              <p className="text-xs text-gray-500 mt-1">
                Engineering PDFs are parsed for diagnostics/signals only.
              </p>
            </div>
            <label className="inline-flex items-center">
              <input
                type="file"
                accept=".pdf,application/pdf"
                multiple
                className="hidden"
                disabled={uploadingPdf || loadingState || uploading || confirmingRoute || uploadingBore}
                onChange={(e) => {
                  const files = e.target.files;
                  if (files && files.length > 0) {
                    handleEngineeringPlanUpload(files);
                  }
                  e.currentTarget.value = "";
                }}
              />
              <span className="px-3 py-1.5 rounded text-sm font-medium bg-gray-800 text-white hover:bg-gray-700 cursor-pointer">
                {uploadingPdf ? "Uploading..." : "Upload Engineering Plan PDFs"}
              </span>
            </label>
          </div>

          {pdfStatusMessage && (
            <div
              className={`mt-3 rounded-md border px-3 py-2 text-xs ${
                pdfStatusTone === "success"
                  ? "bg-green-50 border-green-200 text-green-700"
                  : pdfStatusTone === "warning"
                  ? "bg-yellow-50 border-yellow-200 text-yellow-800"
                  : pdfStatusTone === "error"
                  ? "bg-red-50 border-red-200 text-red-700"
                  : "bg-gray-50 border-gray-200 text-gray-700"
              }`}
            >
              {pdfStatusMessage}
            </div>
          )}

          {(state?.engineering_plans?.length ?? 0) > 0 && (
            <ul className="mt-3 space-y-1 text-xs text-gray-700">
              {state!.engineering_plans!.map((p) => (
                <li
                  key={p.plan_id}
                  className="flex items-center justify-between rounded border border-gray-100 bg-gray-50 px-2 py-1 gap-2"
                >
                  <span className="truncate">{p.original_filename}</span>
                  <span className="text-gray-500 whitespace-nowrap">
                    {Math.max(1, Math.round(p.size_bytes / 1024))} KB · {new Date(p.uploaded_at).toLocaleString()}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* KMZ design upload + active-route confirmation (second lane). */}
        <div className="border-t border-gray-100 pt-4">
          <h3 className="text-sm font-semibold text-gray-800 mb-3">KMZ Design</h3>
          <div className="flex items-center gap-3 flex-wrap">
            <label className="inline-flex items-center">
              <input
                type="file"
                accept=".kmz,.kml"
                className="hidden"
                disabled={uploading || loadingState || confirmingRoute || uploadingBore}
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

        {/*
          Bore-log (field data) lane — third. Structured bore-log files are the
          actual field/billable truth. Wired to the existing
          /api/upload-structured-bore-files route; frontend-only, no backend change.
        */}
        <div className="border-t border-gray-100 pt-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div>
              <h3 className="text-sm font-semibold text-gray-800">Bore Logs (Field Data)</h3>
              <p className="text-xs text-gray-500 mt-1">
                Structured bore-log files (.xlsx, .xls, .csv) — actual field/billable truth.
              </p>
            </div>
            <label className="inline-flex items-center">
              <input
                type="file"
                accept=".xlsx,.xls,.csv"
                multiple
                className="hidden"
                disabled={uploadingBore || loadingState || uploading || confirmingRoute || uploadingPdf}
                onChange={(e) => {
                  const files = e.target.files;
                  if (files && files.length > 0) {
                    handleBoreLogUpload(files);
                  }
                  e.currentTarget.value = "";
                }}
              />
              <span className="px-3 py-1.5 rounded text-sm font-medium bg-gray-800 text-white hover:bg-gray-700 cursor-pointer">
                {uploadingBore ? "Uploading..." : "Upload Bore Logs"}
              </span>
            </label>
          </div>

          {boreStatusMessage && (
            <div
              className={`mt-3 rounded-md border px-3 py-2 text-xs ${
                boreStatusTone === "success"
                  ? "bg-green-50 border-green-200 text-green-700"
                  : boreStatusTone === "warning"
                  ? "bg-yellow-50 border-yellow-200 text-yellow-800"
                  : boreStatusTone === "error"
                  ? "bg-red-50 border-red-200 text-red-700"
                  : "bg-gray-50 border-gray-200 text-gray-700"
              }`}
            >
              {boreStatusMessage}
            </div>
          )}

          {(state?.loaded_field_data_files ?? 0) > 0 && (
            <p className="mt-3 text-xs font-medium text-green-700">
              {state?.loaded_field_data_files} field data file(s) loaded.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
