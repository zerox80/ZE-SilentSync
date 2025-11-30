import { useState } from 'react'
import { LayoutDashboard, AppWindow, Network, Send, LogOut } from 'lucide-react'
import SoftwareLibrary from './components/SoftwareLibrary'
import DeploymentWizard from './components/DeploymentWizard'
import { AuthProvider, useAuth } from './auth/AuthContext'
import Login from './components/Login'

function AppContent() {
    const [activeTab, setActiveTab] = useState('library')
    const { isAuthenticated, logout } = useAuth()

    if (!isAuthenticated) {
        return <Login />
    }

    return (
        <div className="flex h-screen bg-darker text-white font-sans">
            {/* Sidebar */}
            <aside className="w-64 bg-dark border-r border-gray-800 flex flex-col">
                <div className="p-6">
                    <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
                        ZE-SilentSync
                    </h1>
                </div>

                <nav className="flex-1 px-4 space-y-2">
                    <NavButton
                        active={activeTab === 'dashboard'}
                        onClick={() => setActiveTab('dashboard')}
                        icon={<LayoutDashboard size={20} />}
                        label="Dashboard"
                    />
                    <NavButton
                        active={activeTab === 'library'}
                        onClick={() => setActiveTab('library')}
                        icon={<AppWindow size={20} />}
                        label="Software Library"
                    />
                    <NavButton
                        active={activeTab === 'targets'}
                        onClick={() => setActiveTab('targets')}
                        icon={<Network size={20} />}
                        label="Targets (AD)"
                    />
                    <NavButton
                        active={activeTab === 'deployments'}
                        onClick={() => setActiveTab('deployments')}
                        icon={<Send size={20} />}
                        label="Deployments"
                    />
                </nav>

                <div className="p-4 border-t border-gray-800">
                    <button
                        onClick={logout}
                        className="w-full flex items-center gap-3 px-4 py-2 text-gray-400 hover:text-red-400 transition-colors"
                    >
                        <LogOut size={20} />
                        <span>Sign Out</span>
                    </button>
                    <div className="mt-4 text-xs text-center text-gray-600">
                        v2.0 Enterprise
                    </div>
                </div>
            </aside>

            {/* Main Content */}
            <main className="flex-1 overflow-auto p-8">
                {activeTab === 'library' && <SoftwareLibrary />}
                {activeTab === 'targets' && <DeploymentWizard />}
                {activeTab === 'dashboard' && (
                    <div className="text-center mt-20">
                        <h2 className="text-3xl font-bold text-gray-700">Dashboard Placeholder</h2>
                        <p className="text-gray-500 mt-2">Overview of installed software and machine status will go here.</p>
                    </div>
                )}
                {activeTab === 'deployments' && (
                    <div className="text-center mt-20">
                        <h2 className="text-3xl font-bold text-gray-700">Deployments Placeholder</h2>
                        <p className="text-gray-500 mt-2">History of deployments will go here.</p>
                    </div>
                )}
            </main>
        </div>
    )
}

function App() {
    return (
        <AuthProvider>
            <AppContent />
        </AuthProvider>
    )
}

function NavButton({ active, onClick, icon, label }: any) {
    return (
        <button
            onClick={onClick}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200 ${active
                ? 'bg-primary/10 text-primary border border-primary/20'
                : 'text-gray-400 hover:bg-white/5 hover:text-white'
                }`}
        >
            {icon}
            <span className="font-medium">{label}</span>
        </button>
    )
}

export default App
