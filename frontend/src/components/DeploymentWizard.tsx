import { useState } from 'react'
import { Folder, Monitor, ChevronRight, ChevronDown } from 'lucide-react'

// Mock AD Tree Data
const AD_TREE = {
    name: "example.com",
    type: "domain",
    children: [
        {
            name: "Management",
            type: "ou",
            children: [
                { name: "AdminPC", type: "computer" },
                { name: "ManagerLaptop", type: "computer" }
            ]
        },
        {
            name: "Sales",
            type: "ou",
            children: [
                { name: "Sales01", type: "computer" },
                { name: "Sales02", type: "computer" }
            ]
        },
        {
            name: "IT",
            type: "ou",
            children: [
                { name: "DevWorkstation", type: "computer" }
            ]
        }
    ]
}

export default function DeploymentWizard() {
    return (
        <div className="space-y-6">
            <div>
                <h2 className="text-3xl font-bold text-white">Select Targets</h2>
                <p className="text-gray-400 mt-1">Choose Organizational Units (OUs) or specific computers.</p>
            </div>

            <div className="bg-dark border border-gray-800 rounded-xl p-6">
                <TreeNode node={AD_TREE} level={0} />
            </div>
        </div>
    )
}

function TreeNode({ node, level }: { node: any, level: number }) {
    const [expanded, setExpanded] = useState(true)
    const isLeaf = !node.children

    return (
        <div className="select-none">
            <div
                className={`
          flex items-center gap-2 py-2 px-2 rounded-lg hover:bg-white/5 cursor-pointer
          ${level === 0 ? 'mb-2' : ''}
        `}
                style={{ paddingLeft: `${level * 1.5}rem` }}
                onClick={() => !isLeaf && setExpanded(!expanded)}
            >
                {!isLeaf && (
                    <span className="text-gray-500">
                        {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    </span>
                )}
                {isLeaf && <span className="w-4" />} {/* Spacer */}

                {node.type === 'domain' && <NetworkIcon className="text-blue-400" />}
                {node.type === 'ou' && <Folder size={18} className="text-yellow-500" />}
                {node.type === 'computer' && <Monitor size={18} className="text-gray-400" />}

                <span className={node.type === 'domain' ? 'font-bold text-lg' : 'text-gray-300'}>
                    {node.name}
                </span>
            </div>

            {expanded && node.children && (
                <div>
                    {node.children.map((child: any, idx: number) => (
                        <TreeNode key={idx} node={child} level={level + 1} />
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
