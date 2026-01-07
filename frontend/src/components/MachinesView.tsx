import { useState, useEffect } from 'react'
import { api } from '../auth/AuthContext'
import { Trash2, RefreshCw, Monitor, AlertTriangle } from 'lucide-react'

interface Machine {
    id: number
    hostname: string
    mac_address: string
    ip_address: string | null
    os_info: string
    last_seen: string
    ou_path: string | null
}

export default function MachinesView() {
    const [machines, setMachines] = useState<Machine[]>([])
    const [loading, setLoading] = useState(true)
    const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null)
    const [deleting, setDeleting] = useState(false)

    const fetchMachines = async () => {
        setLoading(true)
        try {
            const res = await api.get('/management/machines')
            setMachines(res.data)
        } catch (err) {
            console.error("Failed to fetch machines", err)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        fetchMachines()
    }, [])

    const handleDelete = async (id: number) => {
        setDeleting(true)
        try {
            await api.delete(`/management/machines/${id}`)
            setMachines(machines.filter(m => m.id !== id))
            setDeleteConfirm(null)
        } catch (err: any) {
            alert(err.response?.data?.detail || 'Failed to delete machine')
        } finally {
            setDeleting(false)
        }
    }

    const formatLastSeen = (dateStr: string) => {
        const date = new Date(dateStr)
        const now = new Date()
        const diffMs = now.getTime() - date.getTime()
        const diffMins = Math.floor(diffMs / 60000)

        if (diffMins < 1) return 'Just now'
        if (diffMins < 60) return `${diffMins}m ago`
        if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`
        return `${Math.floor(diffMins / 1440)}d ago`
    }

    const isOnline = (dateStr: string) => {
        const date = new Date(dateStr)
        const now = new Date()
        const diffMs = now.getTime() - date.getTime()
        return diffMs < 5 * 60 * 1000 // 5 minutes
    }

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-3xl font-bold text-white">Machines</h2>
                    <p className="text-gray-400 mt-1">Manage registered agent machines</p>
                </div>
                <button
                    onClick={fetchMachines}
                    disabled={loading}
                    className="flex items-center gap-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white px-4 py-2 rounded-lg transition-colors"
                >
                    <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
                    Refresh
                </button>
            </div>

            <div className="bg-dark border border-gray-800 rounded-xl overflow-hidden">
                {loading && machines.length === 0 ? (
                    <div className="p-8 text-center text-gray-400">Loading machines...</div>
                ) : machines.length === 0 ? (
                    <div className="p-8 text-center text-gray-400">No machines registered yet.</div>
                ) : (
                    <table className="w-full">
                        <thead className="bg-gray-800/50">
                            <tr>
                                <th className="text-left px-6 py-4 text-gray-400 font-medium">Status</th>
                                <th className="text-left px-6 py-4 text-gray-400 font-medium">Hostname</th>
                                <th className="text-left px-6 py-4 text-gray-400 font-medium">MAC Address</th>
                                <th className="text-left px-6 py-4 text-gray-400 font-medium">IP Address</th>
                                <th className="text-left px-6 py-4 text-gray-400 font-medium">OS</th>
                                <th className="text-left px-6 py-4 text-gray-400 font-medium">Last Seen</th>
                                <th className="text-right px-6 py-4 text-gray-400 font-medium">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {machines.map((machine) => (
                                <tr key={machine.id} className="border-t border-gray-800 hover:bg-white/5 transition-colors">
                                    <td className="px-6 py-4">
                                        <div className={`w-3 h-3 rounded-full ${isOnline(machine.last_seen) ? 'bg-green-500' : 'bg-gray-500'}`} />
                                    </td>
                                    <td className="px-6 py-4">
                                        <div className="flex items-center gap-2">
                                            <Monitor size={18} className="text-gray-500" />
                                            <span className="text-white font-medium">{machine.hostname}</span>
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 text-gray-400 font-mono text-sm">{machine.mac_address}</td>
                                    <td className="px-6 py-4 text-gray-400">{machine.ip_address || '-'}</td>
                                    <td className="px-6 py-4 text-gray-400 text-sm">{machine.os_info}</td>
                                    <td className="px-6 py-4 text-gray-400">{formatLastSeen(machine.last_seen)}</td>
                                    <td className="px-6 py-4 text-right">
                                        {deleteConfirm === machine.id ? (
                                            <div className="flex items-center justify-end gap-2">
                                                <span className="text-yellow-400 text-sm">Delete?</span>
                                                <button
                                                    onClick={() => handleDelete(machine.id)}
                                                    disabled={deleting}
                                                    className="px-3 py-1 bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white rounded text-sm"
                                                >
                                                    {deleting ? '...' : 'Yes'}
                                                </button>
                                                <button
                                                    onClick={() => setDeleteConfirm(null)}
                                                    className="px-3 py-1 bg-gray-600 hover:bg-gray-500 text-white rounded text-sm"
                                                >
                                                    No
                                                </button>
                                            </div>
                                        ) : (
                                            <button
                                                onClick={() => setDeleteConfirm(machine.id)}
                                                className="p-2 text-gray-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                                                title="Delete machine"
                                            >
                                                <Trash2 size={18} />
                                            </button>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4 flex items-start gap-3">
                <AlertTriangle className="text-yellow-500 shrink-0 mt-0.5" size={20} />
                <div>
                    <p className="text-yellow-400 font-medium">Deleting a machine</p>
                    <p className="text-gray-400 text-sm mt-1">
                        This removes the machine from the database, allowing re-registration with a new MAC address.
                        All installation history and logs for this machine will be permanently deleted.
                    </p>
                </div>
            </div>
        </div>
    )
}
