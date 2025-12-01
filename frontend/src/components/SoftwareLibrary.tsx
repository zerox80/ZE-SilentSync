import { useState, useEffect } from 'react'
import { Check, Package, Plus } from 'lucide-react'
import { api } from '../auth/AuthContext'
import AddSoftwareModal from './AddSoftwareModal'

export default function SoftwareLibrary() {
    const [selected, setSelected] = useState<number[]>([])
    const [software, setSoftware] = useState<any[]>([])
    const [loading, setLoading] = useState(true)
    const [isAddModalOpen, setIsAddModalOpen] = useState(false)

    useEffect(() => {
        fetchSoftware()
    }, [])

    const fetchSoftware = async () => {
        try {
            const res = await api.get('/management/software')
            const data = Array.isArray(res.data) ? res.data : [];
            setSoftware(data)
        } catch (err) {
            console.error("Failed to fetch software", err)
        } finally {
            setLoading(false)
        }
    }

    const toggleSelect = (id: number) => {
        if (selected.includes(id)) {
            setSelected(selected.filter(i => i !== id))
        } else {
            setSelected([...selected, id])
        }
    }

    const handleDeploy = async (action: string = 'install') => {
        if (selected.length === 0) return;

        const savedTargets = localStorage.getItem('selectedTargets')
        const targets = savedTargets ? JSON.parse(savedTargets) : []

        if (targets.length === 0) {
            alert("No targets selected! Go to 'Targets (AD)' tab first.")
            return
        }

        try {
            await api.post('/management/deploy/bulk', {
                software_ids: selected,
                target_dns: targets,
                action: action
            })
            const verb = action === 'uninstall' ? 'uninstall' : 'deploy';
            alert(`Successfully scheduled to ${verb} ${selected.length} apps on ${targets.length} targets!`)
            setSelected([])
        } catch (err) {
            alert("Action failed! Check console.")
            console.error(err)
        }
    }

    if (loading) return <div className="text-white">Loading library...</div>

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-3xl font-bold text-white">Software Library</h2>
                    <p className="text-gray-400 mt-1">Select applications to deploy to your fleet.</p>
                </div>
                <div className="flex gap-3">
                    <button
                        onClick={() => setIsAddModalOpen(true)}
                        className="bg-white/10 hover:bg-white/20 text-white px-4 py-2 rounded-lg font-medium transition-colors flex items-center gap-2"
                    >
                        <Plus size={18} />
                        Add Software
                    </button>
                    <button
                        onClick={() => handleDeploy('uninstall')}
                        className="bg-red-600 hover:bg-red-500 text-white px-6 py-2 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        disabled={selected.length === 0}
                    >
                        Uninstall
                    </button>
                    <button
                        onClick={() => handleDeploy('install')}
                        className="bg-primary hover:bg-blue-600 text-white px-6 py-2 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        disabled={selected.length === 0}
                    >
                        Deploy {selected.length} Apps
                    </button>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {Array.isArray(software) && software.map((app) => (
                    <div
                        key={app.id}
                        onClick={() => toggleSelect(app.id)}
                        className={`
              relative group cursor-pointer rounded-xl p-4 border transition-all duration-200
              ${selected.includes(app.id)
                                ? 'bg-primary/10 border-primary shadow-[0_0_20px_rgba(59,130,246,0.15)]'
                                : 'bg-dark border-gray-800 hover:border-gray-600 hover:bg-gray-900'}
            `}
                    >
                        <div className="flex items-start justify-between mb-4">
                            <div className="w-12 h-12 bg-white/5 rounded-lg p-2 flex items-center justify-center">
                                {app.icon_url ? <img src={app.icon_url} alt={app.name} className="w-full h-full object-contain" /> : <Package size={24} className="text-blue-400" />}
                            </div>
                            <div className={`
                w-6 h-6 rounded-full border flex items-center justify-center transition-colors
                ${selected.includes(app.id) ? 'bg-primary border-primary' : 'border-gray-600 group-hover:border-gray-400'}
              `}>
                                {selected.includes(app.id) && <Check size={14} className="text-white" />}
                            </div>
                        </div>

                        <h3 className="font-bold text-lg text-gray-100">{app.name}</h3>
                        <p className="text-sm text-gray-500">{app.version}</p>
                        <div className="mt-2 flex gap-2">
                            {app.is_msi && <span className="text-xs bg-purple-500/20 text-purple-300 px-2 py-0.5 rounded">MSI</span>}
                            <span className="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded">EXE</span>
                        </div>
                    </div>
                ))}
            </div>

            <AddSoftwareModal
                isOpen={isAddModalOpen}
                onClose={() => setIsAddModalOpen(false)}
                onSuccess={fetchSoftware}
            />
        </div>
    )
}
