import { useState, useEffect } from 'react'
import { api } from '../auth/AuthContext'
import { Folder, Monitor, ChevronRight, ChevronDown, CheckSquare, Square } from 'lucide-react'



export default function DeploymentWizard() {
    const [selected, setSelected] = useState<string[]>(() => {
        const saved = localStorage.getItem('selectedTargets')
        return saved ? JSON.parse(saved) : []
    })
    const [treeData, setTreeData] = useState<any>(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        const fetchTree = async () => {
            try {
                const res = await api.get('/management/ad/tree')
                setTreeData(res.data)
            } catch (err) {
                console.error("Failed to fetch AD tree", err)
            } finally {
                setLoading(false)
            }
        }
        fetchTree()
    }, [])

    const toggleSelect = (id: string) => {
        if (selected.includes(id)) {
            setSelected(selected.filter(s => s !== id))
        } else {
            setSelected([...selected, id])
        }
    }

    const handleSave = () => {
        localStorage.setItem('selectedTargets', JSON.stringify(selected))
        alert(`Saved ${selected.length} targets! Now go to Software Library to deploy.`)
    }

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-3xl font-bold text-white">Select Targets</h2>
                    <p className="text-gray-400 mt-1">Choose Organizational Units (OUs) or specific computers.</p>
                </div>
                <div className="flex gap-3 items-center">
                    {selected.length > 0 && (
                        <div className="bg-primary/10 border border-primary/50 rounded-lg px-4 py-2">
                            <span className="text-primary font-medium">{selected.length} selected</span>
                        </div>
                    )}
                    <button
                        onClick={handleSave}
                        disabled={selected.length === 0}
                        className="bg-green-600 hover:bg-green-500 disabled:opacity-50 disabled:cursor-not-allowed text-white px-6 py-2 rounded-lg font-medium transition-colors"
                    >
                        Save Selection
                    </button>
                </div>
            </div>

            <div className="bg-dark border border-gray-800 rounded-xl p-6">
                {loading && <div className="text-gray-400">Loading AD Structure...</div>}
                {!loading && treeData && <TreeNode node={treeData} level={0} selected={selected} onToggle={toggleSelect} />}
                {!loading && !treeData && <div className="text-red-400">Failed to load AD structure.</div>}
            </div>
        </div>
    )
}

function TreeNode({ node, level, selected, onToggle }: { node: any, level: number, selected: string[], onToggle: (id: string) => void }) {
    const [expanded, setExpanded] = useState(true)
    const isLeaf = !node.children
    const isSelected = selected.includes(node.id)
    const isSelectable = node.type !== 'domain'

    return (
        <div className="select-none">
            <div
                className={`
          flex items-center gap-2 py-2 px-2 rounded-lg transition-colors
          ${isSelectable ? 'hover:bg-white/5 cursor-pointer' : ''}
          ${isSelected ? 'bg-primary/10' : ''}
          ${level === 0 ? 'mb-2' : ''}
        `}
                style={{ paddingLeft: `${level * 1.5}rem` }}
            >
                {!isLeaf && (
                    <span className="text-gray-500" onClick={(e) => { e.stopPropagation(); setExpanded(!expanded) }}>
                        {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    </span>
                )}
                {isLeaf && <span className="w-4" />}

                {isSelectable && (
                    <span onClick={() => onToggle(node.id)} className="text-primary">
                        {isSelected ? <CheckSquare size={18} /> : <Square size={18} />}
                    </span>
                )}

                <div className="flex items-center gap-2 flex-1" onClick={() => isSelectable && onToggle(node.id)}>
                    {node.type === 'domain' && <NetworkIcon className="text-blue-400" />}
                    {node.type === 'ou' && <Folder size={18} className="text-yellow-500" />}
                    {node.type === 'computer' && <Monitor size={18} className="text-gray-400" />}

                    <span className={node.type === 'domain' ? 'font-bold text-lg' : 'text-gray-300'}>
                        {node.name}
                    </span>
                </div>
            </div>

            {expanded && node.children && (
                <div>
                    {node.children.map((child: any, idx: number) => (
                        <TreeNode key={idx} node={child} level={level + 1} selected={selected} onToggle={onToggle} />
                    ))}
                </div>
            )}
        </div>
    )
}

function NetworkIcon({ className }: { className?: string }) {
    return (
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}><rect x="16" y="16" width="6" height="6" rx="1" /><rect x="2" y="16" width="6" height="6" rx="1" /><rect x="9" y="2" width="6" height="6" rx="1" /><path d="M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3" /><path d="M12 12V8" /></svg>
    )
}
