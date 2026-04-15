<script>
  import { onMount } from 'svelte';
  import Titlebar from './components/Titlebar.svelte';
  import Sidebar from './components/Sidebar.svelte';
  import Dashboard from './pages/Dashboard.svelte';
  import History from './pages/History.svelte';
  import Settings from './pages/Settings.svelte';
  import { createWSConnection } from './lib/websocket.js';
  import { getStatus, getToday } from './lib/api.js';

  let page = $state('dashboard');
  let currentJob = $state(null);
  let todayItems = $state([]);
  let paused = $state(false);
  let systemStatus = $state('idle');
  let wsConnected = $state(false);

  function handleNavigate(target) {
    page = target;
  }

  function handleWsMessage(data) {
    // Backend sends: { type: "progress", step, filename, ... }
    if (data.type === 'progress') {
      if (data.step === 'done') {
        // Job completed — move to today list and clear current
        todayItems = [
          { filename: data.filename, title: data.filename, scene: '', completed_at: new Date().toISOString(), ...data },
          ...todayItems,
        ];
        currentJob = null;
        systemStatus = 'idle';
      } else if (data.step === 'failed') {
        currentJob = null;
        systemStatus = 'idle';
      } else {
        // In-progress update
        currentJob = { filename: data.filename, step: data.step, ...data };
        systemStatus = 'processing';
      }
    }
  }

  onMount(async () => {
    const ws = createWSConnection((data) => {
      wsConnected = true;
      handleWsMessage(data);
    });

    try {
      const [status, today] = await Promise.all([getStatus(), getToday()]);
      systemStatus = status.status ?? 'idle';
      paused = status.paused ?? false;
      currentJob = status.current_job ?? null;
      todayItems = today?.items ?? today ?? [];
    } catch (e) {
      console.error('Failed to fetch initial status:', e);
    }

    return () => ws.close();
  });
</script>

<div class="flex flex-col h-screen bg-[#0f0f0f] text-neutral-200 select-none overflow-hidden">
  <Titlebar status={systemStatus} />

  <div class="flex flex-1 overflow-hidden">
    <Sidebar {page} onNavigate={handleNavigate} connected={wsConnected} />

    <main class="flex-1 overflow-y-auto p-6">
      {#if page === 'dashboard'}
        <Dashboard {currentJob} {todayItems} {paused} {wsConnected} />
      {:else if page === 'history'}
        <History />
      {:else if page === 'settings'}
        <Settings />
      {/if}
    </main>
  </div>
</div>
