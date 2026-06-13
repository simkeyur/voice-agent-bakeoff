import { useState, useEffect, useRef, useCallback } from 'react';
import { 
  Sun, Moon, Play, Pause, BarChart3, History, Settings, 
  Mic, CloudLightning, AudioLines, ClipboardCheck, ArrowRightLeft, 
  Trash2, CheckCircle2, XCircle, AlertCircle, ArrowLeft,
  ChevronLeft, ChevronRight, LayoutDashboard, Plus
} from 'lucide-react';
import logoUrl from './assets/logo.png';
import './App.css';

// Custom Waveform Visualizer using Canvas & Web Audio API
function AudioWaveformVisualizer({ src, latencyMs }) {
  const canvasRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [audioData, setAudioData] = useState(null);
  const [duration, setDuration] = useState(0);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);
    
    fetch(src)
      .then((res) => {
        if (!res.ok) throw new Error('Audio file not available');
        return res.arrayBuffer();
      })
      .then((arrayBuffer) => {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        return audioCtx.decodeAudioData(arrayBuffer);
      })
      .then((audioBuffer) => {
        if (!active) return;
        setDuration(audioBuffer.duration);
        
        const rawData = audioBuffer.getChannelData(0);
        const samples = 80; // horizontal resolution
        const blockSize = Math.floor(rawData.length / samples);
        const filteredData = [];
        for (let i = 0; i < samples; i++) {
          let blockStart = blockSize * i;
          let sum = 0;
          for (let j = 0; j < blockSize; j++) {
            sum = sum + Math.abs(rawData[blockStart + j]);
          }
          filteredData.push(sum / blockSize);
        }
        
        const max = Math.max(...filteredData);
        const normalizedData = filteredData.map(n => (max > 0 ? n / max : 0.05));
        setAudioData(normalizedData);
        setLoading(false);
      })
      .catch((err) => {
        console.warn('Waveform load skipped or failed:', err.message);
        if (active) {
          setError(true);
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [src]);

  useEffect(() => {
    if (!audioData || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    
    canvas.width = canvas.offsetWidth * dpr;
    canvas.height = canvas.offsetHeight * dpr;
    ctx.scale(dpr, dpr);
    
    const w = canvas.offsetWidth;
    const h = canvas.offsetHeight;
    
    ctx.clearRect(0, 0, w, h);
    
    const barWidth = w / audioData.length;
    const gap = 1.5;
    
    for (let i = 0; i < audioData.length; i++) {
      const val = audioData[i];
      const barHeight = Math.max(3, val * (h - 8));
      const x = i * barWidth;
      const y = (h - barHeight) / 2;
      
      const barTime = (i / audioData.length) * duration;
      const isLatency = latencyMs && barTime < (latencyMs / 1000);
      
      if (isLatency) {
        ctx.fillStyle = 'rgba(99, 102, 241, 0.35)'; // Purple/Indigo latency window
      } else {
        ctx.fillStyle = 'rgba(16, 185, 129, 0.85)'; // Success green response audio
      }
      
      ctx.beginPath();
      // Draw rounded rectangle bars
      if (ctx.roundRect) {
        ctx.roundRect(x, y, Math.max(1, barWidth - gap), barHeight, 2);
      } else {
        ctx.rect(x, y, Math.max(1, barWidth - gap), barHeight);
      }
      ctx.fill();
    }
  }, [audioData, duration, latencyMs]);

  const latencyPercent = (latencyMs && duration) ? Math.min(95, ((latencyMs / 1000) / duration) * 100) : 0;

  return (
    <div className="audio-player-wrapper">
      <div className="waveform-canvas-container">
        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', fontSize: 11, color: 'var(--muted)' }}>
            Processing audio peaks...
          </div>
        )}
        {error && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', fontSize: 11, color: 'var(--muted)' }}>
            Waveform rendering unavailable
          </div>
        )}
        {!loading && !error && (
          <>
            <canvas ref={canvasRef} className="waveform-canvas" />
            {latencyPercent > 0 && (
              <div 
                className="waveform-latency-marker" 
                style={{ width: `${latencyPercent}%` }}
                title={`Time-To-First-Audio Latency: ${Math.round(latencyMs)}ms`}
              >
                <span>{Math.round(latencyMs)}ms TTFA</span>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// Upgraded Audio Player with integrated Waveform & Latency tracking
function AudioPlayer({ src, latencyMs }) {
  const audioRef = useRef(null);
  const [playing, setPlaying] = useState(false);

  const toggle = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing) {
      audio.pause();
    } else {
      audio.play();
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, width: '100%', padding: '4px 0' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <button
          type="button"
          className="audio-play-btn"
          onClick={toggle}
          aria-label={playing ? 'Pause response audio' : 'Play response audio'}
          style={{
            width: 28,
            height: 28,
            borderRadius: '50%',
            background: 'var(--color-primary)',
            color: '#fff',
            border: 'none',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            boxShadow: '0 2px 4px rgba(99, 102, 241, 0.25)',
            flexShrink: 0
          }}
        >
          {playing ? <Pause size={12} fill="#fff" /> : <Play size={12} fill="#fff" />}
        </button>
        <span className="audio-player-label" style={{ fontWeight: 600, fontSize: 11, color: 'var(--fg)' }}>Play Response</span>
      </div>
      
      <AudioWaveformVisualizer src={src} latencyMs={latencyMs} />
      
      <audio
        ref={audioRef}
        src={src}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        style={{ display: 'none' }}
      />
    </div>
  );
}

// Live telemetry visualizer of the Pipecat evaluation pipeline
function LivePipelineVisualizer({ activeStep }) {
  const steps = [
    { label: 'Audio Injector', icon: Mic, desc: 'AudioInjectionProcessor' },
    { label: 'Provider Adapter', icon: CloudLightning, desc: 'BaseProviderAdapter' },
    { label: 'Audio Capture', icon: AudioLines, desc: 'AudioCaptureProcessor' },
    { label: 'Metrics Collector', icon: ClipboardCheck, desc: 'MetricsCollector' }
  ];

  // Active step is 1-indexed. Convert to percentage.
  const progressPercent = activeStep <= 1 ? 0 : ((activeStep - 1) / (steps.length - 1)) * 100;

  return (
    <div className="card pipeline-visualizer-card">
      <div className="card-header" style={{ marginBottom: 12 }}>
        <span className="card-title">Live Pipecat Session Telemetry</span>
      </div>
      <div className="card-body">
        <div className="pipeline-visualizer">
          <div className="pipeline-nodes-container">
            <div className="pipeline-connector">
              <div 
                className="pipeline-connector-progress" 
                style={{ width: `${progressPercent}%` }}
              ></div>
            </div>
            
            {steps.map((step, idx) => {
              const stepNum = idx + 1;
              let status = 'idle';
              if (activeStep >= stepNum) {
                status = activeStep === stepNum ? 'active' : 'completed';
              }
              const Icon = step.icon;

              return (
                <div key={idx} className={`pipeline-node ${status}`}>
                  <div className="pipeline-node-icon-wrapper">
                    <Icon size={18} className={status === 'active' ? 'animate-pulse' : ''} />
                  </div>
                  <div className="pipeline-node-label">{step.label}</div>
                  <div style={{ fontSize: 9, color: 'var(--muted)', marginTop: -2 }}>{step.desc}</div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

// Custom responsive SVG comparative bar chart
function CustomBarChart({ geminiValue, openaiValue, title, unit, lowerIsBetter = true }) {
  const maxValue = Math.max(geminiValue || 0, openaiValue || 0) || 100;
  const geminiPercent = geminiValue ? (geminiValue / maxValue) * 100 : 0;
  const openaiPercent = openaiValue ? (openaiValue / maxValue) * 100 : 0;
  
  const isGeminiWinner = lowerIsBetter ? (geminiValue < openaiValue) : (geminiValue > openaiValue);
  const showWinner = geminiValue && openaiValue && (geminiValue !== openaiValue);
  
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '8px 0' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--fg)' }}>{title}</span>
        {showWinner && (
          <span style={{ 
            fontSize: 10, 
            fontWeight: 700, 
            color: 'var(--success)', 
            background: 'rgba(16, 185, 129, 0.08)', 
            padding: '2px 8px', 
            borderRadius: '12px',
            border: '1px solid rgba(16, 185, 129, 0.15)'
          }}>
            {isGeminiWinner ? 'Gemini leading' : 'OpenAI leading'}
          </span>
        )}
      </div>
      
      <svg viewBox="0 0 400 110" style={{ width: '100%', height: 'auto', overflow: 'visible' }}>
        <defs>
          <linearGradient id="geminiGrad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#4f46e5" />
            <stop offset="100%" stopColor="#6366f1" />
          </linearGradient>
          <linearGradient id="openaiGrad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#0891b2" />
            <stop offset="100%" stopColor="#06b6d4" />
          </linearGradient>
        </defs>
        
        {/* Background Grid Lines */}
        <line x1="80" y1="10" x2="380" y2="10" stroke="var(--border)" strokeWidth="1" strokeDasharray="3 3" />
        <line x1="80" y1="55" x2="380" y2="55" stroke="var(--border)" strokeWidth="1" strokeDasharray="3 3" />
        <line x1="80" y1="100" x2="380" y2="100" stroke="var(--border)" strokeWidth="1" strokeDasharray="3 3" />
        
        {/* Gemini Bar */}
        <text x="0" y="32" fill="var(--fg)" fontSize="11" fontWeight="600">GEMINI</text>
        {geminiValue ? (
          <>
            <rect 
              x="80" 
              y="16" 
              width={Math.max(12, (geminiPercent / 100) * 300)} 
              height="20" 
              rx="10" 
              fill="url(#geminiGrad)" 
            />
            <text 
              x={Math.max(105, 80 + (geminiPercent / 100) * 300 - 8)} 
              y="30" 
              fill="#fff" 
              fontSize="10" 
              fontWeight="700" 
              textAnchor="end"
            >
              {geminiValue.toFixed(0)}{unit}
            </text>
          </>
        ) : (
          <text x="80" y="32" fill="var(--muted)" fontSize="11">No data</text>
        )}
        
        {/* OpenAI Bar */}
        <text x="0" y="77" fill="var(--fg)" fontSize="11" fontWeight="600">OPENAI</text>
        {openaiValue ? (
          <>
            <rect 
              x="80" 
              y="61" 
              width={Math.max(12, (openaiPercent / 100) * 300)} 
              height="20" 
              rx="10" 
              fill="url(#openaiGrad)" 
            />
            <text 
              x={Math.max(105, 80 + (openaiPercent / 100) * 300 - 8)} 
              y="75" 
              fill="#fff" 
              fontSize="10" 
              fontWeight="700" 
              textAnchor="end"
            >
              {openaiValue.toFixed(0)}{unit}
            </text>
          </>
        ) : (
          <text x="80" y="77" fill="var(--muted)" fontSize="11">No data</text>
        )}
      </svg>
    </div>
  );
}

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [sidebarExpanded, setSidebarExpanded] = useState(false);
  const [isNewRunModalOpen, setIsNewRunModalOpen] = useState(false);
  const [backendConfig, setBackendConfig] = useState(null);
  const [backendStatus, setBackendStatus] = useState('checking');
  const [runs, setRuns] = useState([]);
  
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem('theme');
    if (saved) return saved;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  useEffect(() => {
    document.documentElement.className = theme;
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };
  
  // Dev state for triggering new runs
  const [selectedProvider, setSelectedProvider] = useState('gemini');
  const [selectedModel, setSelectedModel] = useState('gemini-3.1-flash-live-preview');
  const [selectedTransport, setSelectedTransport] = useState('direct-injection');
  const [numTurns, setNumTurns] = useState(10);
  const [runBothInParallel, setRunBothInParallel] = useState(false);

  // Parallel comparison run tracking
  const [compareRunIds, setCompareRunIds] = useState(null); // { gemini, openai }
  const [compareData, setCompareData] = useState(null); // { gemini, openai }

  // Settings screen state
  const [settingsGeminiModel, setSettingsGeminiModel] = useState('');
  const [settingsOpenaiModel, setSettingsOpenaiModel] = useState('');
  const [settingsGoogleApiKey, setSettingsGoogleApiKey] = useState('');
  const [settingsOpenaiApiKey, setSettingsOpenaiApiKey] = useState('');
  const [geminiModelSelect, setGeminiModelSelect] = useState('gemini-3.1-flash-live-preview');
  const [geminiModelCustom, setGeminiModelCustom] = useState('');
  const [openaiModelSelect, setOpenaiModelSelect] = useState('gpt-realtime-2');
  const [openaiModelCustom, setOpenaiModelCustom] = useState('');
  const [geminiSaveMsg, setGeminiSaveMsg] = useState('');
  const [openaiSaveMsg, setOpenaiSaveMsg] = useState('');
  const [settingsUtterances, setSettingsUtterances] = useState([]);
  const [rawArgsState, setRawArgsState] = useState({});
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [utterancesSaveMsg, setUtterancesSaveMsg] = useState('');
  const [resetMsg, setResetMsg] = useState('');
  
  // Detailed Run Inspection
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [selectedRunData, setSelectedRunData] = useState(null);
  
  // States for comparing two runs
  const [compareSelection, setCompareSelection] = useState([]);
  const [activeComparison, setActiveComparison] = useState(null);
  const [loadingComparison, setLoadingComparison] = useState(false);

  const selectedRunIdRef = useRef(null);
  const activeComparisonRef = useRef(null);

  useEffect(() => {
    selectedRunIdRef.current = selectedRunId;
  }, [selectedRunId]);

  useEffect(() => {
    activeComparisonRef.current = activeComparison;
  }, [activeComparison]);

  const handleTriggerComparison = useCallback((runId1, runId2) => {
    setLoadingComparison(true);
    Promise.all([
      fetch(`${backendUrl}/api/runs/${runId1}`).then((res) => res.json()),
      fetch(`${backendUrl}/api/runs/${runId2}`).then((res) => res.json())
    ])
      .then(([run1, run2]) => {
        setActiveComparison({ run1, run2 });
        setLoadingComparison(false);
      })
      .catch((err) => {
        console.error('Error fetching runs for comparison:', err);
        setLoadingComparison(false);
        alert('Failed to load runs for comparison.');
      });
  }, []);

  const backendUrl = ''; // Relative path for proxy or served directly

  // Effect to load detailed run when selected
  useEffect(() => {
    if (!selectedRunId) {
      setSelectedRunData(null);
      return;
    }
    fetch(`${backendUrl}/api/runs/${selectedRunId}`)
      .then((res) => res.json())
      .then((data) => setSelectedRunData(data))
      .catch((err) => console.error('Error fetching run details:', err));
  }, [selectedRunId]);

  // Synchronize hash state with tab/inspect/compare states
  useEffect(() => {
    const handleHashChange = () => {
      let hash = window.location.hash || '#/dashboard';
      if (hash.startsWith('#/launcher') || hash.startsWith('#/metrics')) {
        window.location.hash = '#/dashboard';
        return;
      }
      if (hash.startsWith('#/history')) {
        window.location.hash = hash.replace('#/history', '#/runs');
        return;
      }
      
      if (hash.startsWith('#/dashboard')) {
        setActiveTab('dashboard');
        setSelectedRunId(null);
        setActiveComparison(null);
      } else if (hash.startsWith('#/settings')) {
        setActiveTab('settings');
        setSelectedRunId(null);
        setActiveComparison(null);
      } else if (hash.startsWith('#/runs')) {
        setActiveTab('runs');
        const parts = hash.split('/');
        if (parts[2] === 'inspect' && parts[3]) {
          setSelectedRunId(parts[3]);
          setActiveComparison(null);
        } else if (parts[2] === 'compare' && parts[3] && parts[4]) {
          setSelectedRunId(null);
          handleTriggerComparison(parts[3], parts[4]);
        } else {
          setSelectedRunId(null);
          setActiveComparison(null);
          setCompareSelection([]);
        }
      }
    };

    window.addEventListener('hashchange', handleHashChange);
    handleHashChange();

    return () => window.removeEventListener('hashchange', handleHashChange);
  }, [handleTriggerComparison]);

  useEffect(() => {
    // Fetch API Config and Health
    fetch(`${backendUrl}/api/health`)
      .then((res) => {
        if (res.ok) {
          setBackendStatus('connected');
        } else {
          setBackendStatus('error');
        }
      })
      .catch(() => setBackendStatus('disconnected'));

    fetch(`${backendUrl}/api/config`)
      .then((res) => res.json())
      .then((data) => {
        setBackendConfig(data);
        if (data.gemini_model) {
          setSelectedModel(data.gemini_model);
        }
      })
      .catch((err) => console.error('Error fetching backend config:', err));

    fetch(`${backendUrl}/api/runs`)
      .then((res) => res.json())
      .then((data) => setRuns(data))
      .catch((err) => console.error('Error fetching runs:', err));
  }, []);

  const [runningId, setRunningId] = useState(null);
  const [runStatus, setRunStatus] = useState(null);
  const [logs, setLogs] = useState([
    { time: new Date().toLocaleTimeString(), text: 'Ready to launch. Select a provider and click "Start Scripted Run".' }
  ]);

  const logsEndRef = useRef(null);
  const lastPollMsgRef = useRef('');

  const addLog = (text) => {
    setLogs((prev) => [...prev, { time: new Date().toLocaleTimeString(), text }]);
  };

  // Like addLog, but skips re-logging the exact same status line on consecutive polls.
  const addPollLog = (text) => {
    if (text === lastPollMsgRef.current) return;
    lastPollMsgRef.current = text;
    addLog(text);
  };

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ block: 'nearest' });
  }, [logs]);

  const pollRunStatus = (runId) => {
    fetch(`${backendUrl}/api/runs/${runId}`)
      .then((res) => res.json())
      .then((data) => {
        setRunStatus(data.status);
        if (selectedRunIdRef.current === runId) {
          setSelectedRunData(data);
        }
        if (data.status === 'completed' || data.status === 'failed') {
          addLog(`Run ${data.status.toUpperCase()}!`);
          setRunningId(null);
          // Refresh runs list
          fetch(`${backendUrl}/api/runs`)
            .then((res) => res.json())
            .then((d) => setRuns(d));
        } else {
          const turns = data.turns || [];
          const lastTurn = turns.length > 0 ? turns[turns.length - 1] : null;
          const turnNum = turns.length;

          let logMsg;
          if (!lastTurn) {
            logMsg = `Status: ${data.status.toUpperCase()}. Waiting for the first turn to start...`;
          } else if (lastTurn.audio_completed_received_at == null) {
            // Turn is in flight
            if (!lastTurn.first_audio_received_at) {
              logMsg = `Turn ${turnNum} (${lastTurn.utterance_id}): sent to agent — "${lastTurn.text_input.slice(0, 50)}" — awaiting response...`;
            } else {
              logMsg = `Turn ${turnNum} (${lastTurn.utterance_id}): receiving response (TTFA ${Math.round(lastTurn.time_to_first_audio_ms)}ms)`;
              if (lastTurn.transcript_output) {
                logMsg += ` — "${lastTurn.transcript_output.slice(0, 60)}"`;
              }
            }
          } else {
            // Turn finished
            logMsg = `Turn ${turnNum} (${lastTurn.utterance_id}) complete`;
            if (lastTurn.transcript_output) {
              logMsg += ` — received: "${lastTurn.transcript_output.slice(0, 60)}"`;
            }
            if (lastTurn.time_to_first_audio_ms != null) {
              logMsg += ` | TTFA: ${Math.round(lastTurn.time_to_first_audio_ms)}ms`;
            }
            if (lastTurn.tool_call_details) {
              const tc = lastTurn.tool_call_details;
              logMsg += ` | tool: ${tc.name}${tc.latency_ms != null ? ` (${Math.round(tc.latency_ms)}ms)` : ''}`;
            }
          }
          addPollLog(logMsg);
          // Continue polling
          setTimeout(() => pollRunStatus(runId), 2000);
        }
      })
      .catch((err) => {
        console.error('Error polling run:', err);
        setRunningId(null);
      });
  };

  const pollCompareStatus = (geminiRunId, openaiRunId) => {
    Promise.all([
      fetch(`${backendUrl}/api/runs/${geminiRunId}`).then((res) => res.json()),
      fetch(`${backendUrl}/api/runs/${openaiRunId}`).then((res) => res.json())
    ])
      .then(([geminiData, openaiData]) => {
        const isDone = (d) => d.status === 'completed' || d.status === 'failed';
        const summarize = (label, d) => `${label}: ${d.status?.toUpperCase()} (turns: ${d.turns ? d.turns.length : 0})`;
        addLog(`${summarize('Gemini', geminiData)} | ${summarize('OpenAI', openaiData)}`);

        if (activeComparisonRef.current && 
            (activeComparisonRef.current.run1.run_id === geminiRunId && activeComparisonRef.current.run2.run_id === openaiRunId)) {
          setActiveComparison({ run1: geminiData, run2: openaiData });
        }

        if (isDone(geminiData) && isDone(openaiData)) {
          addLog('Both comparison runs finished.');
          setCompareData({ gemini: geminiData, openai: openaiData });
          setCompareRunIds(null);
          fetch(`${backendUrl}/api/runs`)
            .then((res) => res.json())
            .then((d) => setRuns(d));
        } else {
          setTimeout(() => pollCompareStatus(geminiRunId, openaiRunId), 2000);
        }
      })
      .catch((err) => {
        console.error('Error polling comparison runs:', err);
        setCompareRunIds(null);
      });
  };

  const handleStartRun = () => {
    if (runningId || compareRunIds) return;

    setLogs([]);
    lastPollMsgRef.current = '';
    setCompareData(null);

    if (runBothInParallel) {
      const geminiModel = backendConfig?.gemini_model || 'gemini-3.1-flash-live-preview';
      const openaiModel = backendConfig?.openai_model || 'gpt-realtime-2';
      addLog(`Requesting parallel comparison run: gemini (${geminiModel}) vs openai (${openaiModel}), ${numTurns} turns each...`);

      fetch(`${backendUrl}/api/run/compare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          gemini_model: geminiModel,
          openai_model: openaiModel,
          transport: selectedTransport,
          num_turns: numTurns
        })
      })
        .then((res) => res.json())
        .then((data) => {
          if (data.gemini_run_id && data.openai_run_id) {
            setCompareRunIds({ gemini: data.gemini_run_id, openai: data.openai_run_id });
            addLog(`Comparison runs started. Gemini: ${data.gemini_run_id}, OpenAI: ${data.openai_run_id}`);
            pollCompareStatus(data.gemini_run_id, data.openai_run_id);
            
            // Navigate to Runs compare page
            setIsNewRunModalOpen(false);
            window.location.hash = `#/runs/compare/${data.gemini_run_id}/${data.openai_run_id}`;
          } else {
            addLog(`Failed to start comparison run: ${data.detail || 'unknown error'}`);
          }
        })
        .catch((err) => {
          addLog(`Connection error: ${err.message}`);
        });
      return;
    }

    addLog(`Requesting new run for ${selectedProvider} (${selectedModel}), ${numTurns} turns...`);

    fetch(`${backendUrl}/api/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider: selectedProvider,
        model: selectedModel,
        transport: selectedTransport,
        num_turns: numTurns
      })
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.run_id) {
          setRunningId(data.run_id);
          addLog(`Run started in background. ID: ${data.run_id}`);
          pollRunStatus(data.run_id);

          // Navigate to Runs inspect page
          setIsNewRunModalOpen(false);
          window.location.hash = `#/runs/inspect/${data.run_id}`;
        } else {
          addLog(`Failed to start run: ${data.detail || 'unknown error'}`);
        }
      })
      .catch((err) => {
        addLog(`Connection error: ${err.message}`);
      });
  };

  const handleStopRun = () => {
    if (compareRunIds) {
      addLog(`Requesting stop for comparison runs ${compareRunIds.gemini} / ${compareRunIds.openai}...`);
      Promise.all([
        fetch(`${backendUrl}/api/run/${compareRunIds.gemini}/stop`, { method: 'POST' }),
        fetch(`${backendUrl}/api/run/${compareRunIds.openai}/stop`, { method: 'POST' })
      ])
        .then(() => addLog('Stop request sent successfully.'))
        .catch((err) => addLog(`Error requesting stop: ${err.message}`));
      return;
    }

    if (!runningId) return;

    addLog(`Requesting stop for run ${runningId}...`);

    fetch(`${backendUrl}/api/run/${runningId}/stop`, {
      method: 'POST'
    })
      .then((res) => {
        if (res.ok) {
          addLog(`Stop request sent successfully.`);
        } else {
          addLog(`Failed to stop run: server returned status ${res.status}`);
        }
      })
      .catch((err) => {
        addLog(`Error requesting stop: ${err.message}`);
      });
  };

  useEffect(() => {
    if (activeTab !== 'settings' || settingsLoaded) return;

    Promise.all([
      fetch(`${backendUrl}/api/settings`).then((res) => res.json()),
      fetch(`${backendUrl}/api/utterances/json`).then((res) => res.json())
    ])
      .then(([settingsData, utterancesData]) => {
        setSettingsGoogleApiKey(settingsData.google_api_key || '');
        setSettingsOpenaiApiKey(settingsData.openai_api_key || '');

        const gModel = settingsData.gemini_model || '';
        if (gModel === '' || ['gemini-3.1-flash-live-preview', 'gemini-2.5-flash', 'gemini-2.5-flash-8b', 'gemini-2.0-flash-exp'].includes(gModel)) {
          setGeminiModelSelect(gModel || 'gemini-3.1-flash-live-preview');
          setGeminiModelCustom('');
        } else {
          setGeminiModelSelect('custom');
          setGeminiModelCustom(gModel);
        }

        const oModel = settingsData.openai_model || '';
        if (oModel === '' || ['gpt-realtime-2', 'gpt-4o-realtime-preview', 'gpt-4o-mini-realtime-preview'].includes(oModel)) {
          setOpenaiModelSelect(oModel || 'gpt-realtime-2');
          setOpenaiModelCustom('');
        } else {
          setOpenaiModelSelect('custom');
          setOpenaiModelCustom(oModel);
        }

        const rawArgs = {};
        if (Array.isArray(utterancesData)) {
          utterancesData.forEach((u, idx) => {
            rawArgs[idx] = u.expect?.args ? JSON.stringify(u.expect.args) : '';
          });
        }
        setRawArgsState(rawArgs);

        setSettingsUtterances(Array.isArray(utterancesData) ? utterancesData : []);
        setSettingsLoaded(true);
      })
      .catch((err) => console.error('Error loading settings:', err));
  }, [activeTab, settingsLoaded]);

  const handleSaveModelSettings = (provider) => {
    const isGemini = provider === 'gemini';
    const setMsg = isGemini ? setGeminiSaveMsg : setOpenaiSaveMsg;
    setMsg('Saving...');

    const geminiModel = geminiModelSelect === 'custom' ? geminiModelCustom : geminiModelSelect;
    const openaiModel = openaiModelSelect === 'custom' ? openaiModelCustom : openaiModelSelect;

    fetch(`${backendUrl}/api/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        gemini_model: geminiModel,
        openai_model: openaiModel,
        google_api_key: isGemini ? settingsGoogleApiKey : '••••••••',
        openai_api_key: !isGemini ? settingsOpenaiApiKey : '••••••••'
      })
    })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to save settings');
        return res.json();
      })
      .then(() => {
        setMsg('Saved.');
        fetch(`${backendUrl}/api/status`)
          .then((res) => res.json())
          .then((cfg) => setBackendConfig(cfg))
          .catch((e) => console.error('Error updating config status:', e));
        setTimeout(() => setMsg(''), 2000);
      })
      .catch((err) => setMsg(`Error: ${err.message}`));
  };

  const handleSaveUtterances = () => {
    setUtterancesSaveMsg('Saving...');
    fetch(`${backendUrl}/api/utterances/json`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ utterances: settingsUtterances })
    })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to save utterances');
        return res.json();
      })
      .then((data) => {
        setUtterancesSaveMsg(`Saved (${data.count} utterances).`);
        setTimeout(() => setUtterancesSaveMsg(''), 3000);
      })
      .catch((err) => setUtterancesSaveMsg(`Error: ${err.message}`));
  };

  const updateUtteranceField = (index, field, value) => {
    const updated = [...settingsUtterances];
    updated[index] = { ...updated[index], [field]: value };
    setSettingsUtterances(updated);
  };

  const updateUtteranceExpectType = (index, type) => {
    const updated = [...settingsUtterances];
    const current = updated[index];
    if (type === 'none') {
      const { expect, ...rest } = current;
      updated[index] = rest;
    } else if (type === 'response') {
      updated[index] = { ...current, expect: { response: current.expect?.response || '' } };
    } else if (type === 'tool') {
      updated[index] = { ...current, expect: { tool: current.expect?.tool || '', args: current.expect?.args || {} } };
    }
    setSettingsUtterances(updated);
  };

  const updateUtteranceExpectField = (index, field, value) => {
    const updated = [...settingsUtterances];
    const current = updated[index];
    updated[index] = {
      ...current,
      expect: {
        ...current.expect,
        [field]: value
      }
    };
    setSettingsUtterances(updated);
  };

  const handleArgsChange = (index, textValue) => {
    setRawArgsState((prev) => ({ ...prev, [index]: textValue }));
    try {
      const parsed = JSON.parse(textValue);
      updateUtteranceExpectField(index, 'args', parsed);
    } catch (e) {
      // Invalid JSON is fine while typing
    }
  };

  const handleDeleteRun = (runId) => {
    if (!window.confirm('Are you sure you want to permanently delete this experiment run?')) {
      return;
    }
    
    fetch(`${backendUrl}/api/runs/${runId}`, {
      method: 'DELETE'
    })
      .then((res) => {
        if (res.ok) {
          if (selectedRunId === runId) {
            setSelectedRunId(null);
            window.location.hash = '#/runs';
          }
          // Refresh runs list
          fetch(`${backendUrl}/api/runs`)
            .then((res) => res.json())
            .then((d) => setRuns(d));
        } else {
          alert('Failed to delete run.');
        }
      })
      .catch((err) => {
        console.error('Error deleting run:', err);
        alert(`Error: ${err.message}`);
      });
  };

  const handleResetDatabase = () => {
    if (!window.confirm('This will permanently delete ALL run history, transcripts, and audio from disk and reset the database. This cannot be undone. Continue?')) {
      return;
    }

    setResetMsg('Resetting...');
    fetch(`${backendUrl}/api/database/reset`, { method: 'POST' })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to reset database.');
        return res.json();
      })
      .then(() => {
        setRuns([]);
        setSelectedRunId(null);
        setSelectedRunData(null);
        window.location.hash = '#/runs';
        setResetMsg('All data has been reset.');
        setTimeout(() => setResetMsg(''), 4000);
      })
      .catch((err) => {
        console.error('Error resetting database:', err);
        setResetMsg(`Error: ${err.message}`);
      });
  };

  const getActivePipelineStep = () => {
    if (!runningId && !compareRunIds) return 0;
    if (logs.length === 0) return 1;
    const lastLog = logs[logs.length - 1]?.text || '';
    if (lastLog.includes('started in background') || lastLog.includes('Waiting for the first turn')) {
      return 1;
    }
    if (lastLog.includes('sent to agent') || lastLog.includes('awaiting response')) {
      return 2;
    }
    if (lastLog.includes('receiving response') || lastLog.includes('receiving')) {
      return 3;
    }
    if (lastLog.includes('complete') || lastLog.includes('Metrics') || lastLog.includes('finished')) {
      return 4;
    }
    return 1;
  };

  const needsApiKeySetup = backendConfig?.providers?.length > 0
    && backendConfig.providers.every((p) => !backendConfig.has_api_key?.[p]);

  const noModelsConfigured = backendConfig && (!backendConfig.gemini_model || !backendConfig.openai_model);

  return (
    <div className="app-container">
      {/* Dynamic Background Glow Orbs */}
      <div className="mesh-gradient-container">
        <div className="glow-orb glow-orb-1"></div>
        <div className="glow-orb glow-orb-2"></div>
        <div className="glow-orb glow-orb-3"></div>
      </div>
      <header className="header">
        <div className="header-title">
          <img src={logoUrl} alt="VoxArena" className="header-logo" />
        </div>
        
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          <div className="api-status">
            <span className={`status-dot ${backendStatus === 'connected' ? 'connected' : 'disconnected'}`}></span>
            <span style={{ color: 'var(--muted)', fontSize: 13 }}>
              {backendStatus === 'connected' ? 'API connected' : 'API disconnected'}
            </span>
          </div>
          <button
            className="theme-toggle-btn"
            onClick={toggleTheme}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg)' }}
            title={theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
          >
            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        </div>
      </header>

      <div className="app-body">
        <aside className={`sidebar ${sidebarExpanded ? 'expanded' : ''}`}>
          <div className="sidebar-top">
            <nav className="sidebar-nav">
              <button
                className={`sidebar-btn ${activeTab === 'dashboard' ? 'active' : ''}`}
                onClick={() => { window.location.hash = '#/dashboard'; }}
                title="Dashboard"
                aria-label="Dashboard"
              >
                <LayoutDashboard size={18} />
                {sidebarExpanded && <span className="sidebar-btn-label">Dashboard</span>}
              </button>
              <button
                className={`sidebar-btn ${activeTab === 'runs' ? 'active' : ''}`}
                onClick={() => { window.location.hash = '#/runs'; }}
                title="Benchmark Runs"
                aria-label="Benchmark Runs"
              >
                <History size={18} />
                {sidebarExpanded && <span className="sidebar-btn-label">Runs</span>}
              </button>
            </nav>
          </div>

          <div className="sidebar-bottom">
            <button
              className={`sidebar-btn ${activeTab === 'settings' ? 'active' : ''}`}
              onClick={() => { window.location.hash = '#/settings'; }}
              title="Settings"
              aria-label="Settings"
            >
              <Settings size={18} />
              {sidebarExpanded && <span className="sidebar-btn-label">Settings</span>}
            </button>

            <button 
              className="sidebar-toggle-btn"
              onClick={() => setSidebarExpanded(!sidebarExpanded)}
              title={sidebarExpanded ? "Collapse Sidebar" : "Expand Sidebar"}
              aria-label={sidebarExpanded ? "Collapse Sidebar" : "Expand Sidebar"}
              style={{ marginTop: 6 }}
            >
              {sidebarExpanded ? <ChevronLeft size={18} /> : <ChevronRight size={18} />}
            </button>
          </div>
        </aside>

        <main className="main-content">
        {activeTab === 'dashboard' && needsApiKeySetup && (
          <div className="setup-banner">
            <div>
              <strong>Welcome to VoxArena!</strong> No API keys are configured yet, so runs will fail.
              Add your provider API keys to get started.
            </div>
            <button className="btn btn-primary" onClick={() => { window.location.hash = '#/settings'; }}>
              Set up API Keys
            </button>
          </div>
        )}
        {activeTab === 'dashboard' && noModelsConfigured && (
          <div className="setup-banner danger-zone">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <AlertCircle size={16} style={{ color: 'var(--error)', flexShrink: 0 }} />
              <div>
                <strong>Configuration Warning:</strong> No voice models are configured. Please set up model names for Gemini and OpenAI to run benchmarks.
              </div>
            </div>
            <button className="btn btn-primary" onClick={() => { window.location.hash = '#/settings'; }}>
              Configure Models
            </button>
          </div>
        )}
        {activeTab === 'dashboard' && (() => {
          const completedRuns = runs.filter(r => r.status === 'completed');
          
          const getAggregates = (provider) => {
            const pRuns = completedRuns.filter(r => r.provider === provider);
            if (pRuns.length === 0) return null;
            
            const ttfas = pRuns.map(r => r.aggregate_metrics?.average_ttfa_ms).filter(v => v != null);
            const accuracies = pRuns.map(r => r.aggregate_metrics?.tool_call_accuracy_rate).filter(v => v != null);
            const interruptions = pRuns.map(r => r.aggregate_metrics?.average_interruption_stop_latency_ms).filter(v => v != null);
            const hallucinations = pRuns.map(r => r.aggregate_metrics?.hallucination_count || 0);
            
            return {
              avgTtfa: ttfas.length ? sum(ttfas) / ttfas.length : null,
              avgAccuracy: accuracies.length ? (sum(accuracies) / accuracies.length) * 100 : null,
              avgInterruption: interruptions.length ? sum(interruptions) / interruptions.length : null,
              totalHallucinations: sum(hallucinations),
              runCount: pRuns.length
            };
          };

          const sum = arr => arr.reduce((a, b) => a + b, 0);
          
          const geminiStats = getAggregates('gemini');
          const openaiStats = getAggregates('openai');
          const hasStats = geminiStats || openaiStats;

          return (
            <div className="scrollable-tab-container">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <div>
                  <h2 style={{ fontSize: 18, fontWeight: 700 }}>Arena Dashboard</h2>
                  <p style={{ color: 'var(--muted)', fontSize: 13 }}>Comparative aggregates of all benchmark runs</p>
                </div>
                <button 
                  className="btn btn-primary" 
                  onClick={() => setIsNewRunModalOpen(true)}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
                >
                  <Plus size={16} />
                  <span>Start New Run</span>
                </button>
              </div>

              {!hasStats ? (
                <div className="card" style={{ marginBottom: 16 }}>
                  <div className="card-header">
                    <span className="card-title">Welcome to VoxArena</span>
                  </div>
                  <div className="card-body" style={{ textAlign: 'center', padding: '40px 0' }}>
                    <p style={{ color: 'var(--muted)', marginBottom: 16 }}>
                      No completed benchmark runs found. Let's start by launching your first test!
                    </p>
                    <button className="btn btn-primary" onClick={() => setIsNewRunModalOpen(true)}>
                      Start Your First Run
                    </button>
                  </div>
                </div>
              ) : (
                <div>
                  <div className="grid-3" style={{ marginBottom: 16 }}>
                    <div className="card">
                      <div className="card-header"><span className="card-title">Latency Showdown (TTFA)</span></div>
                      <div className="card-body">
                        <CustomBarChart 
                          geminiValue={geminiStats?.avgTtfa} 
                          openaiValue={openaiStats?.avgTtfa} 
                          title="Average Response Delay" 
                          unit="ms" 
                          lowerIsBetter={true} 
                        />
                        <div className="metric-label" style={{ marginTop: 12 }}>Lower is better. Measures transport delay to first audio response.</div>
                      </div>
                    </div>

                    <div className="card">
                      <div className="card-header"><span className="card-title">Tool-Call Accuracy</span></div>
                      <div className="card-body">
                        <CustomBarChart 
                          geminiValue={geminiStats?.avgAccuracy} 
                          openaiValue={openaiStats?.avgAccuracy} 
                          title="Tool Accuracy Rate" 
                          unit="%" 
                          lowerIsBetter={false} 
                        />
                        <div className="metric-label" style={{ marginTop: 12 }}>Higher is better. Percentage of correct tool calls.</div>
                      </div>
                    </div>

                    <div className="card">
                      <div className="card-header"><span className="card-title">Interruption Stop Latency</span></div>
                      <div className="card-body">
                        <CustomBarChart 
                          geminiValue={geminiStats?.avgInterruption} 
                          openaiValue={openaiStats?.avgInterruption} 
                          title="Average Interruption Stop Delay" 
                          unit="ms" 
                          lowerIsBetter={true} 
                        />
                        <div className="metric-label" style={{ marginTop: 12 }}>Lower is better. Time taken to stop speaking upon user interruption.</div>
                      </div>
                    </div>
                  </div>

                  <div className="grid-2" style={{ marginBottom: 16 }}>
                    <div className="card">
                      <div className="card-header"><span className="card-title">Fact Hallucinations</span></div>
                      <div className="card-body">
                        <table className="runs-table" style={{ margin: 0 }}>
                          <thead>
                            <tr>
                              <th>Provider</th>
                              <th>Experiment Runs</th>
                              <th>Total Hallucinations</th>
                            </tr>
                          </thead>
                          <tbody>
                            {geminiStats && (
                              <tr>
                                <td>GEMINI</td>
                                <td>{geminiStats.runCount}</td>
                                <td>{geminiStats.totalHallucinations}</td>
                              </tr>
                            )}
                            {openaiStats && (
                              <tr>
                                <td>OPENAI</td>
                                <td>{openaiStats.runCount}</td>
                                <td>{openaiStats.totalHallucinations}</td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    <div className="card">
                      <div className="card-header"><span className="card-title">Recent Run Log</span></div>
                      <div className="card-body" style={{ overflowY: 'auto', maxHeight: '180px', padding: 0 }}>
                        <table className="runs-table" style={{ margin: 0 }}>
                          <thead>
                            <tr>
                              <th>Run ID</th>
                              <th>Model</th>
                              <th>Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {runs.slice(0, 5).map(r => (
                              <tr 
                                key={r.run_id} 
                                style={{ cursor: 'pointer' }}
                                onClick={() => { window.location.hash = `#/runs/inspect/${r.run_id}`; }}
                              >
                                <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{r.run_id.slice(0, 12)}...</td>
                                <td>{r.model}</td>
                                <td>
                                  <span className={`status-badge ${r.status}`}>{r.status}</span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })()}

        {activeTab === 'runs' && (
          <div className="scrollable-tab-container">
            {loadingComparison ? (
              <div className="card">
                <div className="card-body">
                  <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '60px 0' }}>
                    Loading comparison details...
                  </p>
                </div>
              </div>
            ) : activeComparison ? (
              // Side-by-side Comparison View
              <div className="card">
                <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <button 
                      className="btn-icon" 
                      onClick={() => { window.location.hash = '#/runs'; }}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg)', padding: 4, display: 'flex', alignItems: 'center' }}
                      title="Back to Runs"
                    >
                      <ArrowLeft size={18} />
                    </button>
                    <span className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <ArrowRightLeft size={16} />
                      Side-by-Side Run Comparison
                    </span>
                  </div>
                </div>
                <div className="card-body">
                  {/* Split Summary */}
                  <div className="compare-split-view">
                    <div className="comparison-card" style={{ borderLeft: '4px solid var(--color-primary)' }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-primary)', letterSpacing: '0.05em' }}>RUN 1 (GEMINI)</div>
                      <div style={{ fontSize: 15, fontWeight: 600, marginTop: 4 }}>{activeComparison.run1.model}</div>
                      <div style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'var(--font-mono)' }}>ID: {activeComparison.run1.run_id}</div>
                      
                      <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid var(--border)', paddingTop: 10, marginTop: 10 }}>
                        <div>
                          <div style={{ fontSize: 10, color: 'var(--muted)' }}>Avg TTFA</div>
                          <div style={{ fontWeight: 700, fontSize: 16, fontFamily: 'var(--font-mono)', color: 'var(--fg)' }}>
                            {activeComparison.run1.metrics?.average_ttfa_ms ? `${activeComparison.run1.metrics.average_ttfa_ms.toFixed(0)} ms` : '--'}
                          </div>
                        </div>
                        <div>
                          <div style={{ fontSize: 10, color: 'var(--muted)' }}>Tool Accuracy</div>
                          <div style={{ fontWeight: 700, fontSize: 16, fontFamily: 'var(--font-mono)', color: 'var(--fg)' }}>
                            {activeComparison.run1.metrics?.tool_call_accuracy_rate != null ? `${(activeComparison.run1.metrics.tool_call_accuracy_rate * 100).toFixed(0)}%` : '--'}
                          </div>
                        </div>
                        <div>
                          <div style={{ fontSize: 10, color: 'var(--muted)' }}>Hallucinations</div>
                          <div style={{ fontWeight: 700, fontSize: 16, fontFamily: 'var(--font-mono)', color: activeComparison.run1.metrics?.hallucination_count > 0 ? 'var(--error)' : 'var(--fg)' }}>
                            {activeComparison.run1.metrics?.hallucination_count ?? 0}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="comparison-card" style={{ borderLeft: '4px solid var(--color-secondary)' }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-secondary)', letterSpacing: '0.05em' }}>RUN 2 (OPENAI)</div>
                      <div style={{ fontSize: 15, fontWeight: 600, marginTop: 4 }}>{activeComparison.run2.model}</div>
                      <div style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'var(--font-mono)' }}>ID: {activeComparison.run2.run_id}</div>
                      
                      <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid var(--border)', paddingTop: 10, marginTop: 10 }}>
                        <div>
                          <div style={{ fontSize: 10, color: 'var(--muted)' }}>Avg TTFA</div>
                          <div style={{ fontWeight: 700, fontSize: 16, fontFamily: 'var(--font-mono)', color: 'var(--fg)' }}>
                            {activeComparison.run2.metrics?.average_ttfa_ms ? `${activeComparison.run2.metrics.average_ttfa_ms.toFixed(0)} ms` : '--'}
                          </div>
                        </div>
                        <div>
                          <div style={{ fontSize: 10, color: 'var(--muted)' }}>Tool Accuracy</div>
                          <div style={{ fontWeight: 700, fontSize: 16, fontFamily: 'var(--font-mono)', color: 'var(--fg)' }}>
                            {activeComparison.run2.metrics?.tool_call_accuracy_rate != null ? `${(activeComparison.run2.metrics.tool_call_accuracy_rate * 100).toFixed(0)}%` : '--'}
                          </div>
                        </div>
                        <div>
                          <div style={{ fontSize: 10, color: 'var(--muted)' }}>Hallucinations</div>
                          <div style={{ fontWeight: 700, fontSize: 16, fontFamily: 'var(--font-mono)', color: activeComparison.run2.metrics?.hallucination_count > 0 ? 'var(--error)' : 'var(--fg)' }}>
                            {activeComparison.run2.metrics?.hallucination_count ?? 0}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Live comparison logs if active */}
                  {(compareRunIds || activeComparison.run1.status === 'running' || activeComparison.run2.status === 'running') && (
                    <div className="card" style={{ marginTop: 16 }}>
                      <div className="card-header">
                        <span className="card-title">Live Comparison Logs</span>
                      </div>
                      <div className="card-body" style={{ display: 'flex', flexDirection: 'column', height: '200px' }}>
                        <div className="terminal" style={{ flex: 1 }}>
                          {logs.map((log, idx) => (
                            <div className="terminal-line" key={idx}>
                              <span className="terminal-timestamp">[{log.time}]</span>
                              <span>{log.text}</span>
                            </div>
                          ))}
                          <div ref={logsEndRef} />
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Side-by-Side Turn list */}
                  <div style={{ marginTop: 20 }}>
                    <h3 style={{ fontSize: 13, fontWeight: 600, borderBottom: '1px solid var(--border)', paddingBottom: 6, marginBottom: 12 }}>
                      Turn Comparison
                    </h3>
                    
                    {activeComparison.run1.turns.map((turn1, index) => {
                      const turn2 = activeComparison.run2.turns[index] || {};
                      const passed1 = !!turn1.transcript_output && turn1.evaluation_passed !== false;
                      const passed2 = !!turn2.transcript_output && turn2.evaluation_passed !== false;
                      
                      return (
                        <div key={index} style={{ borderBottom: '1px solid var(--border)', paddingBottom: 16, marginBottom: 16 }}>
                          <div style={{ marginBottom: 8 }}>
                            <span className="header-badge">TURN {turn1.utterance_id}</span>
                            <span style={{ fontSize: 12, marginLeft: 8, color: 'var(--muted)' }}>Prompt: "{turn1.text_input}"</span>
                          </div>
                          
                          <div className="compare-split-view" style={{ marginTop: 6 }}>
                            <div className="comparison-card" style={{ borderLeft: `3px solid ${passed1 ? 'var(--success)' : 'var(--error)'}` }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--color-primary)' }}>GEMINI</span>
                                <span className={`status-badge ${passed1 ? 'completed' : 'failed'}`}>{passed1 ? 'PASS' : 'FAIL'}</span>
                              </div>
                              <div style={{ fontSize: 13, margin: '8px 0', minHeight: 40 }}>
                                {turn1.transcript_output || <span style={{ fontStyle: 'italic', color: 'var(--muted)' }}>(No speech output returned)</span>}
                              </div>
                              <div style={{ display: 'flex', gap: 12, fontSize: 11, color: 'var(--muted)', borderTop: '1px dashed var(--border)', paddingTop: 6 }}>
                                <div>TTFA: <strong>{turn1.time_to_first_audio_ms ? `${turn1.time_to_first_audio_ms.toFixed(0)}ms` : '—'}</strong></div>
                                <div>Int Stop: <strong>{turn1.interruption_stop_latency_ms ? `${turn1.interruption_stop_latency_ms.toFixed(0)}ms` : '—'}</strong></div>
                                <div>Tool: <strong>{turn1.tool_call_details ? turn1.tool_call_details.name : '—'}</strong></div>
                              </div>
                              {turn1.audio_output_path && (
                                <div style={{ marginTop: 8 }}>
                                  <AudioPlayer
                                    src={`/api/results/${activeComparison.run1.provider}/${activeComparison.run1.run_id}/${turn1.utterance_id}_response.wav`}
                                    latencyMs={turn1.time_to_first_audio_ms}
                                  />
                                </div>
                              )}
                              {turn1.evaluation_notes && (
                                <div style={{ fontSize: 11, color: 'var(--muted)', background: 'rgba(0,0,0,0.05)', padding: '6px 10px', borderRadius: 6, marginTop: 6 }}>
                                  {turn1.evaluation_notes}
                                </div>
                              )}
                            </div>

                            <div className="comparison-card" style={{ borderLeft: `3px solid ${passed2 ? 'var(--success)' : 'var(--error)'}` }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--color-secondary)' }}>OPENAI</span>
                                <span className={`status-badge ${passed2 ? 'completed' : 'failed'}`}>{passed2 ? 'PASS' : 'FAIL'}</span>
                              </div>
                              <div style={{ fontSize: 13, margin: '8px 0', minHeight: 40 }}>
                                {turn2.transcript_output || <span style={{ fontStyle: 'italic', color: 'var(--muted)' }}>(No speech output returned)</span>}
                              </div>
                              <div style={{ display: 'flex', gap: 12, fontSize: 11, color: 'var(--muted)', borderTop: '1px dashed var(--border)', paddingTop: 6 }}>
                                <div>TTFA: <strong>{turn2.time_to_first_audio_ms ? `${turn2.time_to_first_audio_ms.toFixed(0)}ms` : '—'}</strong></div>
                                <div>Int Stop: <strong>{turn2.interruption_stop_latency_ms ? `${turn2.interruption_stop_latency_ms.toFixed(0)}ms` : '—'}</strong></div>
                                <div>Tool: <strong>{turn2.tool_call_details ? turn2.tool_call_details.name : '—'}</strong></div>
                              </div>
                              {turn2.audio_output_path && (
                                <div style={{ marginTop: 8 }}>
                                  <AudioPlayer
                                    src={`/api/results/${activeComparison.run2.provider}/${activeComparison.run2.run_id}/${turn2.utterance_id}_response.wav`}
                                    latencyMs={turn2.time_to_first_audio_ms}
                                  />
                                </div>
                              )}
                              {turn2.evaluation_notes && (
                                <div style={{ fontSize: 11, color: 'var(--muted)', background: 'rgba(0,0,0,0.05)', padding: '6px 10px', borderRadius: 6, marginTop: 6 }}>
                                  {turn2.evaluation_notes}
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            ) : selectedRunId ? (
              // Detailed Inspector View
              <div className="card">
                <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <button 
                      className="btn-icon" 
                      onClick={() => { window.location.hash = '#/runs'; }}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg)', padding: 4, display: 'flex', alignItems: 'center' }}
                      title="Back to Runs"
                    >
                      <ArrowLeft size={18} />
                    </button>
                    <span className="card-title" style={{ fontFamily: 'var(--font-mono)' }}>
                      INSPECT: {selectedRunId.slice(0, 12)}...
                    </span>
                  </div>
                  <button 
                    className="btn-icon" 
                    onClick={() => handleDeleteRun(selectedRunId)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--error)', padding: 6, display: 'flex', alignItems: 'center', borderRadius: 8, transition: 'background-color 0.2s' }}
                    title="Delete Run"
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
                <div className="card-body">
                  {!selectedRunData ? (
                    <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '20px 0' }}>Loading details...</p>
                  ) : (
                    <div>
                      {/* Live pipeline telemetry and logs if active/running */}
                      {(selectedRunData.status === 'running' || selectedRunData.status === 'pending' || runningId === selectedRunId) && (
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: 24 }}>
                          <div className="card">
                            <div className="card-header">
                              <span className="card-title">Live Pipeline Status</span>
                            </div>
                            <div className="card-body">
                              <LivePipelineVisualizer activeStep={getActivePipelineStep()} />
                            </div>
                          </div>
                          
                          <div className="card">
                            <div className="card-header">
                              <span className="card-title">Live Logs</span>
                            </div>
                            <div className="card-body" style={{ display: 'flex', flexDirection: 'column', height: '240px' }}>
                              <div className="terminal" style={{ flex: 1 }}>
                                {logs.map((log, idx) => (
                                  <div className="terminal-line" key={idx}>
                                    <span className="terminal-timestamp">[{log.time}]</span>
                                    <span>{log.text}</span>
                                  </div>
                                ))}
                                <div ref={logsEndRef} />
                              </div>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Summary Row */}
                      <div className="grid-3" style={{ marginBottom: 24 }}>
                        <div>
                          <div className="form-label">Provider / Model</div>
                          <div style={{ fontWeight: 600 }}>{selectedRunData.provider.toUpperCase()} ({selectedRunData.model})</div>
                        </div>
                        <div>
                          <div className="form-label">Run Created At</div>
                          <div>{new Date(selectedRunData.created_at * 1000).toLocaleString()}</div>
                        </div>
                        <div>
                          <div className="form-label">Overall Status</div>
                          <span className={`status-badge ${selectedRunData.status}`}>{selectedRunData.status}</span>
                        </div>
                      </div>

                      <div className="grid-3" style={{ marginBottom: 24 }}>
                        <div>
                          <div className="form-label">Avg TTFA</div>
                          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 600 }}>
                            {selectedRunData.metrics?.average_ttfa_ms ? `${selectedRunData.metrics.average_ttfa_ms.toFixed(0)} ms` : '--'}
                          </div>
                        </div>
                        <div>
                          <div className="form-label">Tool Call Accuracy</div>
                          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 600 }}>
                            {selectedRunData.metrics?.tool_call_accuracy_rate != null ? `${(selectedRunData.metrics.tool_call_accuracy_rate * 100).toFixed(0)}%` : '--'}
                          </div>
                        </div>
                        <div>
                          <div className="form-label">Hallucinations</div>
                          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 600, color: selectedRunData.metrics?.hallucination_count > 0 ? 'var(--error)' : 'inherit' }}>
                            {selectedRunData.metrics?.hallucination_count ?? 0}
                          </div>
                        </div>
                      </div>

                      {/* Turn-by-Turn Logs */}
                      <h3 style={{ fontSize: 14, fontWeight: 600, borderBottom: '1px solid var(--border)', paddingBottom: 8, marginBottom: 16 }}>
                        Turn-by-Turn Script Execution Logs
                      </h3>
                      
                      <div style={{ overflowX: 'auto' }}>
                        <table className="runs-table turn-results-table">
                          <thead>
                            <tr>
                              <th>Turn</th>
                              <th>User (Input)</th>
                              <th>Agent (Transcript)</th>
                              <th>TTFA</th>
                              <th>Int Stop</th>
                              <th>Tool Called</th>
                              <th>Tool Eval</th>
                              <th>Audio</th>
                              <th>Notes</th>
                              <th>Result</th>
                            </tr>
                          </thead>
                          <tbody>
                            {selectedRunData.turns.map((turn, index) => {
                              const passed = !!turn.transcript_output && turn.evaluation_passed !== false;
                              return (
                                <tr key={index} className={passed ? 'row-pass' : 'row-fail'}>
                                  <td><span className="header-badge" style={{ fontSize: 11 }}>{turn.utterance_id}</span></td>
                                  <td style={{ maxWidth: 220 }}>{turn.text_input}</td>
                                  <td style={{ maxWidth: 280, fontStyle: !turn.transcript_output ? 'italic' : 'normal', color: !turn.transcript_output ? 'var(--muted)' : 'inherit' }}>
                                    {turn.transcript_output || "(No speech output returned)"}
                                  </td>
                                  <td style={{ fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>
                                    {turn.time_to_first_audio_ms != null ? `${turn.time_to_first_audio_ms.toFixed(0)}ms` : '—'}
                                  </td>
                                  <td style={{ fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>
                                    {turn.interruption_stop_latency_ms != null ? `${turn.interruption_stop_latency_ms.toFixed(0)}ms` : '—'}
                                  </td>
                                  <td style={{ whiteSpace: 'nowrap' }}>
                                    {turn.tool_call_details ? <code>{turn.tool_call_details.name}</code> : '—'}
                                  </td>
                                  <td>
                                    {turn.tool_call_correct !== null && turn.tool_call_correct !== undefined ? (
                                      <span className={`status-badge ${turn.tool_call_correct ? 'completed' : 'failed'}`}>
                                        {turn.tool_call_correct ? 'CORRECT' : 'INCORRECT'}
                                      </span>
                                    ) : '—'}
                                  </td>
                                  <td style={{ minWidth: 160 }}>
                                    {turn.audio_output_path ? (
                                      <AudioPlayer
                                        src={`/api/results/${selectedRunData.provider}/${selectedRunData.run_id}/${turn.utterance_id}_response.wav`}
                                        latencyMs={turn.time_to_first_audio_ms}
                                      />
                                    ) : '—'}
                                  </td>
                                  <td style={{ maxWidth: 240, fontSize: 12, color: 'var(--muted)' }}>
                                    {turn.evaluation_notes || '—'}
                                  </td>
                                  <td>
                                    <span className={`status-badge ${passed ? 'completed' : 'failed'}`}>
                                      {passed ? 'PASS' : 'FAIL'}
                                    </span>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              // Run List Table
              <div className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderBottom: '1px solid var(--border)', backgroundColor: 'var(--accent-light)' }}>
                  <span className="card-title">Benchmark Runs</span>
                  <div style={{ display: 'flex', gap: 12 }}>
                    <button className="btn btn-primary" onClick={() => setIsNewRunModalOpen(true)} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                      <Plus size={14} /> New Run
                    </button>
                    {compareSelection.length === 2 && (
                      <button 
                        className="btn btn-primary"
                        onClick={() => { window.location.hash = `#/runs/compare/${compareSelection[0]}/${compareSelection[1]}`; }}
                      >
                        Compare Selected ({compareSelection.length})
                      </button>
                    )}
                  </div>
                </div>
                <div className="card-body" style={{ padding: 0 }}>
                  {runs.length === 0 ? (
                    <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '40px 0' }}>
                      No runs found in the results folder.
                    </p>
                  ) : (
                    <table className="runs-table">
                      <thead>
                        <tr>
                          <th style={{ width: 40, textAlign: 'center' }}>Compare</th>
                          <th>Run ID</th>
                          <th>Provider</th>
                          <th>Model</th>
                          <th>Transport</th>
                          <th>Date</th>
                          <th>Status</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {runs.map((run) => {
                          const isSelected = compareSelection.includes(run.run_id);
                          const toggleSelection = (e) => {
                            if (isSelected) {
                              setCompareSelection(compareSelection.filter(id => id !== run.run_id));
                            } else {
                              if (compareSelection.length < 2) {
                                setCompareSelection([...compareSelection, run.run_id]);
                              } else {
                                alert('You can compare a maximum of 2 runs.');
                              }
                            }
                          };

                          return (
                            <tr key={run.run_id}>
                              <td style={{ textAlign: 'center' }}>
                                <input 
                                  type="checkbox" 
                                  checked={isSelected}
                                  onChange={toggleSelection}
                                  disabled={run.status !== 'completed'}
                                />
                              </td>
                              <td><code>{run.run_id.slice(0, 12)}</code></td>
                              <td>{run.provider.toUpperCase()}</td>
                              <td>{run.model}</td>
                              <td>{run.transport}</td>
                              <td>{new Date(run.created_at * 1000).toLocaleString()}</td>
                              <td>
                                <span className={`status-badge ${run.status}`}>
                                  {run.status}
                                </span>
                              </td>
                              <td>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                                  <button 
                                    className="btn" 
                                    style={{ padding: '4px 8px', fontSize: 11 }}
                                    onClick={() => { window.location.hash = `#/runs/inspect/${run.run_id}`; }}
                                  >
                                    Inspect
                                  </button>
                                  <button 
                                    className="btn-icon" 
                                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--error)', padding: 4, display: 'flex', alignItems: 'center', transition: 'color 0.2s' }}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleDeleteRun(run.run_id);
                                    }}
                                    title="Delete Experiment"
                                  >
                                    <Trash2 size={15} />
                                  </button>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'settings' && (
          <div className="scrollable-tab-container">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16, marginBottom: 24 }}>
              {/* Google Gemini Settings */}
              <div className="card" style={{ margin: 0 }}>
                <div className="card-header">
                  <span className="card-title">Google Gemini Configuration</span>
                </div>
                <div className="card-body">
                  <div className="form-group" style={{ marginBottom: 12 }}>
                    <label className="form-label">Google Gemini API Key</label>
                    <input
                      type="password"
                      className="text-input"
                      value={settingsGoogleApiKey}
                      onChange={(e) => setSettingsGoogleApiKey(e.target.value)}
                      placeholder={settingsGoogleApiKey ? "••••••••" : "Enter Google API Key"}
                    />
                  </div>

                  <div className="form-group" style={{ marginBottom: 12 }}>
                    <label className="form-label">Gemini Model</label>
                    <select
                      className="select-input"
                      value={geminiModelSelect}
                      onChange={(e) => setGeminiModelSelect(e.target.value)}
                    >
                      <option value="gemini-3.1-flash-live-preview">Gemini 3.1 Flash Live Preview (Default)</option>
                      <option value="gemini-2.5-flash">Gemini 2.5 Flash</option>
                      <option value="gemini-2.5-flash-8b">Gemini 2.5 Flash 8B</option>
                      <option value="gemini-2.0-flash-exp">Gemini 2.0 Flash Exp</option>
                      <option value="custom">Custom Model...</option>
                    </select>
                  </div>

                  {geminiModelSelect === 'custom' && (
                    <div className="form-group" style={{ marginBottom: 12 }}>
                      <label className="form-label">Custom Gemini Model ID</label>
                      <input
                        type="text"
                        className="text-input"
                        value={geminiModelCustom}
                        onChange={(e) => setGeminiModelCustom(e.target.value)}
                        placeholder="e.g. gemini-3.1-flash-live-preview"
                      />
                    </div>
                  )}

                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 16 }}>
                    <button className="btn btn-primary" onClick={() => handleSaveModelSettings('gemini')}>
                      Save Gemini Settings
                    </button>
                    {geminiSaveMsg && <span style={{ fontSize: 13, color: 'var(--muted)' }}>{geminiSaveMsg}</span>}
                  </div>
                </div>
              </div>

              {/* OpenAI Settings */}
              <div className="card" style={{ margin: 0 }}>
                <div className="card-header">
                  <span className="card-title">OpenAI Configuration</span>
                </div>
                <div className="card-body">
                  <div className="form-group" style={{ marginBottom: 12 }}>
                    <label className="form-label">OpenAI API Key</label>
                    <input
                      type="password"
                      className="text-input"
                      value={settingsOpenaiApiKey}
                      onChange={(e) => setSettingsOpenaiApiKey(e.target.value)}
                      placeholder={settingsOpenaiApiKey ? "••••••••" : "Enter OpenAI API Key"}
                    />
                  </div>

                  <div className="form-group" style={{ marginBottom: 12 }}>
                    <label className="form-label">OpenAI Model</label>
                    <select
                      className="select-input"
                      value={openaiModelSelect}
                      onChange={(e) => setOpenaiModelSelect(e.target.value)}
                    >
                      <option value="gpt-realtime-2">GPT Realtime 2 (Default)</option>
                      <option value="gpt-4o-realtime-preview">GPT-4o Realtime Preview</option>
                      <option value="gpt-4o-mini-realtime-preview">GPT-4o mini Realtime Preview</option>
                      <option value="custom">Custom Model...</option>
                    </select>
                  </div>

                  {openaiModelSelect === 'custom' && (
                    <div className="form-group" style={{ marginBottom: 12 }}>
                      <label className="form-label">Custom OpenAI Model ID</label>
                      <input
                        type="text"
                        className="text-input"
                        value={openaiModelCustom}
                        onChange={(e) => setOpenaiModelCustom(e.target.value)}
                        placeholder="e.g. gpt-realtime-2"
                      />
                    </div>
                  )}

                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 16 }}>
                    <button className="btn btn-primary" onClick={() => handleSaveModelSettings('openai')}>
                      Save OpenAI Settings
                    </button>
                    {openaiSaveMsg && <span style={{ fontSize: 13, color: 'var(--muted)' }}>{openaiSaveMsg}</span>}
                  </div>
                </div>
              </div>
            </div>

            {/* Interactive Utterances List Editor */}
            <div className="card" style={{ marginTop: 24 }}>
              <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span className="card-title">Scripted Test Utterances ({settingsUtterances.length})</span>
                <button 
                  className="btn btn-primary" 
                  onClick={() => {
                    const nextIndex = settingsUtterances.length;
                    const nextId = `u${String(nextIndex + 1).padStart(2, '0')}`;
                    setSettingsUtterances([...settingsUtterances, { id: nextId, text: '' }]);
                    setRawArgsState((prev) => ({ ...prev, [nextIndex]: '' }));
                  }}
                  style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 8px', fontSize: 12 }}
                >
                  <Plus size={14} /> Add Utterance
                </button>
              </div>
              <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {settingsUtterances.length === 0 ? (
                  <p style={{ textAlign: 'center', color: 'var(--muted)', fontSize: 13, padding: '20px 0' }}>
                    No utterances configured. Click "Add Utterance" to get started.
                  </p>
                ) : (
                  settingsUtterances.map((u, idx) => {
                    const expectType = u.expect?.tool ? 'tool' : u.expect?.response ? 'response' : 'none';
                    
                    return (
                      <div key={idx} className="utterance-edit-row" style={{
                        padding: 10,
                        border: '1px solid var(--border)',
                        borderRadius: 8,
                        backgroundColor: 'rgba(255, 255, 255, 0.02)',
                        position: 'relative'
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)' }}>Turn #{idx + 1}</span>
                            <input
                              type="text"
                              className="text-input"
                              value={u.id}
                              onChange={(e) => updateUtteranceField(idx, 'id', e.target.value)}
                              style={{ width: 60, padding: '2px 4px', fontSize: 11, fontWeight: 'bold', fontFamily: 'var(--font-mono)' }}
                              placeholder="ID"
                            />
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              const updated = settingsUtterances.filter((_, i) => i !== idx);
                              setSettingsUtterances(updated);
                              const nextRawArgs = {};
                              updated.forEach((item, i) => {
                                const oldIdx = i >= idx ? i + 1 : i;
                                nextRawArgs[i] = rawArgsState[oldIdx] || '';
                              });
                              setRawArgsState(nextRawArgs);
                            }}
                            style={{
                              background: 'none',
                              border: 'none',
                              color: 'var(--error)',
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              padding: 4
                            }}
                            title="Delete Utterance"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>

                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                          <div className="form-group" style={{ margin: 0 }}>
                            <label className="form-label" style={{ fontSize: 11, marginBottom: 2 }}>Prompt text</label>
                            <input
                              type="text"
                              className="text-input"
                              value={u.text}
                              onChange={(e) => updateUtteranceField(idx, 'text', e.target.value)}
                              placeholder="Enter the phrase user should say..."
                              style={{ fontSize: 12, padding: '4px 8px' }}
                            />
                          </div>

                          <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 2fr', gap: 8, alignItems: 'end' }}>
                            <div className="form-group" style={{ margin: 0 }}>
                              <label className="form-label" style={{ fontSize: 11, marginBottom: 2 }}>Expectation validation</label>
                              <select
                                className="select-input"
                                value={expectType}
                                onChange={(e) => updateUtteranceExpectType(idx, e.target.value)}
                                style={{ fontSize: 11, padding: '3px 6px', height: 26 }}
                              >
                                <option value="none">None (No check)</option>
                                <option value="response">Expected Response (Substring)</option>
                                <option value="tool">Expected Tool Call</option>
                              </select>
                            </div>

                            {expectType === 'response' && (
                              <div className="form-group" style={{ margin: 0 }}>
                                <label className="form-label" style={{ fontSize: 11, marginBottom: 2 }}>Expected response phrase</label>
                                <input
                                  type="text"
                                  className="text-input"
                                  value={u.expect?.response || ''}
                                  onChange={(e) => updateUtteranceExpectField(idx, 'response', e.target.value)}
                                  placeholder="e.g. open from 9am to 10pm"
                                  style={{ fontSize: 12, padding: '3px 6px', height: 26 }}
                                />
                              </div>
                            )}

                            {expectType === 'tool' && (
                              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                                <div className="form-group" style={{ margin: 0 }}>
                                  <label className="form-label" style={{ fontSize: 11, marginBottom: 2 }}>Expected tool name</label>
                                  <input
                                    type="text"
                                    className="text-input"
                                    value={u.expect?.tool || ''}
                                    onChange={(e) => updateUtteranceExpectField(idx, 'tool', e.target.value)}
                                    placeholder="e.g. get_hours"
                                    style={{ fontSize: 12, padding: '3px 6px', height: 26 }}
                                  />
                                </div>
                                <div className="form-group" style={{ margin: 0 }}>
                                  <label className="form-label" style={{ fontSize: 11, marginBottom: 2 }}>Expected arguments (JSON)</label>
                                  <input
                                    type="text"
                                    className="text-input"
                                    value={rawArgsState[idx] || ''}
                                    onChange={(e) => handleArgsChange(idx, e.target.value)}
                                    placeholder='e.g. {"guests": 2}'
                                    style={{ fontSize: 11, fontFamily: 'var(--font-mono)', padding: '3px 6px', height: 26 }}
                                  />
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
                
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 12 }}>
                  <button className="btn btn-primary" onClick={handleSaveUtterances}>
                    Save Utterances
                  </button>
                  {utterancesSaveMsg && <span style={{ fontSize: 13, color: 'var(--muted)' }}>{utterancesSaveMsg}</span>}
                </div>
              </div>
            </div>

            {/* Danger Zone */}
            <div className="card danger-zone" style={{ marginTop: 24 }}>
              <div className="card-header">
                <span className="card-title" style={{ color: 'var(--error)' }}>Danger Zone</span>
              </div>
              <div className="card-body">
                <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 12 }}>
                  Permanently delete all run history, transcripts, and audio files, and reset the database to a clean state. This cannot be undone.
                </p>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <button className="btn btn-danger" onClick={handleResetDatabase}>
                    Reset All Data
                  </button>
                  {resetMsg && <span style={{ fontSize: 13, color: 'var(--muted)' }}>{resetMsg}</span>}
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
      </div>

      {isNewRunModalOpen && (
        <div className="modal-overlay" onClick={() => setIsNewRunModalOpen(false)}>
          <div className="modal-content-card glass-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <span className="modal-title">Launch New Benchmark Run</span>
              <button className="modal-close-btn" onClick={() => setIsNewRunModalOpen(false)}>&times;</button>
            </div>
            <div className="modal-body" style={{ color: 'var(--fg)' }}>
              <div className="form-group" style={{ marginBottom: 16 }}>
                <label className="checkbox-label" style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input
                    type="checkbox"
                    checked={runBothInParallel}
                    onChange={(e) => setRunBothInParallel(e.target.checked)}
                  />
                  Compare Gemini &amp; OpenAI in parallel
                </label>
              </div>

              {!runBothInParallel && (
                <div className="form-row" style={{ marginBottom: 12 }}>
                  <div className="form-group" style={{ flex: 1 }}>
                    <label className="form-label">Active Provider</label>
                    <select
                      className="select-input"
                      value={selectedProvider}
                      onChange={(e) => {
                        const prov = e.target.value;
                        setSelectedProvider(prov);
                        if (prov === 'gemini') {
                          setSelectedModel(backendConfig?.gemini_model || 'gemini-3.1-flash-live-preview');
                        } else {
                          setSelectedModel(backendConfig?.openai_model || 'gpt-realtime-2');
                        }
                      }}
                    >
                      {backendConfig?.providers?.map(p => (
                        <option key={p} value={p}>{p.toUpperCase()}</option>
                      )) || (
                        <>
                          <option value="gemini">GEMINI</option>
                          <option value="openai">OPENAI</option>
                        </>
                      )}
                    </select>
                  </div>

                  <div className="form-group" style={{ flex: 1 }}>
                    <label className="form-label">Model Version</label>
                    <select
                      className="select-input"
                      value={selectedModel}
                      onChange={(e) => setSelectedModel(e.target.value)}
                    >
                      {selectedProvider === 'gemini' ? (
                        <>
                          <option value={backendConfig?.gemini_model || 'gemini-3.1-flash-live-preview'}>
                            {backendConfig?.gemini_model || 'gemini-3.1-flash-live-preview'} (Default)
                          </option>
                          {backendConfig?.gemini_model !== 'gemini-3.1-flash-live-preview' && (
                            <option value="gemini-3.1-flash-live-preview">gemini-3.1-flash-live-preview</option>
                          )}
                        </>
                      ) : (
                        <>
                          <option value={backendConfig?.openai_model || 'gpt-realtime-2'}>
                            {backendConfig?.openai_model || 'gpt-realtime-2'} (Default)
                          </option>
                          {backendConfig?.openai_model !== 'gpt-realtime-2' && (
                            <option value="gpt-realtime-2">gpt-realtime-2</option>
                          )}
                        </>
                      )}
                    </select>
                  </div>
                </div>
              )}

              <div className="form-row" style={{ marginBottom: 16 }}>
                <div className="form-group" style={{ flex: 1 }}>
                  <label className="form-label">Transport Layer</label>
                  <select
                    className="select-input"
                    value={selectedTransport}
                    onChange={(e) => setSelectedTransport(e.target.value)}
                  >
                    {backendConfig?.transports?.map(t => (
                      <option key={t} value={t}>{t}</option>
                    )) || (
                      <>
                        <option value="direct-injection">direct-injection</option>
                        <option value="webrtc-local">webrtc-local</option>
                      </>
                    )}
                  </select>
                </div>

                <div className="form-group" style={{ flex: 1 }}>
                  <label className="form-label">Conversation Turns</label>
                  <input
                    type="number"
                    className="text-input"
                    min={1}
                    max={10}
                    value={numTurns}
                    onChange={(e) => {
                      const val = parseInt(e.target.value, 10);
                      setNumTurns(Number.isNaN(val) ? 1 : Math.min(10, Math.max(1, val)));
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 20 }}>
                <button className="btn" type="button" onClick={() => setIsNewRunModalOpen(false)}>
                  Cancel
                </button>
                {runningId || compareRunIds ? (
                  <button 
                    className="btn" 
                    type="button"
                    style={{ backgroundColor: '#ea4335', color: '#fff', border: 'none', fontWeight: 'bold' }}
                    onClick={() => {
                      handleStopRun();
                      setIsNewRunModalOpen(false);
                    }}
                  >
                    Stop Current Run
                  </button>
                ) : (
                  <button className="btn btn-primary" type="button" onClick={handleStartRun}>
                    {runBothInParallel ? 'Start Parallel Run' : 'Start Run'}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
