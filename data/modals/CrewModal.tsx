import React from 'react';
import { motion } from 'motion/react';
import { X, Users, Zap, ListTree, Brain, Settings2, Sparkles, LayoutPanelTop, Eye, Activity, Database, BookOpen, Terminal, HardDrive } from 'lucide-react';
import { 
  Section, 
  FieldGroup, 
  Toggle, 
  NumberInput, 
  JsonEditor, 
  SelectInput,
  TextInput 
} from '../ui/ConfigUI';
import { CrewAttributes, ProcessType } from '../../types';
import { cleanPayload } from '../../utils/dataUtils';
import { fetchOptions, Options } from '../../services/apiService';

export default function CrewModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const [options, setOptions] = React.useState<Options | null>(null);

  React.useEffect(() => {
    if (isOpen) {
      fetchOptions().then(setOptions);
    }
  }, [isOpen]);

  const [data, setData] = React.useState<CrewAttributes>({
    crewName: '',
    process: 'sequential'
  });

  const handleSave = () => {
    const cleaned = cleanPayload(data);
    console.log('Saving Crew Payload (Cleaned):', cleaned);
    onClose();
  };

  const [useLogFile, setUseLogFile] = React.useState<boolean | undefined>(undefined);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="absolute inset-0 bg-zinc-950/40 backdrop-blur-sm" 
      />
      
      <motion.div
        initial={{ y: 20, opacity: 0, scale: 0.98 }}
        animate={{ y: 0, opacity: 1, scale: 1 }}
        exit={{ y: 20, opacity: 0, scale: 0.98 }}
        className="relative w-full max-w-[1000px] h-[85vh] bg-white dark:bg-zinc-950 rounded-xl shadow-2xl flex flex-col overflow-hidden border border-zinc-200 dark:border-zinc-800"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-100 dark:border-zinc-900 bg-zinc-50/50 dark:bg-zinc-900/50">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-orange-100 dark:bg-orange-900/30 rounded-lg">
              <Users className="w-5 h-5 text-orange-600 dark:text-orange-400" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">Configure Crew</h2>
              <p className="text-[11px] text-zinc-500 uppercase font-medium tracking-tight">Crew Instance: NEW_CREW_ID</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors">
            <X className="w-5 h-5 text-zinc-400" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 flex overflow-hidden">
          {/* Main Content (Left) */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6 text-zinc-600 dark:text-zinc-400">
            <div className="space-y-4">
              <h3 className="text-sm font-bold text-zinc-400 uppercase tracking-widest flex items-center gap-2">
                <Sparkles className="w-3.5 h-3.5" /> Crew Overview
              </h3>
              <FieldGroup label="Crew Name">
                <TextInput value={data.crewName} onChange={(val) => setData({...data, name: val})} placeholder="e.g. Content Generation Crew" />
              </FieldGroup>
            </div>

            <div className="space-y-6 pt-4 border-t border-zinc-100 dark:border-zinc-900">
              <h3 className="text-sm font-bold text-zinc-400 uppercase tracking-widest flex items-center gap-2">
                <LayoutPanelTop className="w-3.5 h-3.5" /> ORCHESTRATION
              </h3>
              
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-6">
                  <FieldGroup label="Process Type" helperText={data.process === 'hierarchical' ? "Manager required to delegate tasks" : "Tasks executed one by one"}>
                    <div className="flex bg-zinc-100 dark:bg-zinc-900 p-1 rounded-lg w-fit">
                      {(['sequential', 'hierarchical'] as ProcessType[]).map((p) => (
                        <button
                          key={p}
                          onClick={() => setData({...data, process: p})}
                          className={`px-6 py-1.5 text-[11px] font-bold uppercase transition-all rounded-md ${
                            data.process === p 
                            ? 'bg-white dark:bg-zinc-800 text-orange-600 dark:text-orange-400 shadow-sm' 
                            : 'text-zinc-500 hover:text-zinc-700'
                          }`}
                        >
                          {p}
                        </button>
                      ))}
                    </div>
                  </FieldGroup>

                  <FieldGroup label="Global MAX RPM" helperText="Max requests per minute across all agents">
                    <NumberInput value={data.max_rpm} onChange={(val) => setData({...data, max_rpm: val})} placeholder="∞" />
                  </FieldGroup>
                </div>

                {data.process === 'hierarchical' && (
                  <motion.div 
                    initial={{ opacity: 0, y: -10 }} 
                    animate={{ opacity: 1, y: 0 }} 
                    className="p-4 bg-zinc-50/50 dark:bg-zinc-900/50 border border-zinc-200 dark:border-zinc-800 rounded-xl space-y-4"
                  >
                    <Toggle 
                      label="Manage LLM" 
                      description="Use a specific model to manage the process"
                      value={data.manager_llm_enabled} 
                      onChange={(val) => setData({...data, manager_llm_enabled: val})} 
                    />

                    {data.manager_llm_enabled === true ? (
                      <SelectInput 
                        label="Manager LLM Model"
                        options={options?.llmModels || []}
                        value={data.manager_llm_model || ''} 
                        onChange={(val) => setData({...data, manager_llm_model: val})} 
                      />
                    ) : (
                      <FieldGroup 
                        label="Manager Agent" 
                        helperText={data.manager_llm_enabled === undefined ? "Manager Agent is only available when Manage LLM is set to OFF" : "Select an agent to act as the manager"}
                      >
                        <select 
                          disabled={data.manager_llm_enabled === undefined}
                          value={data.manager_agent_id || ''}
                          onChange={(e) => setData({...data, manager_agent_id: e.target.value})}
                          className={`w-full h-9 px-3 text-sm bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-lg outline-none focus:ring-1 focus:ring-orange-500 font-medium appearance-none ${
                            data.manager_llm_enabled === undefined ? 'opacity-50 cursor-not-allowed bg-zinc-50 dark:bg-zinc-800/50' : ''
                          }`}
                          style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%239CA3AF'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E")`, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 0.75rem center', backgroundSize: '1rem' }}
                        >
                          <option value="">No Manager Assigned</option>
                          {options?.agents?.map(name => <option key={name} value={name}>{name}</option>)}
                        </select>
                      </FieldGroup>
                    )}
                  </motion.div>
                )}
              </div>

              <div className="grid grid-cols-2 gap-4">
                 {/* LLM models are now in Advanced settings in the sidebar */}
              </div>
            </div>
          </div>

          {/* Settings Sidebar (Right) */}
          <div className="w-[340px] border-l border-zinc-100 dark:border-zinc-900 overflow-y-auto bg-zinc-50/30 dark:bg-zinc-950/30 font-medium text-zinc-500">
            <Section title="Monitoring" icon={Activity} defaultOpen={true}>
              <div className="space-y-2">
                <Toggle label="Verbose" value={data.is_verbose_logs} onChange={(val) => setData({...data, is_verbose_logs: val})} />
                <Toggle label="Stream" value={data.stream} onChange={(val) => setData({...data, stream: val})} />
                <Toggle label="Tracing" value={data.tracing} onChange={(val) => setData({...data, tracing: val})} />
                <Toggle label="Output Log File" value={useLogFile} onChange={(val) => {
                  setUseLogFile(val);
                  if (val !== true) setData({...data, output_log_file: undefined});
                }} />
                {useLogFile && (
                  <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="pt-2">
                    <FieldGroup label="Log File Path">
                      <TextInput value={data.output_log_file} onChange={(val) => setData({...data, output_log_file: val})} placeholder="e.g. crew.log" />
                    </FieldGroup>
                  </motion.div>
                )}
              </div>
            </Section>

            <Section title="ADVANCED" icon={Settings2} defaultOpen={false}>
              <div className="space-y-4">
                <div className="space-y-4 text-zinc-600">
                  <Toggle label="Planning" value={data.planning} onChange={(val) => setData({...data, planning: val})} />
                  {data.planning && (
                    <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}>
                      <SelectInput 
                        label="Planning LLM" 
                        options={options?.llmModels || []} 
                        value={data.planning_llm_model || ''} 
                        onChange={(val) => setData({...data, planning_llm_model: val})} 
                      />
                    </motion.div>
                  )}
                </div>

                <div className="space-y-4">
                  <Toggle label="Chat with Crew" value={data.chat_with_crew} onChange={(val) => setData({...data, chat_with_crew: val})} />
                  {data.chat_with_crew && (
                    <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}>
                      <SelectInput 
                        label="Chating LLM" 
                        options={options?.llmModels || []} 
                        value={data.chat_llm_model || ''} 
                        onChange={(val) => setData({...data, chat_llm_model: val})} 
                      />
                    </motion.div>
                  )}
                </div>

                <div className="space-y-4 border-t border-zinc-100 dark:border-zinc-900 pt-4">
                  <Toggle label="Embedder for Memory" value={data.embedder_enabled} onChange={(val) => setData({...data, embedder_enabled: val})} />
                  {data.embedder_enabled && (
                    <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}>
                      <SelectInput 
                        label="Embedder" 
                        options={options?.embedders || []} 
                        value={data.embedder_json} 
                        onChange={(val) => setData({...data, embedder_json: val})} 
                      />
                    </motion.div>
                  )}
                </div>
              </div>
            </Section>

            <Section title="MEMORY" icon={Database} defaultOpen={false}>
              <div className="space-y-4">
                <div className="space-y-4">
                  <Toggle label="Checkpoint" value={data.checkpoint} onChange={(val) => setData({...data, checkpoint: val})} />
                  {data.checkpoint && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-3 bg-zinc-100 dark:bg-zinc-900 rounded-lg">
                      <div className="flex items-center gap-2 text-[10px] text-zinc-400 uppercase font-bold mb-2">
                        <Terminal className="w-3 h-3" /> CheckpointConfig Shell
                      </div>
                      <div className="h-20 border-2 border-dashed border-zinc-200 dark:border-zinc-800 rounded flex items-center justify-center text-[10px] px-4 text-center">
                        Advanced configuration UI coming soon
                      </div>
                    </motion.div>
                  )}
                </div>
                <Toggle label="Memory" value={data.memory_enabled} onChange={(val) => setData({...data, memory_enabled: val})} />
                <Toggle label="Cache" value={data.cache} onChange={(val) => setData({...data, cache: val})} />
              </div>
            </Section>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-zinc-100 dark:border-zinc-900 flex items-center justify-between bg-zinc-50/50 dark:bg-zinc-950">
          <p className="text-[11px] text-zinc-500">Global settings apply to all agents in this crew unless overridden.</p>
          <div className="flex items-center gap-3">
            <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors">
              Cancel
            </button>
            <button onClick={handleSave} className="px-6 py-2 text-sm font-semibold bg-orange-600 text-white rounded-lg hover:bg-orange-700 shadow-lg shadow-orange-600/20 transition-all">
              Save Crew
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
