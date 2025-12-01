import { useState } from 'react'
import { X, Upload, FileType, Save } from 'lucide-react'
import { api } from '../auth/AuthContext'

interface AddSoftwareModalProps {
    isOpen: boolean
    onClose: () => void
    onSuccess: () => void
}

export default function AddSoftwareModal({ isOpen, onClose, onSuccess }: AddSoftwareModalProps) {
    const [formData, setFormData] = useState({
        name: '',
        version: '',
        description: '',
        download_url: '',
        silent_args: '',
        uninstall_args: '',
        is_msi: false,
        icon_url: ''
    })
    const [uploading, setUploading] = useState(false)

    if (!isOpen) return null

    const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (!file) return

        const data = new FormData()
        data.append('file', file)

        setUploading(true)
        try {
            const res = await api.post('/management/upload', data, {
                headers: { 'Content-Type': 'multipart/form-data' }
            })

            // Auto-fill based on filename
            const filename = file.name
            const isMsi = filename.toLowerCase().endsWith('.msi')

            setFormData(prev => ({
                ...prev,
                download_url: res.data.url, // Assuming backend returns relative URL like /static/filename
                is_msi: isMsi,
                silent_args: isMsi ? '/qn' : '/S', // Default silent args guess
                name: filename.replace(/\.(msi|exe)$/i, '')
            }))
        } catch (err) {
            console.error("Upload failed", err)
            alert("File upload failed")
        } finally {
            setUploading(false)
        }
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        try {
            await api.post('/management/software', formData)
            onSuccess()
            onClose()
        } catch (err) {
            console.error("Failed to create software", err)
            alert("Failed to save software")
        }
    }

    return (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <div className="bg-dark border border-gray-800 rounded-xl w-full max-w-2xl shadow-2xl flex flex-col max-h-[90vh]">
                <div className="flex justify-between items-center p-6 border-b border-gray-800">
                    <h2 className="text-2xl font-bold text-white">Add New Software</h2>
                    <button onClick={onClose} className="text-gray-400 hover:text-white transition-colors">
                        <X size={24} />
                    </button>
                </div>

                <div className="p-6 overflow-y-auto custom-scrollbar">
                    <form onSubmit={handleSubmit} className="space-y-6">

                        {/* File Upload Section */}
                        <div className="border-2 border-dashed border-gray-700 rounded-xl p-8 text-center hover:border-primary/50 transition-colors bg-white/5">
                            <input
                                type="file"
                                id="file-upload"
                                className="hidden"
                                onChange={handleFileChange}
                                accept=".exe,.msi"
                            />
                            <label htmlFor="file-upload" className="cursor-pointer flex flex-col items-center gap-3">
                                <div className="w-12 h-12 bg-primary/20 rounded-full flex items-center justify-center text-primary">
                                    <Upload size={24} />
                                </div>
                                <div>
                                    <span className="text-primary font-medium hover:underline">Click to upload</span>
                                    <span className="text-gray-400"> or drag and drop</span>
                                </div>
                                <p className="text-sm text-gray-500">Supported: .EXE, .MSI</p>
                            </label>
                            {uploading && <p className="text-blue-400 mt-2 animate-pulse">Uploading...</p>}
                            {formData.download_url && (
                                <div className="mt-4 bg-green-500/10 text-green-400 px-4 py-2 rounded-lg inline-flex items-center gap-2">
                                    <FileType size={16} />
                                    File uploaded successfully
                                </div>
                            )}
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div className="space-y-2">
                                <label className="text-sm font-medium text-gray-400">Software Name</label>
                                <input
                                    type="text"
                                    required
                                    value={formData.name}
                                    onChange={e => setFormData({ ...formData, name: e.target.value })}
                                    className="w-full bg-black/50 border border-gray-700 rounded-lg px-4 py-2 text-white focus:border-primary focus:outline-none"
                                    placeholder="e.g. Google Chrome"
                                />
                            </div>
                            <div className="space-y-2">
                                <label className="text-sm font-medium text-gray-400">Version</label>
                                <input
                                    type="text"
                                    required
                                    value={formData.version}
                                    onChange={e => setFormData({ ...formData, version: e.target.value })}
                                    className="w-full bg-black/50 border border-gray-700 rounded-lg px-4 py-2 text-white focus:border-primary focus:outline-none"
                                    placeholder="e.g. 120.0.1"
                                />
                            </div>
                        </div>

                        <div className="space-y-2">
                            <label className="text-sm font-medium text-gray-400">Description</label>
                            <textarea
                                value={formData.description}
                                onChange={e => setFormData({ ...formData, description: e.target.value })}
                                className="w-full bg-black/50 border border-gray-700 rounded-lg px-4 py-2 text-white focus:border-primary focus:outline-none h-24 resize-none"
                                placeholder="Optional description..."
                            />
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div className="space-y-2">
                                <label className="text-sm font-medium text-gray-400">Silent Install Arguments</label>
                                <input
                                    type="text"
                                    required
                                    value={formData.silent_args}
                                    onChange={e => setFormData({ ...formData, silent_args: e.target.value })}
                                    className="w-full bg-black/50 border border-gray-700 rounded-lg px-4 py-2 text-white focus:border-primary focus:outline-none font-mono text-sm"
                                    placeholder="e.g. /S or /qn"
                                />
                            </div>
                            <div className="space-y-2">
                                <label className="text-sm font-medium text-gray-400">Uninstall Arguments</label>
                                <input
                                    type="text"
                                    value={formData.uninstall_args}
                                    onChange={e => setFormData({ ...formData, uninstall_args: e.target.value })}
                                    className="w-full bg-black/50 border border-gray-700 rounded-lg px-4 py-2 text-white focus:border-primary focus:outline-none font-mono text-sm"
                                    placeholder="Optional"
                                />
                            </div>
                        </div>

                        <div className="flex items-center gap-3 bg-white/5 p-4 rounded-lg">
                            <input
                                type="checkbox"
                                id="is_msi"
                                checked={formData.is_msi}
                                onChange={e => setFormData({ ...formData, is_msi: e.target.checked })}
                                className="w-5 h-5 rounded border-gray-600 bg-black/50 text-primary focus:ring-primary"
                            />
                            <label htmlFor="is_msi" className="text-gray-300 cursor-pointer select-none">
                                Is this an MSI installer? (Windows Installer)
                            </label>
                        </div>

                        <div className="pt-4 flex justify-end gap-3">
                            <button
                                type="button"
                                onClick={onClose}
                                className="px-6 py-2 rounded-lg text-gray-400 hover:text-white hover:bg-white/5 transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                type="submit"
                                disabled={!formData.download_url || !formData.name}
                                className="bg-primary hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed text-white px-6 py-2 rounded-lg font-medium transition-colors flex items-center gap-2"
                            >
                                <Save size={18} />
                                Save Software
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    )
}
