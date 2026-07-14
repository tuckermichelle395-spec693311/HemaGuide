import { GlassCard } from '../layout/GlassCard';
import type { Config } from '../../types/agent';
import type { SystemStatus } from '../../api/client';

interface ConfigPanelProps {
  config: Config;
  onConfigChange: (config: Config) => void;
  disabled: boolean;
  systemStatus: SystemStatus | null;
  loadingStatus: boolean;
  onRefreshStatus: () => void;
}

export function ConfigPanel({ config, onConfigChange, disabled, systemStatus, loadingStatus, onRefreshStatus }: ConfigPanelProps) {
  const models = systemStatus?.decision_models || [];
  return (
    <GlassCard className="p-5" hover={false}>
      <h3 className="text-base font-medium text-slate-800 mb-4 flex items-center gap-2">
        <svg className="w-5 h-5 text-hemaguide-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"
          />
        </svg>
        Local Models
      </h3>

      <div className="space-y-4">
        {/* Model Selection */}
        <div>
          <label className="block text-sm text-slate-500 mb-2">Model</label>
          <select
            value={config.decisionModel}
            onChange={e => onConfigChange({ ...config, decisionModel: e.target.value })}
            disabled={disabled}
            className={`glass-select ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            {models.length === 0 && <option value={config.decisionModel}>{config.decisionModel}</option>}
            {models.map(model => (
              <option key={model} value={model} className="bg-white text-slate-900">
                {model}{model === systemStatus?.recommended_decision_model ? ' (Recommended)' : ''}
              </option>
            ))}
          </select>
        </div>

        <div className="border-t border-slate-200 pt-4">
          <p className="mb-3 text-sm font-medium text-slate-700">测试证据开关</p>
          <div className="grid grid-cols-2 gap-3 text-sm text-slate-600">
            {[
              ['useFlowchart', '使用流程图'],
              ['useHistoricalCases', '使用历史病例'],
              ['usePubMed', '使用 PubMed'],
              ['useConferences', '使用会议记录'],
            ].map(([key, label]) => (
              <label key={key} className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={config[key as keyof Pick<Config, 'useFlowchart' | 'useHistoricalCases' | 'usePubMed' | 'useConferences'>]}
                  onChange={event => onConfigChange({ ...config, [key]: event.target.checked })}
                  disabled={disabled}
                  className="h-4 w-4 rounded border-slate-300 text-hemaguide-600 focus:ring-hemaguide-500"
                />
                <span>{label}</span>
              </label>
            ))}
          </div>
          <p className="mt-3 text-xs text-slate-400">仅用于比较不同证据来源开启/关闭时的输出。</p>
        </div>

        {/* Info text */}
        <div className="pt-2 space-y-2 text-xs">
          <div className="flex items-center justify-between">
            <span className={systemStatus?.ollama_connected ? 'text-emerald-600' : 'text-red-600'}>
              {systemStatus?.ollama_connected ? '● Ollama connected' : '● Ollama unavailable'}
            </span>
            <button onClick={onRefreshStatus} disabled={loadingStatus} className="text-hemaguide-600 hover:underline">
              {loadingStatus ? 'Checking…' : 'Refresh'}
            </button>
          </div>
          <p className={systemStatus?.recommended_embedding_model ? 'text-emerald-600' : 'text-amber-600'}>
            Embedding: {systemStatus?.recommended_embedding_model || 'not detected'}
          </p>
          <p className={systemStatus?.knowledge_base_ready ? 'text-emerald-600' : 'text-amber-600'}>
            Knowledge base: {systemStatus?.knowledge_base_ready ? 'ready' : 'not built'}
          </p>
          <p className="text-slate-400">Flowcharts: {systemStatus?.flowchart_count ?? 0}</p>
        </div>
      </div>
    </GlassCard>
  );
}
