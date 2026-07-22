import { motion, AnimatePresence } from 'framer-motion';
import { GlassCard } from '../layout/GlassCard';
import type { CaseResult } from '../../types/agent';

interface InterimResultsProps {
  caseResults: CaseResult[];
  isProcessing: boolean;
}

function EvidenceSources({ result }: { result: CaseResult }) {
  const evidence = result.evidence_hits;
  if (!evidence) return null;
  const sources = [
    ...(evidence.pubmed || []).map(item => ({ ...item, label: 'PubMed' })),
    ...(evidence.conferences || []).map(item => ({ ...item, label: item.conference || '会议' })),
  ];
  if (sources.length === 0) return null;

  return (
    <div className="mt-4 pt-3 border-t border-slate-200 space-y-2">
      <h6 className="text-xs font-medium text-slate-600">可核查的文献来源</h6>
      {sources.map((source, index) => (
        <div key={`${source.label}-${source.pmid || source.doi || index}`} className="rounded-lg border border-slate-200 bg-white/60 p-3">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-600">{source.label}</span>
            {source.year && <span className="text-slate-400">{source.year}</span>}
            {source.pmid && <span className="text-slate-500">PMID: {source.pmid}</span>}
            {source.doi && <span className="text-slate-500">DOI: {source.doi}</span>}
          </div>
          <p className="mt-1 text-sm text-slate-700">{source.title || '未提供标题'}</p>
          {source.key_finding_zh && <p className="mt-1 text-xs text-slate-500">{source.key_finding_zh}</p>}
          <div className="mt-2 flex flex-wrap gap-3 text-xs">
            {source.url && (
              <a href={source.url} target="_blank" rel="noopener noreferrer" className="text-hemaguide-700 hover:underline">
                {source.pmid ? '查看 PubMed' : '打开来源'}
              </a>
            )}
            {source.doi_url && source.doi_url !== source.url && (
              <a href={source.doi_url} target="_blank" rel="noopener noreferrer" className="text-hemaguide-700 hover:underline">
                打开 DOI
              </a>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function EvidenceExcerpts({ result }: { result: CaseResult }) {
  const evidence = result.evidence_hits;
  if (!evidence) return null;
  const sources = [
    ...(evidence.guidelines || []).map(item => ({ ...item, label: '流程图/指南' })),
    ...(evidence.similar_cases || []).map(item => ({ ...item, label: '历史病例' })),
    ...(evidence.pubmed || []).map(item => ({ ...item, label: 'PubMed' })),
    ...(evidence.conferences || []).map(item => ({ ...item, label: item.conference || '会议记录' })),
  ].filter(item => item.quote);
  if (sources.length === 0) return null;
  return (
    <div className="mt-4 pt-3 border-t border-slate-200 space-y-2">
      <h6 className="text-xs font-medium text-slate-600">引用原文</h6>
      {sources.map((source, index) => (
        <div key={`excerpt-${source.source_file || source.pmid || index}`} className="rounded-lg bg-slate-50 p-3">
          <div className="text-xs text-slate-500">{source.label}{source.pmid ? ` · PMID: ${source.pmid}` : ''}</div>
          <p className="mt-1 text-xs leading-relaxed text-slate-700">“{source.quote}”</p>
        </div>
      ))}
    </div>
  );
}

const MODE_CONFIG = {
  GUIDELINE: {
    label: 'GUIDELINE',
    color: 'text-purple-700',
    bgColor: 'bg-purple-50',
    borderColor: 'border-purple-200',
  },
  ADVANCED: {
    label: 'ADVANCED',
    color: 'text-amber-700',
    bgColor: 'bg-amber-50',
    borderColor: 'border-amber-200',
  },
  PLAIN: {
    label: 'PLAIN',
    color: 'text-slate-700',
    bgColor: 'bg-slate-50',
    borderColor: 'border-slate-300',
  },
  MOLECULAR: {
    label: 'MOLECULAR',
    color: 'text-hemaguide-700',
    bgColor: 'bg-hemaguide-50',
    borderColor: 'border-hemaguide-200',
  },
};

export function InterimResults({ caseResults, isProcessing }: InterimResultsProps) {
  if (caseResults.length === 0) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <div className="h-px flex-1 bg-gradient-to-r from-transparent via-emerald-500/30 to-transparent" />
        <span className="text-sm text-emerald-400 px-4 flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          {caseResults.length} case{caseResults.length !== 1 ? 's' : ''} completed
        </span>
        <div className="h-px flex-1 bg-gradient-to-r from-transparent via-emerald-500/30 to-transparent" />
      </div>

      <AnimatePresence mode="popLayout">
        {caseResults.map((caseResult, index) => {
          const displayedMode = caseResult.effective_mode || caseResult.mode;
          const modeConfig = MODE_CONFIG[displayedMode] || MODE_CONFIG.GUIDELINE;
          const downgraded = displayedMode !== caseResult.mode;

          return (
            <motion.div
              key={caseResult.case_id}
              initial={{ opacity: 0, y: 20, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ delay: index * 0.1 }}
            >
              <GlassCard
                className={`p-5 ${modeConfig.bgColor} ${modeConfig.borderColor}`}
                hover={false}
              >
                {/* Header */}
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className={`
                      w-10 h-10 rounded-xl flex items-center justify-center
                      ${modeConfig.bgColor} border ${modeConfig.borderColor}
                    `}>
                      <motion.svg
                        initial={{ scale: 0, rotate: -180 }}
                        animate={{ scale: 1, rotate: 0 }}
                        className={`w-5 h-5 ${modeConfig.color}`}
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </motion.svg>
                    </div>
                    <div>
                      <h4 className="font-medium text-slate-800">{caseResult.case_name}</h4>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`text-xs ${modeConfig.color}`}>{modeConfig.label} Mode</span>
                        {downgraded && (
                          <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] text-slate-600">
                            由 {caseResult.mode} 降级
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <span className="text-xs text-slate-400">
                    {new Date(caseResult.completed_at).toLocaleTimeString('en-US')}
                  </span>
                </div>

                {/* Decision */}
                <div className="mb-4">
                  <h5 className="text-xs text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-2">
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                    </svg>
                    Decision
                  </h5>
                  <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">
                    {caseResult.konferenzbeschluss || 'No decision available'}
                  </p>
                </div>

                {/* Original model reasoning - Collapsible */}
                <details className="group">
                  <summary className="text-xs text-slate-500 cursor-pointer hover:text-slate-700 transition-colors flex items-center gap-2">
                    <svg className="w-3.5 h-3.5 group-open:rotate-90 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                    原官方 Reason
                  </summary>
                  <div className="mt-3 pt-3 border-t border-slate-200">
                    <p className="text-sm text-slate-600 leading-relaxed whitespace-pre-wrap">
                      {caseResult.begründung || 'No reasoning available'}
                    </p>
                  </div>
                </details>

                {/* Auditable supplemental reasoning */}
                {caseResult.supplemental_reason && (
                  <details className="group mt-3">
                    <summary className="text-xs text-slate-500 cursor-pointer hover:text-slate-700 transition-colors flex items-center gap-2">
                      <svg className="w-3.5 h-3.5 group-open:rotate-90 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                      补充 Reason（命中依据）
                    </summary>
                    <div className="mt-3 pt-3 border-t border-slate-200">
                      <p className="text-sm text-slate-600 leading-relaxed whitespace-pre-wrap">
                        {caseResult.supplemental_reason}
                      </p>
                      <EvidenceSources result={caseResult} />
                      <EvidenceExcerpts result={caseResult} />
                    </div>
                  </details>
                )}
              </GlassCard>
            </motion.div>
          );
        })}
      </AnimatePresence>

      {/* Processing indicator */}
      {isProcessing && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex items-center justify-center gap-2 text-sm text-slate-500 py-2"
        >
          <motion.div
            className="w-4 h-4 border-2 border-hemaguide-200 border-t-hemaguide-500 rounded-full"
            animate={{ rotate: 360 }}
            transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
          />
          Processing additional cases...
        </motion.div>
      )}
    </div>
  );
}
