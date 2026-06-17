import {
  ArrowLeft, GitCompare, ClipboardCheck, Trash2, History, Plus,
  Play, AudioLines,
} from 'lucide-react';
import AudioPlayer from '../AudioPlayer';
import LivePipelineVisualizer from '../LivePipelineVisualizer';

export default function RunsTab({ ctx }) {
  const {
    loadingComparison, activeComparison, selectedRunId, selectedRunData,
    compareRunIds, runningId,
    logs, logsEndRef,
    runs, runsSearchQuery, runsSortField, runsSortDirection,
    compareSelection, filteredAndSortedRuns,
    setRunsSearchQuery, setIsNewRunModalOpen, setCompareSelection,
    handleDeleteRun, handleSortRuns, getActivePipelineStep,
  } = ctx;

  if (loadingComparison) {
    return (
      <div className="scrollable-tab-container">
        <div className="card">
          <div className="card-body">
            <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '60px 0' }}>
              Loading comparison details...
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (activeComparison) {
    return (
      <div className="scrollable-tab-container">
        <ComparisonView
          activeComparison={activeComparison}
          compareRunIds={compareRunIds}
          logs={logs}
          logsEndRef={logsEndRef}
        />
      </div>
    );
  }

  if (selectedRunId) {
    return (
      <div className="scrollable-tab-container">
        <RunInspector
          selectedRunId={selectedRunId}
          selectedRunData={selectedRunData}
          runningId={runningId}
          logs={logs}
          logsEndRef={logsEndRef}
          handleDeleteRun={handleDeleteRun}
          getActivePipelineStep={getActivePipelineStep}
        />
      </div>
    );
  }

  return (
    <div className="scrollable-tab-container">
      <RunList
        runs={runs}
        filteredAndSortedRuns={filteredAndSortedRuns}
        runsSearchQuery={runsSearchQuery}
        runsSortField={runsSortField}
        runsSortDirection={runsSortDirection}
        compareSelection={compareSelection}
        setRunsSearchQuery={setRunsSearchQuery}
        setIsNewRunModalOpen={setIsNewRunModalOpen}
        setCompareSelection={setCompareSelection}
        handleDeleteRun={handleDeleteRun}
        handleSortRuns={handleSortRuns}
      />
    </div>
  );
}

function responseScore(turns) {
  const scored = (turns || []).filter(t => t.response_match !== null && t.response_match !== undefined);
  if (!scored.length) return null;
  return scored.filter(t => t.response_match).length / scored.length;
}

function MetricTile({ label, value, tone }) {
  const color = tone === 'error' ? 'var(--error)' : 'inherit';
  return (
    <div style={{ padding: '10px 14px', border: '1px solid var(--border)', borderRadius: 8, background: 'var(--accent-light)' }}>
      <div style={{ fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 600, color }}>
        {value}
      </div>
    </div>
  );
}

function CheckPill({ name, passed, fullName }) {
  const title = fullName || name;
  if (passed === null || passed === undefined) {
    return (
      <span title={`${title}: not evaluated`}
        style={{ fontSize: 9, padding: '2px 5px', borderRadius: 3, background: 'var(--accent-light)', color: 'var(--muted)', fontWeight: 600, letterSpacing: 0.3 }}>
        {name}
      </span>
    );
  }
  return (
    <span title={`${title}: ${passed ? 'pass' : 'fail'}`}
      style={{ fontSize: 9, padding: '2px 5px', borderRadius: 3, background: passed ? 'var(--success, #16a34a)' : 'var(--error)', color: '#fff', fontWeight: 700, letterSpacing: 0.3 }}>
      {name}
    </span>
  );
}

function EvalNotes({ notes }) {
  if (!notes) return '—';
  const text = notes.replace(/\[(LLM|Eval)\]\s*/g, '').trim();
  return <span>{text || '—'}</span>;
}

function ComparisonView({ activeComparison, compareRunIds, logs, logsEndRef }) {
  const r1 = activeComparison.run1;
  const r2 = activeComparison.run2;
  const m1 = r1.metrics || {};
  const m2 = r2.metrics || {};

  const rs1 = responseScore(r1.turns);
  const rs2 = responseScore(r2.turns);

  const ttfaWinner = (m1.average_ttfa_ms != null && m2.average_ttfa_ms != null)
    ? (m1.average_ttfa_ms < m2.average_ttfa_ms ? r1.run_id : (m2.average_ttfa_ms < m1.average_ttfa_ms ? r2.run_id : null))
    : null;
  const accWinner = (m1.tool_call_accuracy_rate != null && m2.tool_call_accuracy_rate != null)
    ? (m1.tool_call_accuracy_rate > m2.tool_call_accuracy_rate ? r1.run_id : (m2.tool_call_accuracy_rate > m1.tool_call_accuracy_rate ? r2.run_id : null))
    : null;
  const hallWinner = ((m1.hallucination_count ?? 0) < (m2.hallucination_count ?? 0))
    ? r1.run_id
    : ((m2.hallucination_count ?? 0) < (m1.hallucination_count ?? 0) ? r2.run_id : null);
  const costWinner = (m1.total_cost_usd != null && m2.total_cost_usd != null)
    ? (m1.total_cost_usd < m2.total_cost_usd ? r1.run_id : (m2.total_cost_usd < m1.total_cost_usd ? r2.run_id : null))
    : null;
  const respWinner = (rs1 != null && rs2 != null)
    ? (rs1 > rs2 ? r1.run_id : (rs2 > rs1 ? r2.run_id : null))
    : null;

  const ttfaDelta = (m1.average_ttfa_ms != null && m2.average_ttfa_ms != null)
    ? Math.abs(m1.average_ttfa_ms - m2.average_ttfa_ms).toFixed(0)
    : null;

  const winners = { ttfa: ttfaWinner, acc: accWinner, hall: hallWinner, cost: costWinner, resp: respWinner, ttfaDelta };
  const showLiveLogs = !!compareRunIds || r1.status === 'running' || r2.status === 'running';

  return (
    <div className="card">
      <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <button
          className="btn-icon"
          onClick={() => { window.location.hash = '#/runs'; }}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg)', padding: 4, display: 'flex', alignItems: 'center' }}
          title="Back to Runs"
        >
          <ArrowLeft size={18} />
        </button>
        <span className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <GitCompare size={16} style={{ color: 'var(--color-primary)' }} />
          Side-by-Side Run Comparison
        </span>
      </div>
      <div className="card-body">
        <div className="compare-split-view">
          <SummaryCard run={r1} winners={winners} />
          <SummaryCard run={r2} winners={winners} />
        </div>

        {showLiveLogs && (
          <details open={showLiveLogs && !!compareRunIds} style={{ marginTop: 16, border: '1px solid var(--border)', borderRadius: 8, padding: '8px 12px' }}>
            <summary style={{ cursor: 'pointer', fontSize: 12, fontWeight: 600, color: 'var(--muted)' }}>
              Live Comparison Logs
            </summary>
            <div className="terminal" style={{ marginTop: 8, height: 200 }}>
              {logs.map((log, idx) => (
                <div className="terminal-line" key={idx}>
                  <span className="terminal-timestamp">[{log.time}]</span>
                  <span>{log.text}</span>
                </div>
              ))}
              <div ref={logsEndRef} />
            </div>
          </details>
        )}

        <div style={{ marginTop: 20 }}>
          <h3 style={{ fontSize: 13, fontWeight: 600, borderBottom: '1px solid var(--border)', paddingBottom: 6, marginBottom: 12 }}>
            Turn Comparison
          </h3>

          {r1.turns.map((turn1, index) => {
            const turn2 = r2.turns[index] || {};
            return (
              <div key={index} style={{ borderBottom: '1px solid var(--border)', paddingBottom: 16, marginBottom: 16 }}>
                <div style={{ marginBottom: 8 }}>
                  <span className="header-badge">TURN {turn1.utterance_id}</span>
                  <span style={{ fontSize: 12, marginLeft: 8, color: 'var(--muted)' }}>Prompt: "{turn1.text_input}"</span>
                </div>
                <div className="compare-split-view" style={{ marginTop: 6 }}>
                  <TurnCell run={r1} turn={turn1} />
                  <TurnCell run={r2} turn={turn2} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, isWinner, tone, delta, badge }) {
  const color = tone === 'error' ? 'var(--error)' : (isWinner ? 'var(--fg)' : 'var(--muted)');
  return (
    <div>
      <div style={{ fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: 0.4, display: 'flex', alignItems: 'center', gap: 4 }}>
        {label}
        {badge && (
          <span style={{ fontSize: 8, fontWeight: 700, background: 'var(--color-primary)', color: '#fff', borderRadius: 3, padding: '0 4px', letterSpacing: 0.3 }}>
            {badge}
          </span>
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginTop: 2 }}>
        <span style={{ fontWeight: isWinner ? 700 : 500, fontSize: 16, fontFamily: 'var(--font-mono)', color }}>
          {value}
        </span>
        {delta && (
          <span style={{ fontSize: 10, color: 'var(--muted)', fontFamily: 'var(--font-mono)' }}>{delta}</span>
        )}
      </div>
    </div>
  );
}

function SummaryCard({ run, winners }) {
  const m = run.metrics || {};
  const isTtfaW = winners.ttfa === run.run_id;
  const isAccW = winners.acc === run.run_id;
  const isHallW = winners.hall === run.run_id;
  const isCostW = winners.cost === run.run_id;
  const isRespW = winners.resp === run.run_id;
  const myRs = responseScore(run.turns);
  return (
    <div className="comparison-card">
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.6, color: 'var(--fg)' }}>
          {(run.provider || '').toUpperCase()}
        </span>
        <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--muted)' }}>{run.model}</span>
      </div>
      <div style={{ fontSize: 10, color: 'var(--muted)', fontFamily: 'var(--font-mono)' }}>{run.run_id}</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, borderTop: '1px solid var(--border)', paddingTop: 10, marginTop: 10 }}>
        <Metric
          label="Avg TTFA"
          value={m.average_ttfa_ms != null ? `${m.average_ttfa_ms.toFixed(0)} ms` : '—'}
          isWinner={isTtfaW}
          delta={!isTtfaW && winners.ttfaDelta ? `+${winners.ttfaDelta}ms` : null}
        />
        <Metric
          label="Tool Accuracy"
          value={m.tool_call_accuracy_rate != null ? `${(m.tool_call_accuracy_rate * 100).toFixed(0)}%` : '—'}
          isWinner={isAccW}
        />
        <Metric
          label="Response Score"
          value={myRs != null ? `${(myRs * 100).toFixed(0)}%` : '—'}
          isWinner={isRespW}
        />
        <Metric
          label="Hallucinations"
          value={m.hallucination_count ?? 0}
          isWinner={isHallW}
          tone={(m.hallucination_count ?? 0) > 0 ? 'error' : null}
        />
        <Metric
          label="Est. Cost"
          value={m.total_cost_usd != null ? `$${m.total_cost_usd.toFixed(4)}` : '—'}
          isWinner={isCostW}
        />
      </div>
    </div>
  );
}

function TurnCell({ run, turn }) {
  const passed = !!turn.transcript_output && turn.evaluation_passed !== false;
  return (
    <div className="comparison-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: 0.5, color: 'var(--muted)' }}>
          {(run.provider || '').toUpperCase()}
        </span>
        <span className={`status-badge ${passed ? 'completed' : 'failed'}`}>{passed ? 'PASS' : 'FAIL'}</span>
      </div>
      <div style={{ fontSize: 13, margin: '8px 0', minHeight: 40 }}>
        {turn.transcript_output || (
          <span style={{ fontStyle: 'italic', color: 'var(--muted)' }}>(No speech output returned)</span>
        )}
      </div>
      <div style={{ display: 'flex', gap: 12, fontSize: 11, color: 'var(--muted)', borderTop: '1px dashed var(--border)', paddingTop: 6 }}>
        <div>TTFA <strong>{turn.time_to_first_audio_ms ? `${turn.time_to_first_audio_ms.toFixed(0)}ms` : '—'}</strong></div>
        <div>Int Stop <strong>{turn.interruption_stop_latency_ms ? `${turn.interruption_stop_latency_ms.toFixed(0)}ms` : '—'}</strong></div>
        <div>Tool <strong>{turn.tool_call_details ? turn.tool_call_details.name : '—'}</strong></div>
      </div>
      {turn.audio_output_path && (
        <div style={{ marginTop: 8 }}>
          <AudioPlayer
            src={`/api/results/${run.provider}/${run.run_id}/${turn.utterance_id}_response.wav`}
            latencyMs={turn.time_to_first_audio_ms}
          />
        </div>
      )}
      {turn.evaluation_notes && (
        <div style={{ fontSize: 11, color: 'var(--muted)', background: 'rgba(0,0,0,0.05)', padding: '6px 10px', borderRadius: 6, marginTop: 6 }}>
          <EvalNotes notes={turn.evaluation_notes} />
        </div>
      )}
    </div>
  );
}

function RunInspector({ selectedRunId, selectedRunData, runningId, logs, logsEndRef, handleDeleteRun, getActivePipelineStep }) {
  return (
    <div className="card">
      <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <button
            className="btn-icon"
            onClick={() => { window.location.hash = '#/runs'; }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg)', padding: 4, display: 'flex', alignItems: 'center' }}
            title="Back to Runs"
          >
            <ArrowLeft size={18} />
          </button>
          <span className="card-title" style={{ fontFamily: 'var(--font-mono)', display: 'flex', alignItems: 'center', gap: 8 }}>
            <ClipboardCheck size={16} style={{ color: 'var(--color-primary)' }} />
            INSPECT: {selectedRunId.slice(0, 12)}...
          </span>
          {selectedRunData && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, fontSize: 12, color: 'var(--muted)', borderLeft: '1px solid var(--border)', paddingLeft: 14 }}>
              <span>
                <strong style={{ color: 'var(--fg)' }}>{selectedRunData.provider.toUpperCase()}</strong>
                <span style={{ marginLeft: 6, fontFamily: 'var(--font-mono)' }}>{selectedRunData.model}</span>
              </span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>
                {new Date(selectedRunData.created_at * 1000).toLocaleString()}
              </span>
              <span className={`status-badge ${selectedRunData.status}`}>{selectedRunData.status}</span>
            </div>
          )}
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
            {(selectedRunData.status === 'running' || selectedRunData.status === 'pending' || runningId === selectedRunId) && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: 24 }}>
                <div className="card">
                  <div className="card-header">
                    <span className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Play size={16} style={{ color: 'var(--color-primary)' }} />Live Pipeline Status</span>
                  </div>
                  <div className="card-body">
                    <LivePipelineVisualizer activeStep={getActivePipelineStep()} />
                  </div>
                </div>

                <div className="card">
                  <div className="card-header">
                    <span className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}><History size={16} style={{ color: 'var(--color-primary)' }} />Live Logs</span>
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

            <div className="metric-tile-grid" style={{ marginBottom: 24 }}>
              <MetricTile
                label="Avg TTFA"
                value={selectedRunData.metrics?.average_ttfa_ms ? `${selectedRunData.metrics.average_ttfa_ms.toFixed(0)} ms` : '—'}
              />
              <MetricTile
                label="Tool Call Accuracy"
                value={selectedRunData.metrics?.tool_call_accuracy_rate != null ? `${(selectedRunData.metrics.tool_call_accuracy_rate * 100).toFixed(0)}%` : '—'}
              />
              <MetricTile
                label="Response Score"
                value={(() => {
                  const rs = selectedRunData.metrics?.response_match_rate ?? responseScore(selectedRunData.turns);
                  return rs != null ? `${(rs * 100).toFixed(0)}%` : '—';
                })()}
              />
              <MetricTile
                label="Faithfulness"
                value={selectedRunData.metrics?.faithfulness_rate != null ? `${(selectedRunData.metrics.faithfulness_rate * 100).toFixed(0)}%` : '—'}
              />
              <MetricTile
                label="Conciseness"
                value={selectedRunData.metrics?.conciseness_rate != null ? `${(selectedRunData.metrics.conciseness_rate * 100).toFixed(0)}%` : '—'}
              />
              <MetricTile
                label="Hallucinations"
                value={selectedRunData.metrics?.hallucination_count ?? 0}
                tone={selectedRunData.metrics?.hallucination_count > 0 ? 'error' : null}
              />
            </div>

            {selectedRunData.stitched_audio_path && (
              <div className="card" style={{ marginBottom: 24, padding: 16, border: '1px solid var(--border)', background: 'var(--accent-light)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
                  <div>
                    <h4 style={{ margin: 0, fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
                      <AudioLines size={16} style={{ color: 'var(--color-primary)' }} />
                      Stitched Call Audio (Left: User, Right: Bot)
                    </h4>
                    <p style={{ margin: '2px 0 0 0', fontSize: 12, color: 'var(--muted)' }}>
                      Listen to the entire call timeline with user and bot audio stitched at real relative timing.
                    </p>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'var(--font-mono)' }}>
                    /api/results/{selectedRunData.provider}/{selectedRunData.run_id}/stitched.wav
                  </div>
                </div>
                <AudioPlayer
                  src={`/api/results/${selectedRunData.provider}/${selectedRunData.run_id}/stitched.wav`}
                  fullWidth
                />
              </div>
            )}

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
                    <th>Tool</th>
                    <th>Checks</th>
                    <th>Audio</th>
                    <th>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedRunData.turns.map((turn, index) => {
                    const runActive = selectedRunData.status === 'running' || selectedRunData.status === 'pending';
                    const turnPending = runActive && !turn.transcript_output;
                    const passed = !turnPending && !!turn.transcript_output && turn.evaluation_passed !== false;
                    const rowClass = turnPending ? 'row-running' : (passed ? 'row-pass' : 'row-fail');
                    return (
                      <tr key={index} className={rowClass}>
                        <td><span className="header-badge" style={{ fontSize: 11 }}>{turn.utterance_id}</span></td>
                        <td style={{ maxWidth: 220 }}>{turn.text_input}</td>
                        <td style={{ maxWidth: 280, fontStyle: !turn.transcript_output ? 'italic' : 'normal', color: !turn.transcript_output ? 'var(--muted)' : 'inherit' }}>
                          {turn.transcript_output || '(No speech output returned)'}
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>
                          {turn.time_to_first_audio_ms != null ? `${turn.time_to_first_audio_ms.toFixed(0)}ms` : '—'}
                        </td>
                        <td style={{ whiteSpace: 'nowrap' }}>
                          {turn.tool_call_details ? <code>{turn.tool_call_details.name}</code> : '—'}
                        </td>
                        <td>
                          {turnPending ? (
                            <span className="status-badge running">RUNNING</span>
                          ) : (
                            <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap', alignItems: 'center' }}>
                              <CheckPill name="TOOL" fullName="Tool call" passed={turn.tool_call_correct} />
                              <CheckPill name="RESP" fullName="Response match" passed={turn.response_match} />
                              <CheckPill name="FAITH" fullName="Faithfulness" passed={turn.faithfulness_passed} />
                              <CheckPill name="CNC" fullName="Conciseness" passed={turn.conciseness_passed} />
                              {turn.hallucination_count != null && (
                                <span title={`Hallucinations: ${turn.hallucination_count}`}
                                  style={{ fontSize: 9, padding: '2px 5px', borderRadius: 3, background: turn.hallucination_count > 0 ? 'var(--error)' : 'var(--success, #16a34a)', color: '#fff', fontWeight: 700, letterSpacing: 0.3 }}>
                                  HALL {turn.hallucination_count}
                                </span>
                              )}
                            </div>
                          )}
                        </td>
                        <td style={{ minWidth: 160 }}>
                          {turn.audio_output_path ? (
                            <AudioPlayer
                              src={`/api/results/${selectedRunData.provider}/${selectedRunData.run_id}/${turn.utterance_id}_response.wav`}
                              latencyMs={turn.time_to_first_audio_ms}
                            />
                          ) : '—'}
                        </td>
                        <td style={{ maxWidth: 280, fontSize: 12, color: 'var(--muted)' }}>
                          <EvalNotes notes={turn.evaluation_notes} />
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
  );
}

function RunList({
  runs, filteredAndSortedRuns,
  runsSearchQuery, runsSortField, runsSortDirection,
  compareSelection,
  setRunsSearchQuery, setIsNewRunModalOpen, setCompareSelection,
  handleDeleteRun, handleSortRuns,
}) {
  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderBottom: '1px solid var(--border)', backgroundColor: 'var(--accent-light)' }}>
        <span className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <History size={16} style={{ color: 'var(--color-primary)' }} />
          Benchmark Runs
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <input
            type="text"
            className="text-input"
            value={runsSearchQuery}
            onChange={(e) => setRunsSearchQuery(e.target.value)}
            placeholder="Search runs..."
            style={{ width: 180, fontSize: 12, padding: '4px 8px', height: 28, margin: 0 }}
          />
          <button className="btn btn-primary" onClick={() => setIsNewRunModalOpen(true)} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, height: 28, padding: '4px 8px' }}>
            <Plus size={14} /> New Run
          </button>
          {compareSelection.length === 2 && (
            <button
              className="btn btn-primary"
              onClick={() => { window.location.hash = `#/runs/compare/${compareSelection[0]}/${compareSelection[1]}`; }}
              style={{ fontSize: 12, height: 28, padding: '4px 8px' }}
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
        ) : filteredAndSortedRuns.length === 0 ? (
          <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '40px 0' }}>
            No runs match your search query.
          </p>
        ) : (
          <table className="runs-table">
            <thead>
              <tr>
                {[
                  ['run_id', 'Run ID'],
                  ['provider', 'Provider'],
                  ['model', 'Model'],
                  ['transport', 'Transport'],
                  ['created_at', 'Date'],
                  ['status', 'Status'],
                ].map(([field, label]) => (
                  <th
                    key={field}
                    onClick={() => handleSortRuns(field)}
                    style={{ cursor: 'pointer', userSelect: 'none' }}
                  >
                    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      {label} {runsSortField === field && (runsSortDirection === 'asc' ? '▲' : '▼')}
                    </div>
                  </th>
                ))}
                <th style={{ width: 80, textAlign: 'center' }}>Compare</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredAndSortedRuns.map((run) => {
                const isSelected = compareSelection.includes(run.run_id);
                const toggleSelection = () => {
                  if (run.status !== 'completed') return;
                  if (isSelected) {
                    setCompareSelection(compareSelection.filter((id) => id !== run.run_id));
                  } else {
                    if (compareSelection.length < 2) {
                      setCompareSelection([...compareSelection, run.run_id]);
                    } else {
                      alert('You can compare a maximum of 2 runs.');
                    }
                  }
                };

                const handleRowClick = (e) => {
                  if (e.target.closest('button') || e.target.closest('a') || e.target.closest('input')) return;
                  toggleSelection();
                };

                return (
                  <tr
                    key={run.run_id}
                    onClick={handleRowClick}
                    style={{
                      cursor: run.status === 'completed' ? 'pointer' : 'default',
                      opacity: run.status === 'completed' ? 1 : 0.85,
                    }}
                  >
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
                    <td style={{ textAlign: 'center' }} onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        className="modern-checkbox"
                        checked={isSelected}
                        onChange={toggleSelection}
                        disabled={run.status !== 'completed'}
                      />
                    </td>
                    <td onClick={(e) => e.stopPropagation()}>
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
  );
}
