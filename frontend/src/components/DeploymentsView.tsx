import { useState, useEffect } from 'react'
import { Trash2, AlertTriangle, RefreshCw, X } from 'lucide-react'
import { api } from '../auth/AuthContext'

interface Deployment {
    id: number
    software_id: number
    target_value: string
    target_name?: string
    target_type: string
    action: string
    created_at: string
    software?: {
        name: string
    }
}

export default function DeploymentsView() {
    const [deployments, setDeployments] = useState<Deployment[]>([])
    const [loading, setLoading] = useState(true)
    const [clearing, setClearing] = useState(false)

    useEffect(() => {
        fetchDeployments()
    }, [])

    const fetchDeployments = async () => {
        try {
            const res = await api.get('/management/deployments')
            setDeployments(Array.isArray(res.data) ? res.data : [])
        } catch (err) {
            console.error("Failed to fetch deployments", err)
            setDeployments([])
        } finally {
            setLoading(false)
        }
    }

    const handleClearAll = async () => {
        if (!confirm("⚠️ Are you sure you want to clear ALL pending deployments?\n\nThis will stop all queued install/uninstall tasks immediately.")) {
            return
        }

        setClearing(true)
        try {
            const res = await api.delete('/management/deploy/clear-all')
            alert(`✅ Cleared ${res.data.count} deployments!`)
            setDeployments([])
        } catch (err) {
            console.error("Failed to clear deployments", err)
            alert("Failed to clear deployments. Check console.")
        } finally {
            setClearing(false)
        }
    }

    const handleDeleteSingle = async (id: number, softwareName: string) => {
        if (!confirm(`Cancel deployment for "${softwareName}"?`)) {
            return
        }

        try {
            await api.delete(`/management/deploy/${id}`)
            setDeployments(deployments.filter(d => d.id !== id))
        } catch (err) {
            console.error("Failed to delete deployment", err)
            alert("Failed to cancel deployment. Check console.")
        }
    }

    if (loading) {
        return <div className="text-white">Loading deployments...</div>
    }

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-3xl font-bold text-white">Pending Deployments</h2>
                    <p className="text-gray-400 mt-1">
                        {deployments.length} pending task{deployments.length !== 1 ? 's' : ''} in queue
                    </p>
                </div>
                <div className="flex gap-3">
                    <button
                        onClick={fetchDeployments}
                        className="bg-white/10 hover:bg-white/20 text-white px-4 py-2 rounded-lg font-medium transition-colors flex items-center gap-2"
                    >
                        <RefreshCw size={18} />
                        Refresh
                    </button>
                    <button
                        onClick={handleClearAll}
                        disabled={clearing || deployments.length === 0}
                        className="bg-red-600 hover:bg-red-500 text-white px-6 py-2 rounded-lg font-medium transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {clearing ? (
                            <>
                                <RefreshCw size={18} className="animate-spin" />
                                Clearing...
                            </>
                        ) : (
                            <>
                                <Trash2 size={18} />
                                Clear All Tasks
                            </>
                        )}
                    </button>
                </div>
            </div>

            {deployments.length === 0 ? (
                <div className="bg-dark border border-gray-800 rounded-xl p-12 text-center">
                    <AlertTriangle size={48} className="mx-auto text-gray-600 mb-4" />
                    <h3 className="text-xl font-semibold text-gray-400">No Pending Deployments</h3>
                    <p className="text-gray-500 mt-2">All clear! No tasks are queued for agents.</p>
                </div>
            ) : (
                <div className="bg-dark border border-gray-800 rounded-xl overflow-hidden">
                    <table className="w-full">
                        <thead className="bg-gray-900/50">
                            <tr>
                                <th className="px-6 py-4 text-left text-sm font-medium text-gray-400">ID</th>
                                <th className="px-6 py-4 text-left text-sm font-medium text-gray-400">Software</th>
                                <th className="px-6 py-4 text-left text-sm font-medium text-gray-400">Target</th>
                                <th className="px-6 py-4 text-left text-sm font-medium text-gray-400">Action</th>
                                <th className="px-6 py-4 text-left text-sm font-medium text-gray-400">Created</th>
                                <th className="px-6 py-4 text-center text-sm font-medium text-gray-400">Cancel</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-800">
                            {deployments.map((dep) => (
                                <tr key={dep.id} className="hover:bg-gray-900/30">
                                    <td className="px-6 py-4 text-sm text-gray-300">#{dep.id}</td>
                                    <td className="px-6 py-4 text-sm text-white font-medium">
                                        {dep.software?.name || `Software #${dep.software_id}`}
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-300">
                                        <span className="text-xs text-gray-500 mr-2">[{dep.target_type}]</span>
                                        {dep.target_name || dep.target_value}
                                    </td>
                                    <td className="px-6 py-4">
                                        <span className={`text-xs px-2 py-1 rounded ${dep.action === 'uninstall'
                                            ? 'bg-red-500/20 text-red-300'
                                            : 'bg-green-500/20 text-green-300'
                                            }`}>
                                            {dep.action.toUpperCase()}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-400">
                                        {new Date(dep.created_at).toLocaleString()}
                                    </td>
                                    <td className="px-6 py-4 text-center">
                                        <button
                                            onClick={() => handleDeleteSingle(dep.id, dep.software?.name || 'Unknown')}
                                            className="p-2 text-gray-500 hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-colors"
                                            title="Cancel this deployment"
                                        >
                                            <X size={18} />
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    )
}
