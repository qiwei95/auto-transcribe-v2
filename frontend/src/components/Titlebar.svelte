<script>
  let { status = 'idle' } = $props();

  let statusColor = $derived(
    status === 'processing' ? 'bg-blue-500' :
    status === 'paused' ? 'bg-yellow-500' :
    'bg-neutral-500'
  );

  let statusLabel = $derived(
    status === 'processing' ? 'Processing' :
    status === 'paused' ? 'Paused' :
    'Idle'
  );

  async function minimize() {
    const { getCurrentWindow } = await import('@tauri-apps/api/window');
    getCurrentWindow().minimize();
  }

  async function toggleMaximize() {
    const { getCurrentWindow } = await import('@tauri-apps/api/window');
    getCurrentWindow().toggleMaximize();
  }

  async function close() {
    const { getCurrentWindow } = await import('@tauri-apps/api/window');
    getCurrentWindow().close();
  }
</script>

<div
  class="h-10 min-h-[40px] bg-[#1a1a1a] flex items-center justify-between px-4 border-b border-neutral-800"
  data-tauri-drag-region
>
  <!-- App name -->
  <div class="flex items-center gap-2 pointer-events-none">
    <div class="w-4 h-4 rounded bg-blue-500 flex items-center justify-center">
      <svg class="w-2.5 h-2.5 text-white" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/>
      </svg>
    </div>
    <span class="text-sm font-medium text-neutral-300">Auto-Transcribe</span>
  </div>

  <!-- Status indicator -->
  <div class="flex items-center gap-2 pointer-events-none">
    <span class="relative flex h-2 w-2">
      {#if status === 'processing'}
        <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
      {/if}
      <span class="relative inline-flex rounded-full h-2 w-2 {statusColor}"></span>
    </span>
    <span class="text-xs text-neutral-400">{statusLabel}</span>
  </div>

  <!-- Window controls -->
  <div class="flex items-center gap-1">
    <button
      onclick={minimize}
      class="w-7 h-7 rounded flex items-center justify-center text-neutral-400 hover:bg-neutral-700 hover:text-neutral-200 transition-colors"
      aria-label="Minimize"
    >
      <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M5 12h14"/>
      </svg>
    </button>
    <button
      onclick={toggleMaximize}
      class="w-7 h-7 rounded flex items-center justify-center text-neutral-400 hover:bg-neutral-700 hover:text-neutral-200 transition-colors"
      aria-label="Maximize"
    >
      <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="4" y="4" width="16" height="16" rx="1"/>
      </svg>
    </button>
    <button
      onclick={close}
      class="w-7 h-7 rounded flex items-center justify-center text-neutral-400 hover:bg-red-500/80 hover:text-white transition-colors"
      aria-label="Close"
    >
      <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M6 6l12 12M6 18L18 6"/>
      </svg>
    </button>
  </div>
</div>
