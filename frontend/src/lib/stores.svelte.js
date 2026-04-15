/**
 * Svelte 5 global stores using module-level $state runes.
 */

export const appState = $state({
  /** Current processing job from WebSocket */
  currentJob: null,

  /** Today's completed items */
  todayItems: [],

  /** Whether processing is paused */
  paused: false,

  /** Current page: "dashboard" | "history" | "settings" */
  page: "dashboard",
});
