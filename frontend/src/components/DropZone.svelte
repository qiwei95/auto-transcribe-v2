<script>
  let { onUpload } = $props();

  let dragover = $state(false);
  let uploading = $state(false);
  let dragCount = $state(0);
  let fileInput;

  function handleDragEnter(e) {
    e.preventDefault();
    dragCount++;
    dragover = true;
  }

  function handleDragLeave(e) {
    e.preventDefault();
    dragCount--;
    if (dragCount <= 0) {
      dragover = false;
      dragCount = 0;
    }
  }

  function handleDragOver(e) {
    e.preventDefault();
  }

  async function handleDrop(e) {
    e.preventDefault();
    dragover = false;
    dragCount = 0;

    const files = Array.from(e.dataTransfer.files).filter(f =>
      f.type.startsWith('audio/') || f.type.startsWith('video/')
    );

    if (files.length === 0) return;

    uploading = true;
    try {
      for (const file of files) {
        await onUpload(file);
      }
    } finally {
      uploading = false;
    }
  }

  function handleClick() {
    fileInput?.click();
  }

  async function handleFileSelect(e) {
    const files = Array.from(e.target.files);
    if (files.length === 0) return;

    uploading = true;
    try {
      for (const file of files) {
        await onUpload(file);
      }
    } finally {
      uploading = false;
      e.target.value = '';
    }
  }
</script>

<input
  bind:this={fileInput}
  type="file"
  accept="audio/*,video/*"
  multiple
  class="hidden"
  onchange={handleFileSelect}
/>

<button
  type="button"
  class="w-full rounded-xl border-2 border-dashed transition-all duration-200 p-8 flex flex-col items-center justify-center gap-3 cursor-pointer
    {dragover
      ? 'border-blue-500 bg-blue-500/10 scale-[1.01]'
      : uploading
        ? 'border-neutral-600 bg-[#252525]'
        : 'border-neutral-700 bg-[#1a1a1a] hover:border-neutral-500 hover:bg-[#252525]/50'
    }"
  ondragenter={handleDragEnter}
  ondragleave={handleDragLeave}
  ondragover={handleDragOver}
  ondrop={handleDrop}
  onclick={handleClick}
>
  {#if uploading}
    <div class="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
    <p class="text-sm text-neutral-400">Uploading...</p>
  {:else}
    <div class="w-12 h-12 rounded-full bg-[#252525] flex items-center justify-center {dragover ? 'bg-blue-500/20' : ''}">
      <svg class="w-6 h-6 {dragover ? 'text-blue-400' : 'text-neutral-500'}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
        <polyline points="17 8 12 3 7 8"/>
        <line x1="12" y1="3" x2="12" y2="15"/>
      </svg>
    </div>
    {#if dragover}
      <p class="text-sm text-blue-400 font-medium">Drop files to transcribe</p>
    {:else}
      <div class="text-center">
        <p class="text-sm text-neutral-300">Drop audio or video files here</p>
        <p class="text-xs text-neutral-500 mt-1">or click to browse</p>
      </div>
    {/if}
  {/if}
</button>
