// web/src/lib/photos/exif.ts
//
// V1 Photo GPS Mapping — EXIF extraction utility.
//
// Pure function. No React, no map, no state. Reads EXIF GPS tags from an
// uploaded image File (JPEG, HEIC/HEIF, and anything else exifr supports) and
// returns a {lat, lon} pair when present, or null otherwise.
//
// - Safe to call for files of any type. On non-image files or images with no
//   GPS tags, it resolves to null (never throws).
// - Normalizes GPS ref tags (N/S/E/W) so returned lat/lon are already signed.
// - Rejects obviously invalid coordinates (NaN, out of globe range, or the
//   0,0 "null island" pair which is almost always junk EXIF, not a real fix).

import exifr from "exifr";

export type PhotoGps = { lat: number; lon: number };

export async function extractGps(file: File): Promise<PhotoGps | null> {
  if (!file) return null;

  // exifr.gps() is the narrow-scope helper: it only parses GPS tags and is
  // cheap on HEIC/large RAW files. It returns { latitude, longitude } or
  // undefined, and already applies the N/S/E/W reference signs.
  let result: { latitude?: number; longitude?: number } | undefined;
  try {
    result = await exifr.gps(file);
  } catch {
    // Bad/unsupported file, corrupted EXIF, etc. Treat as "no GPS available".
    return null;
  }

  if (!result) return null;
  const { latitude, longitude } = result;

  if (typeof latitude !== "number" || typeof longitude !== "number") return null;
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null;
  if (latitude < -90 || latitude > 90) return null;
  if (longitude < -180 || longitude > 180) return null;

  // Null island filter: many cameras/apps write (0, 0) when GPS hasn't locked.
  // Real jobsites at exactly (0, 0) are effectively impossible for this app.
  if (latitude === 0 && longitude === 0) return null;

  return { lat: latitude, lon: longitude };
}
