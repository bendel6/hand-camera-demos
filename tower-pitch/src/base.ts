/** Base URL for runtime-fetched assets (relative builds work on any host or sub-path). */
export const BASE: string = import.meta.env.BASE_URL;
/** Extra suffix for model files on hosts that only serve a fixed list of file types (artifact preview). */
export const MODEL_SUFFIX: string = (import.meta.env.VITE_MODEL_SUFFIX as string | undefined) ?? '';
