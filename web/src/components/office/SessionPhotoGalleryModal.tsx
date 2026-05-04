// Reusable session photo gallery modal. Lifted verbatim from
// SessionListPanel.tsx so the same modal can be embedded inside
// /projects/[projectId] (RedlineMap) without users having to leave the
// workspace for /jobs/[jobId].

"use client";

import type { Photo } from "@/lib/api";

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "https://walkv1-backend.onrender.com"
).replace(/\/+$/, "");

function resolvePhotoUrl(photoUrl: string): string {
  if (/^https?:\/\//i.test(photoUrl)) {
    try {
      const parsed = new URL(photoUrl);
      const isLocalhostHost =
        parsed.hostname === "localhost" ||
        parsed.hostname === "127.0.0.1" ||
        parsed.hostname === "0.0.0.0";
      if (isLocalhostHost) {
        const normalizedPath = `${parsed.pathname}${parsed.search}${parsed.hash}`;
        return API_BASE_URL ? `${API_BASE_URL}${normalizedPath}` : normalizedPath;
      }
      return photoUrl;
    } catch {
      return photoUrl;
    }
  }
  const normalizedPath = photoUrl.startsWith("/") ? photoUrl : `/${photoUrl}`;
  return API_BASE_URL ? `${API_BASE_URL}${normalizedPath}` : normalizedPath;
}

function formatTimestamp(ts: string | null): string {
  if (!ts) return "-";
  return new Date(ts).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

export type SessionPhotoGallery =
  | { kind: "list"; photos: Photo[] }
  | { kind: "fallback"; url: string };

export function sortPhotosByUploadedDesc(items: Photo[]): Photo[] {
  return [...items].sort((a, b) => {
    const ta = a.uploaded_at ? new Date(a.uploaded_at).getTime() : NaN;
    const tb = b.uploaded_at ? new Date(b.uploaded_at).getTime() : NaN;
    const na = Number.isFinite(ta) ? ta : 0;
    const nb = Number.isFinite(tb) ? tb : 0;
    return nb - na;
  });
}

type SessionPhotoGalleryModalProps = {
  gallery: SessionPhotoGallery | null;
  onClose: () => void;
};

export default function SessionPhotoGalleryModal({
  gallery,
  onClose,
}: SessionPhotoGalleryModalProps) {
  if (!gallery) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        aria-label="Close gallery"
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Session photos"
        className="relative flex max-h-[90vh] w-full max-w-3xl flex-col rounded-lg bg-white shadow-xl"
      >
        <div className="flex shrink-0 items-center justify-between border-b border-gray-200 px-4 py-3">
          <h3 className="text-sm font-semibold text-gray-900">Photos</h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
          >
            Close
          </button>
        </div>
        <div className="min-h-0 overflow-y-auto p-4">
          {gallery.kind === "list" ? (
            <div className="flex flex-col gap-6">
              {gallery.photos.map((photo) => (
                <div
                  key={photo.id}
                  className="rounded-lg border border-gray-100 bg-gray-50/80 p-3"
                >
                  {photo.thumbnail_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={resolvePhotoUrl(photo.thumbnail_url)}
                      alt=""
                      className="mx-auto max-h-72 w-auto max-w-full rounded-md object-contain"
                    />
                  ) : (
                    <p className="text-xs text-gray-500">No image URL</p>
                  )}
                  {(photo.station_label?.trim() ||
                    photo.note?.trim() ||
                    photo.uploaded_at) && (
                    <dl className="mt-2 space-y-1 text-xs text-gray-600">
                      {photo.station_label?.trim() ? (
                        <div>
                          <dt className="font-medium text-gray-500">Station</dt>
                          <dd>{photo.station_label}</dd>
                        </div>
                      ) : null}
                      {photo.note?.trim() ? (
                        <div>
                          <dt className="font-medium text-gray-500">Note</dt>
                          <dd>{photo.note}</dd>
                        </div>
                      ) : null}
                      {photo.uploaded_at ? (
                        <div>
                          <dt className="font-medium text-gray-500">
                            Uploaded
                          </dt>
                          <dd>{formatTimestamp(photo.uploaded_at)}</dd>
                        </div>
                      ) : null}
                    </dl>
                  )}
                </div>
              ))}
            </div>
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={resolvePhotoUrl(gallery.url)}
              alt=""
              className="mx-auto max-h-[70vh] w-auto max-w-full rounded-md object-contain"
            />
          )}
        </div>
      </div>
    </div>
  );
}
