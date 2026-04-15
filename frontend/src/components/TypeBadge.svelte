<script>
  let { type = 'unknown' } = $props();

  const colorMap = {
    meeting: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
    memo: 'bg-green-500/15 text-green-400 border-green-500/30',
    'video-short': 'bg-purple-500/15 text-purple-400 border-purple-500/30',
    'video-long': 'bg-purple-500/15 text-purple-400 border-purple-500/30',
    video: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
    call: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
    class: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
    lecture: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
    interview: 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30',
    podcast: 'bg-pink-500/15 text-pink-400 border-pink-500/30',
    voice: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  };

  let classes = $derived(
    colorMap[type] ?? 'bg-neutral-500/15 text-neutral-400 border-neutral-500/30'
  );

  let label = $derived(
    type.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  );
</script>

<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium border {classes}">
  {label}
</span>
