<script>
  import { onMount } from 'svelte';
  import TypeBadge from '../components/TypeBadge.svelte';
  import { getHistory } from '../lib/api.js';

  let items = $state([]);
  let query = $state('');
  let activeType = $state('all');
  let loading = $state(false);
  let offset = $state(0);
  let hasMore = $state(true);
  let debounceTimer;

  const typeFilters = ['all', 'meeting', 'memo', 'video', 'call', 'class', 'interview', 'podcast'];
  const PAGE_SIZE = 20;

  async function loadItems(reset = false) {
    if (loading) return;
    loading = true;

    const newOffset = reset ? 0 : offset;
    try {
      const result = await getHistory({
        q: query || undefined,
        type: activeType === 'all' ? undefined : activeType,
        offset: newOffset,
        limit: PAGE_SIZE,
      });

      const newItems = result.items ?? result ?? [];

      if (reset) {
        items = newItems;
        offset = newItems.length;
      } else {
        items = [...items, ...newItems];
        offset = items.length;
      }

      hasMore = newItems.length >= PAGE_SIZE;
    } catch (e) {
      console.error('Failed to load history:', e);
    } finally {
      loading = false;
    }
  }

  function handleSearch(e) {
    query = e.target.value;
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => loadItems(true), 300);
  }

  function handleTypeFilter(type) {
    activeType = type;
    loadItems(true);
  }

  function handleScroll(e) {
    const el = e.target;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 100 && hasMore && !loading) {
      loadItems(false);
    }
  }

  function formatDate(timestamp) {
    if (!timestamp) return '';
    const d = new Date(timestamp);
    const today = new Date();
    if (d.toDateString() === today.toDateString()) return 'Today';
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }

  function formatDuration(seconds) {
    if (!seconds) return '--:--';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  onMount(() => {
    loadItems(true);
  });
</script>

<div class="max-w-3xl mx-auto space-y-5">
  <!-- Header -->
  <h1 class="text-xl font-semibold text-neutral-100">History</h1>

  <!-- Search -->
  <div class="relative">
    <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <circle cx="11" cy="11" r="8"/>
      <path d="M21 21l-4.35-4.35"/>
    </svg>
    <input
      type="text"
      placeholder="Search transcriptions..."
      value={query}
      oninput={handleSearch}
      class="w-full bg-[#1a1a1a] border border-neutral-800 rounded-lg pl-10 pr-4 py-2.5 text-sm text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20 transition-colors"
    />
  </div>

  <!-- Type filter pills -->
  <div class="flex gap-2 flex-wrap">
    {#each typeFilters as type}
      <button
        onclick={() => handleTypeFilter(type)}
        class="px-3 py-1.5 rounded-full text-xs font-medium transition-colors
          {activeType === type
            ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
            : 'bg-[#1a1a1a] text-neutral-400 border border-neutral-800 hover:border-neutral-700 hover:text-neutral-300'
          }"
      >
        {type.charAt(0).toUpperCase() + type.slice(1)}
      </button>
    {/each}
  </div>

  <!-- Items list -->
  <div
    class="space-y-2 max-h-[calc(100vh-280px)] overflow-y-auto pr-1"
    onscroll={handleScroll}
  >
    {#if items.length === 0 && !loading}
      <div class="bg-[#1a1a1a] rounded-xl p-12 text-center">
        <p class="text-sm text-neutral-500">
          {query ? 'No results found' : 'No transcription history yet'}
        </p>
      </div>
    {/if}

    {#each items as item}
      <div class="bg-[#1a1a1a] hover:bg-[#252525] rounded-xl p-4 flex items-center justify-between transition-colors cursor-default">
        <div class="flex items-center gap-3 min-w-0">
          <div class="w-8 h-8 rounded-lg bg-[#252525] flex items-center justify-center shrink-0">
            {#if item.step === 'failed'}
              <svg class="w-4 h-4 text-red-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6"/>
              </svg>
            {:else}
              <svg class="w-4 h-4 text-neutral-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
              </svg>
            {/if}
          </div>
          <div class="min-w-0">
            <p class="text-sm text-neutral-200 truncate">{item.note_name || item.filename}</p>
            <div class="flex items-center gap-2 mt-1">
              {#if item.step === 'failed'}
                <span class="text-xs px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/20">Failed</span>
              {/if}
              <span class="text-xs text-neutral-600">{formatDuration(item.duration_sec)}</span>
            </div>
          </div>
        </div>

        <span class="text-xs text-neutral-600 shrink-0 ml-3">{formatDate(item.updated_at)}</span>
      </div>
    {/each}

    {#if loading}
      <div class="flex justify-center py-4">
        <div class="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
      </div>
    {/if}
  </div>
</div>
