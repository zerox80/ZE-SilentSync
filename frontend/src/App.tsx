import { ReactNode } from 'react'
import { LayoutDashboard, AppWindow, Network, Send, LogOut, Monitor } from 'lucide-react'
import { BrowserRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import SoftwareLibrary from './components/SoftwareLibrary'
import DeploymentWizard from './components/DeploymentWizard'
import DeploymentsView from './components/DeploymentsView'
import MachinesView from './components/MachinesView'
import { AuthProvider, useAuth } from './auth/AuthContext'
import Login from './components/Login'

// Error Boundary Component
import React from 'react'
class ErrorBoundary extends React.Component<{ children: ReactNode }, { hasError: boolean }> {
    constructor(props: { children: ReactNode }) {
        super(props);
        this.state = { hasError: false };
    }

    static getDerivedStateFromError(_error: any) {
        return { hasError: true };
    }

    componentDidCatch(error: any, errorInfo: any) {
        console.error("Uncaught error:", error, errorInfo);
    }

    render() {
        if (this.state.hasError) {
            return (
                <div className="h-screen w-full flex items-center justify-center bg-dark text-white">
                    <div className="text-center">
                        <h1 className="text-3xl font-bold text-red-500 mb-4">Something went wrong.</h1>
                        <button onClick={() => window.location.reload()} className="px-4 py-2 bg-primary rounded">Reload Page</button>
                    </div>
                </div>
            );
        }
        return this.props.children;
    }
}

function AppContent() {
    const { isAuthenticated, logout } = useAuth()
    const navigate = useNavigate()
    const location = useLocation()
    const currentPath = location.pathname

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
                        active={currentPath === '/dashboard'}
                        onClick={() => navigate('/dashboard')}
                        icon={<LayoutDashboard size={20} />}
                        label="Dashboard"
                    />
                    <NavButton
                        active={currentPath === '/library' || currentPath === '/'}
                        onClick={() => navigate('/library')}
                        icon={<AppWindow size={20} />}
                        label="Software Library"
                    />
                    <NavButton
                        active={currentPath === '/targets'}
                        onClick={() => navigate('/targets')}
                        icon={<Network size={20} />}
                        label="Targets (AD)"
                    />
                    <NavButton
                        active={currentPath === '/deployments'}
                        onClick={() => navigate('/deployments')}
                        icon={<Send size={20} />}
                        label="Deployments"
                    />
                    <NavButton
                        active={currentPath === '/machines'}
                        onClick={() => navigate('/machines')}
                        icon={<Monitor size={20} />}
                        label="Machines"
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
                <ErrorBoundary>
                    <Routes>
                        <Route path="/" element={<SoftwareLibrary />} />
                        <Route path="/library" element={<SoftwareLibrary />} />
                        <Route path="/targets" element={<DeploymentWizard />} />
                        <Route path="/dashboard" element={
                            <div className="text-center mt-20">
                                <h2 className="text-3xl font-bold text-gray-700">Dashboard Placeholder</h2>
                                <p className="text-gray-500 mt-2">Overview of installed software and machine status will go here.</p>
                            </div>
                        } />
                        <Route path="/deployments" element={<DeploymentsView />} />
                        <Route path="/machines" element={<MachinesView />} />
                    </Routes>
                </ErrorBoundary>
            </main>
        </div>
    )
}

function App() {
    return (
        <BrowserRouter>
            <AuthProvider>
                <AppContent />
            </AuthProvider>
        </BrowserRouter>
    )
}

interface NavButtonProps {
    active: boolean;
    onClick: () => void;
    icon: ReactNode;
    label: string;
}

function NavButton({ active, onClick, icon, label }: NavButtonProps) {
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
