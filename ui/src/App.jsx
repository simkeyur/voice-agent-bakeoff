import { useState, useEffect, useRef } from 'react';
import { Sun, Moon, Play, Pause, BarChart3, History, Settings } from 'lucide-react';
import logoUrl from './assets/logo.png';
import './App.css';

function AudioPlayer({ src }) {
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
    <div className="audio-player">
      <button
        type="button"
        className="audio-play-btn"
        onClick={toggle}
        aria-label={playing ? 'Pause response audio' : 'Play response audio'}
      >
        {playing ? <Pause size={14} /> : <Play size={14} />}
      </button>
      <span className="audio-player-label">Response Audio</span>
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

function App() {
  const [activeTab, setActiveTab] = useState('launcher');
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
  const [settingsUtterances, setSettingsUtterances] = useState('');
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [settingsSaveMsg, setSettingsSaveMsg] = useState('');
  const [utterancesSaveMsg, setUtterancesSaveMsg] = useState('');
  const [resetMsg, setResetMsg] = useState('');
  
  // Detailed Run Inspection
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [selectedRunData, setSelectedRunData] = useState(null);
  
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
      fetch(`${backendUrl}/api/utterances`).then((res) => res.json())
    ])
      .then(([settingsData, utterancesData]) => {
        setSettingsGeminiModel(settingsData.gemini_model || '');
        setSettingsOpenaiModel(settingsData.openai_model || '');
        setSettingsUtterances(utterancesData.content || '');
        setSettingsLoaded(true);
      })
      .catch((err) => console.error('Error loading settings:', err));
  }, [activeTab, settingsLoaded]);

  const handleSaveModelSettings = () => {
    setSettingsSaveMsg('Saving...');
    fetch(`${backendUrl}/api/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        gemini_model: settingsGeminiModel,
        openai_model: settingsOpenaiModel
      })
    })
      .then((res) => res.json())
      .then((data) => {
        setSettingsSaveMsg('Saved.');
        setBackendConfig((prev) => ({ ...prev, gemini_model: data.gemini_model, openai_model: data.openai_model }));
        setTimeout(() => setSettingsSaveMsg(''), 2000);
      })
      .catch((err) => setSettingsSaveMsg(`Error: ${err.message}`));
  };

  const handleSaveUtterances = () => {
    setUtterancesSaveMsg('Saving...');
    fetch(`${backendUrl}/api/utterances`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: settingsUtterances })
    })
      .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
      .then(({ ok, data }) => {
        if (ok) {
          setUtterancesSaveMsg(`Saved (${data.count} utterances).`);
        } else {
          setUtterancesSaveMsg(`Error: ${data.detail || 'failed to save'}`);
        }
        setTimeout(() => setUtterancesSaveMsg(''), 4000);
      })
      .catch((err) => setUtterancesSaveMsg(`Error: ${err.message}`));
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
        setResetMsg('All data has been reset.');
        setTimeout(() => setResetMsg(''), 4000);
      })
      .catch((err) => {
        console.error('Error resetting database:', err);
        setResetMsg(`Error: ${err.message}`);
      });
  };

  const needsApiKeySetup = backendConfig?.providers?.length > 0
    && backendConfig.providers.every((p) => !backendConfig.has_api_key?.[p]);

  return (
    <div className="app-container">
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
        <aside className="sidebar">
          <nav className="sidebar-nav">
            <button
              className={`sidebar-btn ${activeTab === 'launcher' ? 'active' : ''}`}
              onClick={() => setActiveTab('launcher')}
              title="Run Launcher"
              aria-label="Run Launcher"
            >
              <Play size={18} />
            </button>
            <button
              className={`sidebar-btn ${activeTab === 'metrics' ? 'active' : ''}`}
              onClick={() => setActiveTab('metrics')}
              title="Metrics Showdown"
              aria-label="Metrics Showdown"
            >
              <BarChart3 size={18} />
            </button>
            <button
              className={`sidebar-btn ${activeTab === 'history' ? 'active' : ''}`}
              onClick={() => {
                setActiveTab('history');
                setSelectedRunId(null);
              }}
              title="Results Browser"
              aria-label="Results Browser"
            >
              <History size={18} />
            </button>
          </nav>

          <button
            className={`sidebar-btn ${activeTab === 'settings' ? 'active' : ''}`}
            onClick={() => setActiveTab('settings')}
            title="Settings"
            aria-label="Settings"
          >
            <Settings size={18} />
          </button>
        </aside>

        <main className="main-content">
        {activeTab === 'launcher' && needsApiKeySetup && (
          <div className="setup-banner">
            <div>
              <strong>Welcome to VoxArena!</strong> No API keys are configured yet, so runs will fail.
              Add your provider API keys to get started.
            </div>
            <button className="btn btn-primary" onClick={() => setActiveTab('settings')}>
              Set up API Keys
            </button>
          </div>
        )}
        {activeTab === 'launcher' && (
          <div className="launcher-container">
            <div className="card">
              <div className="card-header">
                <span className="card-title">Run Configuration</span>
              </div>
              <div className="card-body">
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Active Provider</label>
                    <select
                      className="select-input"
                      value={selectedProvider}
                      disabled={runBothInParallel}
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

                  <div className="form-group">
                    <label className="form-label">Model Version</label>
                    <select
                      className="select-input"
                      value={selectedModel}
                      disabled={runBothInParallel}
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

                <div className="form-row">
                  <div className="form-group">
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

                  <div className="form-group">
                    <label className="form-label">Number of Conversation Turns</label>
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

                <div className="form-row form-row-actions">
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={runBothInParallel}
                      onChange={(e) => setRunBothInParallel(e.target.checked)}
                    />
                    Run Gemini &amp; OpenAI in parallel and compare
                  </label>

                  {(runningId || compareRunIds) ? (
                    <button
                      className="btn"
                      style={{ backgroundColor: '#ea4335', color: '#fff', border: 'none', fontWeight: 'bold' }}
                      onClick={handleStopRun}
                    >
                      Stop Run
                    </button>
                  ) : (
                    <button
                      className="btn btn-primary"
                      onClick={handleStartRun}
                    >
                      {runBothInParallel ? 'Start Parallel Comparison Run' : 'Start Scripted Run'}
                    </button>
                  )}
                </div>
                {(runningId || compareRunIds) && (
                  <div className="form-row">
                    <button className="btn btn-primary btn-disabled" style={{ width: '100%' }} disabled>
                      Running Test Suite...
                    </button>
                  </div>
                )}
              </div>
            </div>

            <div className="card">
              <div className="card-header">
                <span className="card-title">Live Log Console</span>
              </div>
              <div className="card-body" style={{ display: 'flex', flexDirection: 'column' }}>
                <div className="terminal">
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

        {activeTab === 'metrics' && (() => {
          const completedRuns = runs.filter(r => r.status === 'completed');
          
          // Calculate provider aggregates
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
          
          // Helper to calculate max value for relative bar widths
          const maxTtfa = Math.max(geminiStats?.avgTtfa || 0, openaiStats?.avgTtfa || 0) || 1000;
          const maxInterruption = Math.max(geminiStats?.avgInterruption || 0, openaiStats?.avgInterruption || 0) || 1000;

          return (
            <div className="scrollable-tab-container">
              {!hasStats ? (
                <div className="card">
                  <div className="card-header">
                    <span className="card-title">Metrics Showdown</span>
                  </div>
                  <div className="card-body">
                    <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '60px 0' }}>
                      No completed runs found. Execute at least one run from the "Run Launcher" tab to see comparative analytics.
                    </p>
                  </div>
                </div>
              ) : (
                <div>
                  <div className="grid-3" style={{ marginBottom: 24 }}>
                    <div className="card">
                      <div className="card-header"><span className="card-title">Latency Showdown (TTFA)</span></div>
                      <div className="card-body">
                        <div className="comp-bar-container">
                          {geminiStats && (
                            <div className="comp-bar-item">
                              <div className="comp-bar-header">
                                <span>GEMINI</span>
                                <span>{geminiStats.avgTtfa?.toFixed(0)} ms</span>
                              </div>
                              <div className="comp-bar-wrapper">
                                <div className="comp-bar-fill" style={{ width: `${(geminiStats.avgTtfa / maxTtfa) * 100}%` }}></div>
                              </div>
                            </div>
                          )}
                          {openaiStats && (
                            <div className="comp-bar-item">
                              <div className="comp-bar-header" style={{ color: 'var(--muted)' }}>
                                <span>OPENAI</span>
                                <span>{openaiStats.avgTtfa?.toFixed(0)} ms</span>
                              </div>
                              <div className="comp-bar-wrapper">
                                <div className="comp-bar-fill" style={{ width: `${(openaiStats.avgTtfa / maxTtfa) * 100}%`, backgroundColor: 'var(--muted)' }}></div>
                              </div>
                            </div>
                          )}
                        </div>
                        <div className="metric-label" style={{ marginTop: 12 }}>Lower is better. Measures transport delay to first audio response.</div>
                      </div>
                    </div>

                    <div className="card">
                      <div className="card-header"><span className="card-title">Tool-Call Accuracy</span></div>
                      <div className="card-body">
                        <div className="comp-bar-container">
                          {geminiStats && (
                            <div className="comp-bar-item">
                              <div className="comp-bar-header">
                                <span>GEMINI</span>
                                <span>{geminiStats.avgAccuracy?.toFixed(1)}%</span>
                              </div>
                              <div className="comp-bar-wrapper">
                                <div className="comp-bar-fill" style={{ width: `${geminiStats.avgAccuracy}%` }}></div>
                              </div>
                            </div>
                          )}
                          {openaiStats && (
                            <div className="comp-bar-item">
                              <div className="comp-bar-header" style={{ color: 'var(--muted)' }}>
                                <span>OPENAI</span>
                                <span>{openaiStats.avgAccuracy?.toFixed(1)}%</span>
                              </div>
                              <div className="comp-bar-wrapper">
                                <div className="comp-bar-fill" style={{ width: `${openaiStats.avgAccuracy}%`, backgroundColor: 'var(--muted)' }}></div>
                              </div>
                            </div>
                          )}
                        </div>
                        <div className="metric-label" style={{ marginTop: 12 }}>Higher is better. Percentage of correct tool calls.</div>
                      </div>
                    </div>

                    <div className="card">
                      <div className="card-header"><span className="card-title">Interruption Stop Latency</span></div>
                      <div className="card-body">
                        <div className="comp-bar-container">
                          {geminiStats && geminiStats.avgInterruption != null && (
                            <div className="comp-bar-item">
                              <div className="comp-bar-header">
                                <span>GEMINI</span>
                                <span>{geminiStats.avgInterruption?.toFixed(0)} ms</span>
                              </div>
                              <div className="comp-bar-wrapper">
                                <div className="comp-bar-fill" style={{ width: `${(geminiStats.avgInterruption / maxInterruption) * 100}%` }}></div>
                              </div>
                            </div>
                          )}
                          {openaiStats && openaiStats.avgInterruption != null && (
                            <div className="comp-bar-item">
                              <div className="comp-bar-header" style={{ color: 'var(--muted)' }}>
                                <span>OPENAI</span>
                                <span>{openaiStats.avgInterruption?.toFixed(0)} ms</span>
                              </div>
                              <div className="comp-bar-wrapper">
                                <div className="comp-bar-fill" style={{ width: `${(openaiStats.avgInterruption / maxInterruption) * 100}%`, backgroundColor: 'var(--muted)' }}></div>
                              </div>
                            </div>
                          )}
                        </div>
                        <div className="metric-label" style={{ marginTop: 12 }}>Lower is better. Time taken to stop speaking upon user interruption.</div>
                      </div>
                    </div>
                  </div>

                  <div className="card">
                    <div className="card-header"><span className="card-title">Fact Hallucinations</span></div>
                    <div className="card-body">
                      <table className="runs-table" style={{ margin: 0 }}>
                        <thead>
                          <tr>
                            <th>Provider</th>
                            <th>Experiment Runs</th>
                            <th>Total Hallucinations Audited</th>
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
                </div>
              )}
            </div>
          );
        })()}

        {activeTab === 'history' && (
          <div className="scrollable-tab-container">
            {selectedRunId ? (
              // Detailed Inspector View
              <div className="card">
                <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span className="card-title" style={{ fontFamily: 'var(--font-mono)' }}>
                    INSPECT: {selectedRunId.slice(0, 12)}...
                  </span>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button 
                      className="btn" 
                      style={{ color: 'var(--error)', borderColor: 'rgba(220, 38, 38, 0.2)' }}
                      onClick={() => handleDeleteRun(selectedRunId)}
                    >
                      Delete Run
                    </button>
                    <button className="btn" onClick={() => setSelectedRunId(null)}>
                      &larr; Back to History
                    </button>
                  </div>
                </div>
                <div className="card-body">
                  {!selectedRunData ? (
                    <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '20px 0' }}>Loading details...</p>
                  ) : (
                    <div>
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
              // Run List History Table
              <div className="card">
                <div className="card-header">
                  <span className="card-title">Completed Experiments</span>
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
                        {runs.map((run) => (
                          <tr key={run.run_id}>
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
                              <div style={{ display: 'flex', gap: 8 }}>
                                <button 
                                  className="btn" 
                                  style={{ padding: '4px 8px', fontSize: 11 }}
                                  onClick={() => setSelectedRunId(run.run_id)}
                                >
                                  Inspect
                                </button>
                                <button 
                                  className="btn" 
                                  style={{ padding: '4px 8px', fontSize: 11, color: 'var(--error)', borderColor: 'rgba(220, 38, 38, 0.2)' }}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleDeleteRun(run.run_id);
                                  }}
                                >
                                  Delete
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
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
            <div className="card">
              <div className="card-header">
                <span className="card-title">API Keys</span>
              </div>
              <div className="card-body">
                <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 12 }}>
                  VoxArena needs API keys for the providers you want to test. Add them to the{' '}
                  <code>.env</code> file at the root of the project ({backendConfig?.base_dir || 'project root'}),
                  then restart the server for changes to take effect.
                </p>
                {backendConfig?.providers?.map((p) => (
                  <div key={p} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>
                      {p.toUpperCase()}_API_KEY
                    </span>
                    <span className={`status-badge ${backendConfig?.has_api_key?.[p] ? 'completed' : 'failed'}`}>
                      {backendConfig?.has_api_key?.[p] ? 'Configured' : 'Missing'}
                    </span>
                  </div>
                ))}
                <div className="terminal" style={{ marginTop: 12, flex: 'none' }}>
                  <div className="terminal-line">GOOGLE_API_KEY=your-gemini-api-key</div>
                  <div className="terminal-line">OPENAI_API_KEY=your-openai-api-key</div>
                </div>
              </div>
            </div>

            <div className="card" style={{ marginTop: 24 }}>
              <div className="card-header">
                <span className="card-title">Model Configuration</span>
              </div>
              <div className="card-body">
                <div className="form-group">
                  <label className="form-label">Gemini Model</label>
                  <input
                    type="text"
                    className="text-input"
                    value={settingsGeminiModel}
                    onChange={(e) => setSettingsGeminiModel(e.target.value)}
                    placeholder="gemini-3.1-flash-live-preview"
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">OpenAI Model</label>
                  <input
                    type="text"
                    className="text-input"
                    value={settingsOpenaiModel}
                    onChange={(e) => setSettingsOpenaiModel(e.target.value)}
                    placeholder="gpt-realtime-2"
                  />
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <button className="btn btn-primary" onClick={handleSaveModelSettings}>
                    Save Model Settings
                  </button>
                  {settingsSaveMsg && <span style={{ fontSize: 13, color: 'var(--muted)' }}>{settingsSaveMsg}</span>}
                </div>
              </div>
            </div>

            <div className="card" style={{ marginTop: 24 }}>
              <div className="card-header">
                <span className="card-title">Scripted Conversation Utterances (YAML)</span>
              </div>
              <div className="card-body">
                <div className="form-group">
                  <label className="form-label">
                    Edit the test utterances run during a scripted session. Each entry needs an <code>id</code>, <code>text</code>, and optional <code>expect</code> block.
                  </label>
                  <textarea
                    className="text-input"
                    style={{ fontFamily: 'var(--font-mono)', fontSize: 12, minHeight: 400, resize: 'vertical', whiteSpace: 'pre' }}
                    value={settingsUtterances}
                    onChange={(e) => setSettingsUtterances(e.target.value)}
                    spellCheck={false}
                  />
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <button className="btn btn-primary" onClick={handleSaveUtterances}>
                    Save Utterances
                  </button>
                  {utterancesSaveMsg && <span style={{ fontSize: 13, color: 'var(--muted)' }}>{utterancesSaveMsg}</span>}
                </div>
              </div>
            </div>

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
    </div>
  );
}

export default App;
