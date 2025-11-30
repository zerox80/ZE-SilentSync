import { useState } from 'react'
import { Check, Download } from 'lucide-react'

// Mock data until backend is connected
const MOCK_SOFTWARE = [
    { id: 1, name: "Google Chrome", version: "119.0", icon: "https://upload.wikimedia.org/wikipedia/commons/e/e1/Google_Chrome_icon_%28February_2022%29.svg" },
    { id: 2, name: "Mozilla Firefox", version: "120.0", icon: "https://upload.wikimedia.org/wikipedia/commons/a/a0/Firefox_logo%2C_2019.svg" },
    { id: 3, name: "7-Zip", version: "23.01", icon: "https://upload.wikimedia.org/wikipedia/commons/7/77/7-Zip_img.png" },
    { id: 4, name: "VLC Media Player", version: "3.0.18", icon: "https://upload.wikimedia.org/wikipedia/commons/e/e6/VLC_Icon.svg" },
    { id: 5, name: "Notepad++", version: "8.5.8", icon: "https://upload.wikimedia.org/wikipedia/commons/f/f5/Notepad_plus_plus.png" },
    { id: 6, name: "Visual Studio Code", version: "1.84", icon: "https://upload.wikimedia.org/wikipedia/commons/9/9a/Visual_Studio_Code_1.35_icon.svg" },
]

export default function SoftwareLibrary() {
    const [selected, setSelected] = useState<number[]>([])

    const toggleSelect = (id: number) => {
        if (selected.includes(id)) {
            setSelected(selected.filter(i => i !== id))
        } else {
            setSelected([...selected, id])
        }
    }

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-3xl font-bold text-white">Software Library</h2>
                    <p className="text-gray-400 mt-1">Select applications to deploy to your fleet.</p>
                </div>
                <button
                    className="bg-primary hover:bg-blue-600 text-white px-6 py-2 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    disabled={selected.length === 0}
                >
                    Deploy {selected.length} Apps
                </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {MOCK_SOFTWARE.map((app) => (
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
                                {/* Fallback icon if image fails or is empty */}
                                {app.icon ? <img src={app.icon} alt={app.name} className="w-full h-full object-contain" /> : <Download size={24} />}
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
                    </div>
                ))}
            </div>
        </div>
    )
}
