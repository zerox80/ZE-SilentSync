import React, { createContext, useContext, useState, useLayoutEffect } from 'react';
import axios from 'axios';

const API_URL = '/api/v1';
axios.defaults.baseURL = API_URL;

interface AuthContextType {
    token: string | null;
    login: (username: string, password: string) => Promise<void>;
    logout: () => void;
    isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
    const [token, setToken] = useState<string | null>(() => {
        const savedToken = localStorage.getItem('token');
        if (savedToken) {
            axios.defaults.headers.common['Authorization'] = `Bearer ${savedToken}`;
        }
        return savedToken;
    });

    useLayoutEffect(() => {
        if (token) {
            localStorage.setItem('token', token);
            axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
        } else {
            localStorage.removeItem('token');
            delete axios.defaults.headers.common['Authorization'];
        }

        const interceptor = axios.interceptors.response.use(
            (response) => response,
            (error) => {
                if (error.response && error.response.status === 401) {
                    logout();
                }
                return Promise.reject(error);
            }
        );

        return () => {
            axios.interceptors.response.eject(interceptor);
        };
    }, [token]);

    const login = async (username: string, password: string) => {
        const formData = new FormData();
        formData.append('username', username);
        formData.append('password', password);

        try {
            const response = await axios.post('/auth/token', formData);
            setToken(response.data.access_token);
        } catch (error) {
            console.error("Login failed", error);
            throw error;
        }
    };

    const logout = () => {
        setToken(null);
    };

    return (
        <AuthContext.Provider value={{ token, login, logout, isAuthenticated: !!token }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};

// Export a configured axios instance if needed, but global defaults work for simple apps
export const api = axios;
