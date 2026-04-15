<script>
  let { job } = $props();

  const steps = [
    { key: 'waiting', label: 'Queued' },
    { key: 'extracting', label: 'Extracting' },
    { key: 'transcribing', label: 'Transcribing' },
    { key: 'summarizing', label: 'Summarizing' },
    { key: 'saving', label: 'Saving' },
  ];

  let currentStepIndex = $derived(
    Math.max(0, steps.findIndex(s => s.key === job?.step))
  );

  let progress = $derived(
    job?.step === 'done' ? 100 : ((currentStepIndex + 0.5) / steps.length) * 100
  );

  let filename = $derived(
    job?.filename?.length > 40
      ? job.filename.slice(0, 37) + '...'
      : job?.filename ?? 'Unknown file'
  );
</script>

{#if job}
  <div class="bg-[#252525] rounded-xl p-5 border border-neutral-800">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded-lg bg-blue-500/20 flex items-center justify-center">
          <svg class="w-4 h-4 text-blue-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="5 3 19 12 5 21 5 3"/>
          </svg>
        </div>
        <div>
          <p class="text-sm font-medium text-neutral-200">{filename}</p>
          <p class="text-xs text-neutral-500">{job.step_label ?? steps[currentStepIndex]?.label ?? 'Processing'}</p>
        </div>
      </div>
      <span class="text-xs text-blue-400 font-mono">{Math.round(progress)}%</span>
    </div>

    <!-- Progress bar -->
    <div class="h-1 bg-neutral-700 rounded-full overflow-hidden mb-5">
      <div
        class="h-full bg-blue-500 rounded-full transition-all duration-700 ease-out"
        style="width: {progress}%"
      ></div>
    </div>

    <!-- Step indicators -->
    <div class="flex items-center justify-between">
      {#each steps as step, i}
        <div class="flex flex-col items-center gap-1.5">
          <div class="relative">
            {#if i < currentStepIndex}
              <!-- Completed -->
              <div class="w-6 h-6 rounded-full bg-blue-500 flex items-center justify-center">
                <svg class="w-3 h-3 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
              </div>
            {:else if i === currentStepIndex}
              <!-- Current - pulsing -->
              <div class="w-6 h-6 rounded-full bg-blue-500 flex items-center justify-center animate-pulse">
                <div class="w-2 h-2 rounded-full bg-white"></div>
              </div>
            {:else}
              <!-- Pending -->
              <div class="w-6 h-6 rounded-full bg-neutral-700 flex items-center justify-center">
                <div class="w-2 h-2 rounded-full bg-neutral-500"></div>
              </div>
            {/if}
          </div>
          <span class="text-[10px] {i <= currentStepIndex ? 'text-neutral-300' : 'text-neutral-600'}">
            {step.label}
          </span>
        </div>

        {#if i < steps.length - 1}
          <div class="flex-1 h-px mx-1 mb-5 {i < currentStepIndex ? 'bg-blue-500' : 'bg-neutral-700'}"></div>
        {/if}
      {/each}
    </div>
  </div>
{/if}
