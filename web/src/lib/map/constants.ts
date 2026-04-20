// Projection, zoom, and label-threshold constants for the map canvas.
// Moved verbatim from components/RedlineMap.tsx as part of Phase 1 extraction.
// Changing any value here will change map behavior — treat as stable config.

export const PROJECTION_BASE_WIDTH = 1000;
export const MAP_HEIGHT = 620;
export const MIN_ZOOM = 1;
export const MAX_ZOOM = 300;
export const FIT_PADDING = 36;
export const WHEEL_IN = 1.18;
export const WHEEL_OUT = 0.85;
export const BUTTON_IN = 1.22;
export const BUTTON_OUT = 1 / BUTTON_IN;
export const LOW_ZOOM_LABEL_THRESHOLD = 6;
export const MID_ZOOM_LABEL_THRESHOLD = 16;
