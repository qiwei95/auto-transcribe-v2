<script>
  import DropZone from '../components/DropZone.svelte';
  import ProcessingCard from '../components/ProcessingCard.svelte';
  import TypeBadge from '../components/TypeBadge.svelte';
  import { uploadFile } from '../lib/api.js';

  let { currentJob = null, todayItems = [], paused = false, wsConnected = false } = $props();

  async function handleUpload(file) {
    try {
      await uploadFile(file);
    } catch (e) {
      console.error('Upload failed:', e);
    }
  }

  function formatDuration(seconds) {
    if (!seconds) return '--:--';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  function formatTime(timestamp) {
    if (!timestamp) return '';
    const d = new Date(timestamp);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
</script>

<div class="max-w-3xl mx-auto space-y-6">
  <!-- Header -->
  <div class="flex items-center justify-between">
    <h1 class="text-xl font-semibold text-neutral-100">Dashboard</h1>
    {#if paused}
      <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-yellow-500/10 text-yellow-400 text-xs font-medium border border-yellow-500/20">
        <span class="w-1.5 h-1.5 rounded-full bg-yellow-400"></span>
        Paused
      </span>
    {/if}
  </div>

  <!-- Drop zone -->
  <DropZone onUpload={handleUpload} />

  <!-- Processing card -->
  {#if currentJob}
    <ProcessingCard job={currentJob} />
  {/if}

  <!-- Today's completed -->
  <div>
    <h2 class="text-sm font-medium text-neutral-400 mb-3">Today's Completed</h2>

    {#if todayItems.length === 0}
      <div class="bg-[#1a1a1a] rounded-xl p-8 text-center">
        <p class="text-sm text-neutral-500">No transcriptions completed today</p>
      </div>
    {:else}
      <div class="space-y-2">
        {#each todayItems as item}
          <button
            type="button"
            class="w-full bg-[#1a1a1a] hover:bg-[#252525] rounded-xl p-4 flex items-center justify-between transition-colors group text-left"
          >
            <div class="flex items-center gap-3 min-w-0">
              <div class="w-8 h-8 rounded-lg bg-[#252525] group-hover:bg-[#303030] flex items-center justify-center shrink-0">
                <svg class="w-4 h-4 text-neutral-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
                </svg>
              </div>
              <div class="min-w-0">
                <p class="text-sm text-neutral-200 truncate">{item.title ?? item.filename}</p>
                <div class="flex items-center gap-2 mt-1">
                  {#if item.scene}
                    <TypeBadge type={item.scene} />
                  {/if}
                  <span class="text-xs text-neutral-600">{formatDuration(item.duration)}</span>
                </div>
              </div>
            </div>

            <span class="text-xs text-neutral-600 shrink-0 ml-3">{formatTime(item.completed_at)}</span>
          </button>
        {/each}
      </div>
    {/if}
  </div>
</div>
