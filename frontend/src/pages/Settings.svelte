<script>
  import { onMount } from 'svelte';
  import Toggle from '../components/Toggle.svelte';
  import { getConfig, getSystemInfo } from '../lib/api.js';

  let config = $state({
    model: 'large-v3-turbo',
    device: 'auto',
    language: 'zh',
    obsidian_path: '',
    captures_path: '',
    telegram_configured: false,
    plaud_enabled: false,
    icloud_enabled: false,
    process_priority: 'normal',
  });

  let system = $state({
    cpu: '',
    memory: '',
    gpu: '',
    version: '',
  });

  let saving = $state(false);

  const models = [
    { value: 'tiny', label: 'Tiny (fastest)' },
    { value: 'base', label: 'Base' },
    { value: 'small', label: 'Small' },
    { value: 'medium', label: 'Medium' },
    { value: 'large-v3-turbo', label: 'Large V3 Turbo (recommended)' },
  ];

  const devices = [
    { value: 'auto', label: 'Auto' },
    { value: 'cuda', label: 'CUDA (GPU)' },
    { value: 'cpu', label: 'CPU' },
    { value: 'mps', label: 'MPS (Apple Silicon)' },
  ];

  const priorities = [
    { value: 'low', label: 'Low' },
    { value: 'normal', label: 'Normal' },
    { value: 'high', label: 'High' },
  ];

  async function handleConfigChange(key, value) {
    config = { ...config, [key]: value };
    saving = true;
    try {
      const res = await fetch('http://127.0.0.1:8765/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value }),
      });
      if (!res.ok) throw new Error(`Config update failed: ${res.status}`);
    } catch (e) {
      console.error('Failed to save config:', e);
    } finally {
      saving = false;
    }
  }

  async function pickFolder(key) {
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({ directory: true, multiple: false });
      if (selected) {
        handleConfigChange(key, selected);
      }
    } catch (e) {
      console.error('Folder picker error:', e);
    }
  }

  onMount(async () => {
    try {
      const [cfg, sys] = await Promise.all([getConfig(), getSystemInfo()]);
      if (cfg) config = { ...config, ...cfg };
      if (sys) system = { ...system, ...sys };
    } catch (e) {
      console.error('Failed to load settings:', e);
    }
  });
</script>

<div class="max-w-2xl mx-auto space-y-8">
  <!-- Header -->
  <div class="flex items-center justify-between">
    <h1 class="text-xl font-semibold text-neutral-100">Settings</h1>
    {#if saving}
      <span class="text-xs text-blue-400">Saving...</span>
    {/if}
  </div>

  <!-- Transcription -->
  <section class="space-y-4">
    <h2 class="text-sm font-medium text-neutral-400 uppercase tracking-wider">Transcription</h2>
    <div class="bg-[#1a1a1a] rounded-xl p-5 space-y-5 border border-neutral-800">
      <!-- Model -->
      <div class="flex items-center justify-between">
        <div>
          <p class="text-sm text-neutral-200">Model</p>
          <p class="text-xs text-neutral-500 mt-0.5">Larger models are more accurate but slower</p>
        </div>
        <select
          value={config.model}
          onchange={(e) => handleConfigChange('model', e.target.value)}
          class="bg-[#252525] border border-neutral-700 rounded-lg px-3 py-1.5 text-sm text-neutral-200 focus:outline-none focus:border-blue-500/50 cursor-pointer"
        >
          {#each models as m}
            <option value={m.value}>{m.label}</option>
          {/each}
        </select>
      </div>

      <!-- Device -->
      <div class="flex items-center justify-between border-t border-neutral-800 pt-5">
        <div>
          <p class="text-sm text-neutral-200">Device</p>
          <p class="text-xs text-neutral-500 mt-0.5">Hardware acceleration for transcription</p>
        </div>
        <select
          value={config.device}
          onchange={(e) => handleConfigChange('device', e.target.value)}
          class="bg-[#252525] border border-neutral-700 rounded-lg px-3 py-1.5 text-sm text-neutral-200 focus:outline-none focus:border-blue-500/50 cursor-pointer"
        >
          {#each devices as d}
            <option value={d.value}>{d.label}</option>
          {/each}
        </select>
      </div>

      <!-- Language -->
      <div class="flex items-center justify-between border-t border-neutral-800 pt-5">
        <div>
          <p class="text-sm text-neutral-200">Language</p>
          <p class="text-xs text-neutral-500 mt-0.5">Primary language of audio files</p>
        </div>
        <input
          type="text"
          value={config.language}
          onchange={(e) => handleConfigChange('language', e.target.value)}
          class="bg-[#252525] border border-neutral-700 rounded-lg px-3 py-1.5 text-sm text-neutral-200 w-20 text-center focus:outline-none focus:border-blue-500/50"
          placeholder="zh"
        />
      </div>
    </div>
  </section>

  <!-- Paths -->
  <section class="space-y-4">
    <h2 class="text-sm font-medium text-neutral-400 uppercase tracking-wider">Paths</h2>
    <div class="bg-[#1a1a1a] rounded-xl p-5 space-y-5 border border-neutral-800">
      <!-- Obsidian output -->
      <div>
        <p class="text-sm text-neutral-200 mb-2">Obsidian Output</p>
        <div class="flex gap-2">
          <input
            type="text"
            value={config.obsidian_path}
            onchange={(e) => handleConfigChange('obsidian_path', e.target.value)}
            class="flex-1 bg-[#252525] border border-neutral-700 rounded-lg px-3 py-1.5 text-sm text-neutral-300 focus:outline-none focus:border-blue-500/50 font-mono text-xs"
            placeholder="~/Documents/Obsidian Vault/"
          />
          <button
            onclick={() => pickFolder('obsidian_path')}
            class="px-3 py-1.5 bg-[#252525] border border-neutral-700 rounded-lg text-sm text-neutral-400 hover:text-neutral-200 hover:border-neutral-600 transition-colors shrink-0"
          >
            Browse
          </button>
        </div>
      </div>

      <!-- Captures output -->
      <div class="border-t border-neutral-800 pt-5">
        <p class="text-sm text-neutral-200 mb-2">Captures Output</p>
        <div class="flex gap-2">
          <input
            type="text"
            value={config.captures_path}
            onchange={(e) => handleConfigChange('captures_path', e.target.value)}
            class="flex-1 bg-[#252525] border border-neutral-700 rounded-lg px-3 py-1.5 text-sm text-neutral-300 focus:outline-none focus:border-blue-500/50 font-mono text-xs"
            placeholder="~/Documents/captures/"
          />
          <button
            onclick={() => pickFolder('captures_path')}
            class="px-3 py-1.5 bg-[#252525] border border-neutral-700 rounded-lg text-sm text-neutral-400 hover:text-neutral-200 hover:border-neutral-600 transition-colors shrink-0"
          >
            Browse
          </button>
        </div>
      </div>
    </div>
  </section>

  <!-- Integrations -->
  <section class="space-y-4">
    <h2 class="text-sm font-medium text-neutral-400 uppercase tracking-wider">Integrations</h2>
    <div class="bg-[#1a1a1a] rounded-xl p-5 space-y-5 border border-neutral-800">
      <!-- Telegram -->
      <div class="flex items-center justify-between">
        <div>
          <p class="text-sm text-neutral-200">Telegram</p>
          <p class="text-xs text-neutral-500 mt-0.5">Send transcription notifications</p>
        </div>
        {#if config.telegram_configured}
          <span class="inline-flex items-center px-2.5 py-1 rounded-full bg-green-500/10 text-green-400 text-xs font-medium border border-green-500/20">
            Configured
          </span>
        {:else}
          <span class="inline-flex items-center px-2.5 py-1 rounded-full bg-neutral-500/10 text-neutral-500 text-xs font-medium border border-neutral-500/20">
            Not configured
          </span>
        {/if}
      </div>

      <!-- Plaud -->
      <div class="flex items-center justify-between border-t border-neutral-800 pt-5">
        <div>
          <p class="text-sm text-neutral-200">Plaud Sync</p>
          <p class="text-xs text-neutral-500 mt-0.5">Auto-import from Plaud recorder</p>
        </div>
        <Toggle
          checked={config.plaud_enabled}
          onChange={(v) => handleConfigChange('plaud_enabled', v)}
        />
      </div>

      <!-- iCloud -->
      <div class="flex items-center justify-between border-t border-neutral-800 pt-5">
        <div>
          <p class="text-sm text-neutral-200">iCloud Sync</p>
          <p class="text-xs text-neutral-500 mt-0.5">Watch iCloud folder for new recordings</p>
        </div>
        <Toggle
          checked={config.icloud_enabled}
          onChange={(v) => handleConfigChange('icloud_enabled', v)}
        />
      </div>
    </div>
  </section>

  <!-- System -->
  <section class="space-y-4">
    <h2 class="text-sm font-medium text-neutral-400 uppercase tracking-wider">System</h2>
    <div class="bg-[#1a1a1a] rounded-xl p-5 space-y-5 border border-neutral-800">
      <!-- Priority -->
      <div class="flex items-center justify-between">
        <div>
          <p class="text-sm text-neutral-200">Process Priority</p>
          <p class="text-xs text-neutral-500 mt-0.5">CPU priority for background processing</p>
        </div>
        <select
          value={config.process_priority}
          onchange={(e) => handleConfigChange('process_priority', e.target.value)}
          class="bg-[#252525] border border-neutral-700 rounded-lg px-3 py-1.5 text-sm text-neutral-200 focus:outline-none focus:border-blue-500/50 cursor-pointer"
        >
          {#each priorities as p}
            <option value={p.value}>{p.label}</option>
          {/each}
        </select>
      </div>

      <!-- System info -->
      <div class="border-t border-neutral-800 pt-5 space-y-3">
        <p class="text-sm text-neutral-200 mb-3">System Info</p>
        <div class="grid grid-cols-2 gap-3 text-xs">
          {#if system.cpu}
            <div class="bg-[#252525] rounded-lg p-3">
              <p class="text-neutral-500 mb-1">CPU</p>
              <p class="text-neutral-300 font-mono">{system.cpu}</p>
            </div>
          {/if}
          {#if system.memory}
            <div class="bg-[#252525] rounded-lg p-3">
              <p class="text-neutral-500 mb-1">Memory</p>
              <p class="text-neutral-300 font-mono">{system.memory}</p>
            </div>
          {/if}
          {#if system.gpu}
            <div class="bg-[#252525] rounded-lg p-3">
              <p class="text-neutral-500 mb-1">GPU</p>
              <p class="text-neutral-300 font-mono">{system.gpu}</p>
            </div>
          {/if}
          {#if system.version}
            <div class="bg-[#252525] rounded-lg p-3">
              <p class="text-neutral-500 mb-1">Version</p>
              <p class="text-neutral-300 font-mono">{system.version}</p>
            </div>
          {/if}
        </div>
      </div>
    </div>
  </section>

  <!-- Bottom spacer -->
  <div class="h-8"></div>
</div>
