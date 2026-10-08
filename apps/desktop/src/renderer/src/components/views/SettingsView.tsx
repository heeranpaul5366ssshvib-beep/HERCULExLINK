import { useState, useEffect } from 'react';
import { Settings, Palette, Info, Rocket, Trash2, Cpu, HardDrive, Bot, Check, FlaskConical, Clock, Gauge, Sun, Moon, Contrast, RotateCcw, Smartphone } from 'lucide-react';
import { cn } from '@/src/utils/cn';
import {
  useTheme,
  ACCENTS,
  type AccentName,
  type FontScale,
  type ThemeMode,
  type FontFamily,
  type RadiusChoice,
  type DensityChoice,
  type ChatStyle,
  type SidebarSide,
  type ChatWidth,
  type BgEffect,
} from '@/src/context/ThemeContext';
import { ROADMAP } from '@/src/data/catalog';
import { clearWorkspace } from '@/src/hooks/useWorkspace';
import { clearHerculeStorage, useLocalStorage } from '@/src/hooks/useLocalStorage';
import { useAppConfig } from '@/src/hooks/useAppConfig';
import { IDLE_STOP_KEY, IDLE_STOP_MINUTES } from '@/src/constants';
import { useSync } from '@/src/hooks/useSync';

interface SettingsViewProps {
  modelStatus: string;
  currentModel: string | null;
}

const FONT_OPTIONS: { id: FontScale; label: string; hint: string }[] = [
  { id: 'compact', label: 'Compact', hint: 'Dense, more on screen' },
  { id: 'regular', label: 'Regular', hint: 'Balanced default' },
  { id: 'large', label: 'Large', hint: 'Roomier, easier to read' },
];

const THEME_OPTIONS: { id: ThemeMode; label: string; hint: string; icon: React.ReactNode }[] = [
  { id: 'dark', label: 'Dark', hint: 'Default deep navy', icon: <Moon className="w-4 h-4" /> },
  { id: 'midnight', label: 'Midnight', hint: 'Pure black', icon: <Contrast className="w-4 h-4" /> },
  { id: 'light', label: 'Light', hint: 'Bright daytime', icon: <Sun className="w-4 h-4" /> },
];

const FONT_FAMILY_OPTIONS: { id: FontFamily; label: string; hint: string }[] = [
  { id: 'inter', label: 'Inter', hint: 'Modern UI default' },
  { id: 'system', label: 'System', hint: 'Native OS font' },
  { id: 'serif', label: 'Serif', hint: 'Reading-friendly' },
  { id: 'mono', label: 'Mono', hint: 'Terminal feel' },
];

const RADIUS_OPTIONS: { id: RadiusChoice; label: string; hint: string }[] = [
  { id: 'sharp', label: 'Sharp', hint: '6px · precise' },
  { id: 'smooth', label: 'Smooth', hint: '10px · balanced' },
  { id: 'round', label: 'Round', hint: '14px · friendly' },
  { id: 'pill', label: 'Pill', hint: '20px · softest' },
];

const DENSITY_OPTIONS: { id: DensityChoice; label: string; hint: string }[] = [
  { id: 'compact', label: 'Compact', hint: 'Tight spacing' },
  { id: 'comfortable', label: 'Comfortable', hint: 'Balanced' },
  { id: 'spacious', label: 'Spacious', hint: 'Airy, relaxed' },
];

const CHAT_OPTIONS: { id: ChatStyle; label: string; hint: string }[] = [
  { id: 'bubbles', label: 'Bubbles', hint: 'Classic chat' },
  { id: 'minimal', label: 'Minimal', hint: 'Clean feed' },
  { id: 'cards', label: 'Cards', hint: 'Boxed messages' },
];

const WIDTH_OPTIONS: { id: ChatWidth; label: string; hint: string }[] = [
  { id: 'narrow', label: 'Narrow', hint: 'Focused · 3xl' },
  { id: 'wide', label: 'Wide', hint: 'Roomy · 5xl' },
  { id: 'full', label: 'Full', hint: 'Edge to edge' },
];

const SIDEBAR_OPTIONS: { id: SidebarSide; label: string; hint: string }[] = [
  { id: 'left', label: 'Left', hint: 'Classic' },
  { id: 'right', label: 'Right', hint: 'Mirrored' },
];

const BG_OPTIONS: { id: BgEffect; label: string; hint: string }[] = [
  { id: 'none', label: 'None', hint: 'Flat' },
  { id: 'gradient', label: 'Gradient', hint: 'Accent wash' },
  { id: 'grid', label: 'Grid', hint: 'Blueprint' },
  { id: 'glow', label: 'Glow', hint: 'Top light' },
  { id: 'aurora', label: 'Aurora', hint: 'Triple wash' },
];

const STATUS_META = {
  'in-progress': { label: 'In progress', icon: <FlaskConical className="w-3.5 h-3.5" />, classes: 'bg-blue-500/15 text-blue-400 border-blue-500/20' },
  planned: { label: 'Planned', icon: <Clock className="w-3.5 h-3.5" />, classes: 'bg-violet-500/15 text-violet-400 border-violet-500/20' },
  later: { label: 'Later', icon: <Rocket className="w-3.5 h-3.5" />, classes: 'bg-slate-700/60 text-text-tertiary border-border-primary' },
} as const;

function Toggle({ on, onClick, label }: { on: boolean; onClick: () => void; label: string }) {
  return (
    <button
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={onClick}
      className={cn('relative flex-shrink-0 h-6 w-11 rounded-full transition-colors', on ? 't-toggle-on' : 'bg-slate-700')}
    >
      <span className={cn('absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all', on ? 'left-[22px]' : 'left-0.5')} />
    </button>
  );
}

function OptionGrid<T extends string>({
  options,
  value,
  onPick,
  renderPreview,
}: {
  options: { id: T; label: string; hint: string }[];
  value: T;
  onPick: (v: T) => void;
  renderPreview?: (id: T) => React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
      {options.map((opt) => {
        const active = value === opt.id;
        return (
          <button
            key={opt.id}
            onClick={() => onPick(opt.id)}
            title={opt.hint}
            className={cn(
              'px-3 py-2.5 rounded-lg border transition-all text-left',
              active ? 't-accent-border t-accent-bg-soft' : 'border-border-primary hover:border-border-secondary'
            )}
          >
            <span className="flex items-center justify-between gap-2">
              <span className={cn('text-sm font-semibold', active ? 't-accent-text' : 'text-text-primary')}>
                {opt.label}
              </span>
              {active && <Check className="w-3.5 h-3.5 t-accent-text flex-shrink-0" />}
              {renderPreview?.(opt.id)}
            </span>
            <span className="block text-[11px] text-text-tertiary mt-0.5">{opt.hint}</span>
          </button>
        );
      })}
    </div>
  );
}

export function SettingsView({ modelStatus, currentModel }: SettingsViewProps) {
  const {
    accent, setAccent,
    fontScale, setFontScale,
    themeMode, setThemeMode,
    fontFamily, setFontFamily,
    radius, setRadius,
    density, setDensity,
    chatStyle, setChatStyle,
    sidebarSide, setSidebarSide,
    chatWidth, setChatWidth,
    bgEffect, setBgEffect,
    customAccent, setCustomAccent,
    showAvatars, setShowAvatars,
    showRightPanel, setShowRightPanel,
    animations, setAnimations,
    resetAppearance,
  } = useTheme();
  const [version, setVersion] = useState<string>('…');
  const [platform, setPlatform] = useState<string>('…');
  const [cleared, setCleared] = useState(false);
  const [idleStop, setIdleStop] = useLocalStorage<boolean>(IDLE_STOP_KEY, false);
  const { num: configNum, set: setConfig } = useAppConfig(0);
  const ctxSize = configNum('ctxSize', 0);
  const ctxEffective = configNum('ctxSizeEffective', 0);
  const { info: syncInfo, busy: syncBusy, setEnabled: setSyncEnabled, rotateCode, unpair } = useSync();

  useEffect(() => {
    if (typeof window !== 'undefined' && window.electronAPI) {
      window.electronAPI.app.getVersion().then(setVersion).catch(() => setVersion('dev'));
      setPlatform(window.nodeAPI?.platform ?? 'unknown');
    } else {
      setVersion('web preview');
      setPlatform('browser');
    }
  }, []);

  const handleClearWorkspace = () => {
    clearWorkspace();
    setCleared(true);
    setTimeout(() => setCleared(false), 2500);
  };

  const handleResetSetup = async () => {
    try {
      if (window.electronAPI) {
        await window.electronAPI.installer.reset();
        await window.electronAPI.app.restart();
      }
    } catch {
      clearHerculeStorage(['hercule-theme-accent', 'hercule-theme-font']);
    }
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-8">
      <div className="flex items-center gap-3 mb-1">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-700/60 text-text-secondary border border-border-primary">
          <Settings className="w-5 h-5" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-text-primary tracking-tight">Settings</h1>
          <p className="text-sm text-text-tertiary">Appearance studio, performance, about, and what is coming next</p>
        </div>
      </div>

      <h2 className="mt-6 mb-3 text-sm font-semibold uppercase tracking-wider text-text-tertiary flex items-center gap-2">
        <Palette className="w-4 h-4" /> Appearance studio
      </h2>
      <div className="card p-4 space-y-5">
        <div>
          <p className="text-sm font-medium text-text-primary mb-2">Theme</p>
          <OptionGrid options={THEME_OPTIONS} value={themeMode} onPick={setThemeMode} />
        </div>

        <div>
          <p className="text-sm font-medium text-text-primary mb-2">Accent color</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {(Object.keys(ACCENTS) as Exclude<AccentName, 'custom'>[]).map((name) => {
              const def = ACCENTS[name];
              const active = accent === name;
              return (
                <button
                  key={name}
                  onClick={() => setAccent(name)}
                  className={cn(
                    'p-3 rounded-xl border text-left transition-all',
                    active ? 't-accent-border t-accent-bg-soft' : 'border-border-primary hover:border-border-secondary'
                  )}
                >
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg mb-2" style={{ backgroundColor: def.soft }}>
                    <span className="h-4 w-4 rounded-full" style={{ backgroundColor: def.main }} />
                  </span>
                  <span className="flex items-center gap-1 text-xs font-semibold text-text-primary">
                    {def.label}
                    {active && <Check className="w-3.5 h-3.5 t-accent-text" />}
                  </span>
                </button>
              );
            })}
            <button
              onClick={() => setAccent('custom')}
              className={cn(
                'p-3 rounded-xl border text-left transition-all',
                accent === 'custom' ? 't-accent-border t-accent-bg-soft' : 'border-border-primary hover:border-border-secondary'
              )}
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-lg mb-2" style={{ backgroundColor: customAccent + '26' }}>
                <span className="h-4 w-4 rounded-full border border-white/40" style={{ backgroundColor: customAccent }} />
              </span>
              <span className="flex items-center gap-1 text-xs font-semibold text-text-primary">
                Custom
                {accent === 'custom' && <Check className="w-3.5 h-3.5 t-accent-text" />}
              </span>
            </button>
          </div>
          {accent === 'custom' && (
            <div className="mt-2 flex items-center gap-2">
              <input
                type="color"
                value={customAccent}
                onChange={(e) => setCustomAccent(e.target.value)}
                className="h-9 w-12 cursor-pointer rounded-lg border border-border-primary bg-transparent"
                aria-label="Pick custom accent color"
              />
              <input
                type="text"
                value={customAccent}
                onChange={(e) => {
                  const v = e.target.value;
                  if (/^#[0-9a-fA-F]{0,6}$/.test(v)) setCustomAccent(v.length === 7 ? v : v);
                }}
                placeholder="#ec4899"
                maxLength={7}
                className="input max-w-[120px] font-mono"
                aria-label="Custom accent hex"
              />
              <span className="text-xs text-text-tertiary">Applies instantly everywhere.</span>
            </div>
          )}
        </div>

        <div>
          <p className="text-sm font-medium text-text-primary mb-2">Text size</p>
          <div className="flex gap-2">
            {FONT_OPTIONS.map((f) => (
              <button
                key={f.id}
                onClick={() => setFontScale(f.id)}
                title={f.hint}
                className={cn(
                  'flex-1 px-3 py-2 text-sm rounded-lg border transition-all',
                  fontScale === f.id
                    ? 't-accent-border t-accent-bg-soft t-accent-text font-semibold'
                    : 'border-border-primary text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary'
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <p className="text-sm font-medium text-text-primary mb-2">Font family</p>
          <OptionGrid options={FONT_FAMILY_OPTIONS} value={fontFamily} onPick={setFontFamily} />
        </div>

        <div>
          <p className="text-sm font-medium text-text-primary mb-2">Corner roundness</p>
          <OptionGrid options={RADIUS_OPTIONS} value={radius} onPick={setRadius} />
        </div>

        <div>
          <p className="text-sm font-medium text-text-primary mb-2">Density</p>
          <OptionGrid options={DENSITY_OPTIONS} value={density} onPick={setDensity} />
        </div>

        <div>
          <p className="text-sm font-medium text-text-primary mb-2">Chat style</p>
          <OptionGrid options={CHAT_OPTIONS} value={chatStyle} onPick={setChatStyle} />
        </div>

        <div>
          <p className="text-sm font-medium text-text-primary mb-2">Chat width</p>
          <OptionGrid options={WIDTH_OPTIONS} value={chatWidth} onPick={setChatWidth} />
        </div>

        <div>
          <p className="text-sm font-medium text-text-primary mb-2">Sidebar position</p>
          <OptionGrid options={SIDEBAR_OPTIONS} value={sidebarSide} onPick={setSidebarSide} />
        </div>

        <div>
          <p className="text-sm font-medium text-text-primary mb-2">Background effect</p>
          <OptionGrid options={BG_OPTIONS} value={bgEffect} onPick={setBgEffect} />
        </div>

        <div className="space-y-3 pt-1">
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <p className="text-sm font-medium text-text-primary">Show avatars</p>
              <p className="text-xs text-text-tertiary mt-0.5">Bot / user icons next to messages.</p>
            </div>
            <Toggle on={showAvatars} onClick={() => setShowAvatars(!showAvatars)} label="Show avatars" />
          </div>
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <p className="text-sm font-medium text-text-primary">Monitoring panel</p>
              <p className="text-xs text-text-tertiary mt-0.5">Right-side system / activity / plugins panel.</p>
            </div>
            <Toggle on={showRightPanel} onClick={() => setShowRightPanel(!showRightPanel)} label="Show monitoring panel" />
          </div>
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <p className="text-sm font-medium text-text-primary">Animations</p>
              <p className="text-xs text-text-tertiary mt-0.5">Slide, glow and pulse effects. Off = calmer + faster.</p>
            </div>
            <Toggle on={animations} onClick={() => setAnimations(!animations)} label="Enable animations" />
          </div>
        </div>

        <div className="rounded-xl border border-border-primary p-3">
          <p className="text-xs uppercase tracking-wider text-text-tertiary mb-2">Live preview</p>
          <div className="flex justify-end mb-2">
            <div className="max-w-[75%] rounded-2xl rounded-br-md bg-slate-700/60 border border-border-primary px-3 py-2 text-xs text-text-primary">
              Preview: your message bubble
            </div>
          </div>
          <div className="flex gap-2">
            <div className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full t-accent-gradient text-white">
              <Bot className="w-3.5 h-3.5" />
            </div>
            <div className="t-accent-bg-soft t-accent-border border rounded-xl px-3 py-2 text-xs text-text-primary">
              Preview: HERCULE reply in your accent, radius, font and density.
            </div>
          </div>
        </div>

        <button
          onClick={resetAppearance}
          className="flex items-center justify-center gap-2 w-full px-4 py-2 text-sm rounded-lg border border-border-primary text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
        >
          <RotateCcw className="w-4 h-4" /> Reset appearance to defaults
        </button>
      </div>

      <h2 className="mt-6 mb-3 text-sm font-semibold uppercase tracking-wider text-text-tertiary flex items-center gap-2">
        <Gauge className="w-4 h-4" /> Performance & RAM
      </h2>
      <div className="card p-4 space-y-4">
        <div>
          <p className="text-sm font-medium text-text-primary">Conversation memory (context window)</p>
          <p className="text-xs text-text-tertiary mt-0.5">
            Larger remembers longer chats but uses more RAM. Applies the next time the model starts.
            {ctxEffective > 0 && (
              <span className="text-text-secondary"> Currently running with {ctxEffective.toLocaleString()} tokens.</span>
            )}
          </p>
          <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-2">
            {[
              { value: 0, label: 'Auto', hint: '2K · 4K · 8K by your RAM' },
              { value: 2048, label: '2K', hint: '~lowest RAM' },
              { value: 4096, label: '4K', hint: 'balanced' },
              { value: 8192, label: '8K', hint: '~most RAM' },
            ].map((opt) => (
              <button
                key={opt.value}
                onClick={() => setConfig('ctxSize', opt.value)}
                title={opt.hint}
                className={cn(
                  'px-3 py-2 rounded-lg border transition-all text-left',
                  ctxSize === opt.value
                    ? 't-accent-border t-accent-bg-soft'
                    : 'border-border-primary hover:border-border-secondary'
                )}
              >
                <span className={cn('block text-sm font-semibold', ctxSize === opt.value ? 't-accent-text' : 'text-text-primary')}>
                  {opt.label}
                </span>
                <span className="block text-[11px] text-text-tertiary">{opt.hint}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-3 pt-1">
          <div className="flex-1">
            <p className="text-sm font-medium text-text-primary">Free RAM when idle</p>
            <p className="text-xs text-text-tertiary mt-0.5">
              Stop the model server after {IDLE_STOP_MINUTES} minutes without chatting. Frees all model RAM; start it again from the Model Manager when you return.
            </p>
          </div>
          <Toggle on={idleStop} onClick={() => setIdleStop(!idleStop)} label="Free RAM when idle" />
        </div>
      </div>

      <h2 className="mt-6 mb-3 text-sm font-semibold uppercase tracking-wider text-text-tertiary flex items-center gap-2">
        <Smartphone className="w-4 h-4" /> Mobile sync
      </h2>
      <div className="card p-4 space-y-4">
        <div className="flex items-center gap-3">
          <div className="flex-1">
            <p className="text-sm font-medium text-text-primary">Sync over local Wi-Fi</p>
            <p className="text-xs text-text-tertiary mt-0.5">
              Shares tasks, projects, memories and your goal with a paired phone app. Local network only — nothing listens while this is off. Only enable on trusted Wi-Fi.
            </p>
          </div>
          <Toggle on={syncInfo.enabled} onClick={() => setSyncEnabled(!syncInfo.enabled)} label="Enable mobile sync" />
        </div>
        {syncInfo.enabled && (
          <div className="rounded-xl border border-border-primary p-3 space-y-3">
            <div>
              <p className="text-xs uppercase tracking-wider text-text-tertiary">Connect to</p>
              {syncInfo.addresses.length > 0 ? (
                <div className="mt-1 space-y-1">
                  {syncInfo.addresses.map((a) => (
                    <p key={a} className="font-mono text-sm t-accent-text">{a}:{syncInfo.port}</p>
                  ))}
                </div>
              ) : (
                <p className="mt-1 text-xs text-text-tertiary">No network found — connect to Wi-Fi first.</p>
              )}
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-text-tertiary">Pairing code</p>
              <p className="mt-1 font-mono text-2xl font-bold tracking-[0.2em] text-text-primary">{syncInfo.pairingCode || '…'}</p>
              <p className="mt-0.5 text-xs text-text-tertiary">
                {syncInfo.paired
                  ? `A device is paired${syncInfo.lastSyncAt ? ` · last sync ${new Date(syncInfo.lastSyncAt).toLocaleTimeString()}` : ''}.`
                  : 'Enter this code in the phone app to pair.'}
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={rotateCode}
                disabled={syncBusy}
                className="flex-1 px-4 py-2 text-sm rounded-lg border border-border-primary text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors disabled:opacity-40"
              >
                New code{syncInfo.paired ? ' (unpairs device)' : ''}
              </button>
              {syncInfo.paired && (
                <button
                  onClick={unpair}
                  disabled={syncBusy}
                  className="flex-1 px-4 py-2 text-sm rounded-lg border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-40"
                >
                  Unpair device
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      <h2 className="mt-6 mb-3 text-sm font-semibold uppercase tracking-wider text-text-tertiary flex items-center gap-2">
        <Info className="w-4 h-4" /> About HERCULE
      </h2>
      <div className="card p-5">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl t-accent-gradient text-white shadow-lg">
            <Bot className="w-6 h-6" />
          </div>
          <div>
            <p className="text-lg font-bold text-text-primary tracking-tight">
              HERCULE <span className="t-accent-text">x</span>
            </p>
            <p className="text-xs uppercase tracking-[0.2em] text-text-tertiary">AI Operating System</p>
          </div>
        </div>
        <p className="mt-3 text-sm text-text-secondary leading-relaxed">
          Two pillars, one core: <span className="text-text-primary font-medium">Intelligence</span> (reasoning, memory,
          perception) joined to <span className="text-text-primary font-medium">Execution</span> (tools, automation,
          verification) by the HERCULEx core — running 100% on your device. No cloud, no tracking, no account.
        </p>
        <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
          {[
            { icon: <Info className="w-4 h-4 mx-auto mb-1" />, label: 'Version', value: version },
            { icon: <Cpu className="w-4 h-4 mx-auto mb-1" />, label: 'Platform', value: platform },
            { icon: <Bot className="w-4 h-4 mx-auto mb-1" />, label: 'Model', value: currentModel ?? 'none' },
            { icon: <HardDrive className="w-4 h-4 mx-auto mb-1" />, label: 'Engine', value: modelStatus },
          ].map((s) => (
            <div key={s.label} className="rounded-xl bg-slate-800/50 border border-border-primary px-2 py-3">
              <div className="text-text-tertiary">{s.icon}</div>
              <p className="text-[11px] uppercase tracking-wider text-text-muted mt-1">{s.label}</p>
              <p className="text-xs font-mono font-semibold text-text-primary truncate" title={s.value}>{s.value}</p>
            </div>
          ))}
        </div>
      </div>

      <h2 className="mt-6 mb-3 text-sm font-semibold uppercase tracking-wider text-text-tertiary flex items-center gap-2">
        <Rocket className="w-4 h-4" /> Future upgrades
      </h2>
      <div className="space-y-2">
        {ROADMAP.map((item) => {
          const meta = STATUS_META[item.status];
          return (
            <div key={item.title} className="card p-4 flex items-start gap-3">
              <div className="flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="font-semibold text-text-primary text-sm">{item.title}</h3>
                  <span className={cn('flex items-center gap-1 px-2 py-0.5 text-[11px] font-medium rounded-full border', meta.classes)}>
                    {meta.icon}
                    {meta.label}
                  </span>
                </div>
                <p className="mt-1 text-xs text-text-tertiary">{item.description}</p>
              </div>
            </div>
          );
        })}
      </div>

      <h2 className="mt-6 mb-3 text-sm font-semibold uppercase tracking-wider text-text-tertiary flex items-center gap-2">
        <Trash2 className="w-4 h-4" /> Data & reset
      </h2>
      <div className="card p-4 flex flex-col sm:flex-row gap-2">
        <button
          onClick={handleClearWorkspace}
          className="flex-1 px-4 py-2 text-sm rounded-lg border border-border-primary text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
        >
          {cleared ? 'Workspace cleared ✓' : 'Clear tasks, projects & memories'}
        </button>
        <button
          onClick={handleResetSetup}
          className="flex-1 px-4 py-2 text-sm rounded-lg border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-colors"
        >
          Re-run first-time setup
        </button>
      </div>
    </div>
  );
}
