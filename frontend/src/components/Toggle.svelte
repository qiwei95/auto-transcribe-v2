<script>
  let { checked = false, onChange, label = '', disabled = false } = $props();

  function handleClick() {
    if (disabled) return;
    onChange?.(!checked);
  }

  function handleKeydown(e) {
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      handleClick();
    }
  }
</script>

<label class="inline-flex items-center gap-3 {disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}">
  <button
    type="button"
    role="switch"
    aria-checked={checked}
    aria-label={label}
    {disabled}
    onclick={handleClick}
    onkeydown={handleKeydown}
    class="relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors duration-200 ease-in-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 focus-visible:ring-offset-[#1a1a1a]
      {checked ? 'bg-blue-500' : 'bg-neutral-600'}"
  >
    <span
      class="pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow-sm transform transition-transform duration-200 ease-in-out mt-0.5
        {checked ? 'translate-x-[18px] ml-0' : 'translate-x-[2px]'}"
    ></span>
  </button>
  {#if label}
    <span class="text-sm text-neutral-300">{label}</span>
  {/if}
</label>
