<script>
  let { page = 'dashboard', onNavigate, connected = false } = $props();

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: 'dashboard' },
    { id: 'history', label: 'History', icon: 'history' },
    { id: 'settings', label: 'Settings', icon: 'settings' },
  ];
</script>

<aside class="w-56 min-w-[224px] bg-[#1a1a1a] border-r border-neutral-800 flex flex-col">
  <nav class="flex-1 py-4 space-y-1 px-3">
    {#each navItems as item}
      <button
        onclick={() => onNavigate(item.id)}
        class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all
          {page === item.id
            ? 'bg-[#252525] text-neutral-100 border-l-2 border-blue-500 pl-2.5'
            : 'text-neutral-400 hover:text-neutral-200 hover:bg-[#252525]/50 border-l-2 border-transparent pl-2.5'
          }"
      >
        {#if item.icon === 'dashboard'}
          <svg class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="7" height="7" rx="1"/>
            <rect x="14" y="3" width="7" height="7" rx="1"/>
            <rect x="3" y="14" width="7" height="7" rx="1"/>
            <rect x="14" y="14" width="7" height="7" rx="1"/>
          </svg>
        {:else if item.icon === 'history'}
          <svg class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 3v5h5"/>
            <path d="M3.05 13A9 9 0 1 0 6 5.3L3 8"/>
            <path d="M12 7v5l4 2"/>
          </svg>
        {:else if item.icon === 'settings'}
          <svg class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
        {/if}
        <span>{item.label}</span>
      </button>
    {/each}
  </nav>

  <!-- Connection status -->
  <div class="px-5 py-4 border-t border-neutral-800">
    <div class="flex items-center gap-2">
      <span class="relative flex h-2 w-2">
        <span class="relative inline-flex rounded-full h-2 w-2 {connected ? 'bg-green-500' : 'bg-red-500'}"></span>
      </span>
      <span class="text-xs text-neutral-500">
        {connected ? 'Connected' : 'Disconnected'}
      </span>
    </div>
  </div>
</aside>
